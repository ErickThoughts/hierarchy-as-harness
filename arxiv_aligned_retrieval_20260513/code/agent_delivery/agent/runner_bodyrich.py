"""
Body-rich 主实验 runner（plan.md §P1–P8 对齐版）。

相比原 runner.py：
- Budget 语义切到 `budget_eval.evaluate_at_budget`：取消 per-section/per-path k 上限，
  对候选池全量打分 → score 降序 → 字符级截断填充 `budget_chars`
- Summary 额外产出 ChunkHit@1 / MRR@chunks / Coverage@budget_lenient / evidence_chars_actual /
  trajectory_length（保留原 retrieval_metrics P@k / MRR / Coverage / nDCG 作对比）
- 支持可选 `pred_jsonl`：空 → Gold vs Flat-ReAct；非空 → Gold / Pred / Flat-ReAct
- 不侵入 agent_loop.run_agent_episode；本文件自带 episode 逻辑：
  hierarchy 可走 fixed/toolspace/compact，flat 臂统一使用 flat_react 多轮 search。

Process 层效率 `eff`（写入 `score_process`）：
- 默认：轨迹长度以 2 步为优、超过 2 后每 8 步线性扣至 0。
- `hier_policy=toolspace` 且 `representation=hierarchical` 时单独放宽（避免多步工具链被同一尺误伤），
  见 `_trajectory_efficiency` 及环境变量 `TOOLSPACE_STEP_BUDGET`、`PROCESS_EFF_SPAN_TOOLSPACE` 等。

**Task 判分**：默认 **语义主评测**（`JUDGE_SEMANTIC_PRIMARY=1`，需 `OPENAI_API_KEY` 等）。
加 `--inspect-judge` 时：任务 JSON 含 `inspect_id` 且在 Inspect 任务库命中则按 `inspect_scoring.score_sample`：
content 为「金标能抽出数字则数值完全匹配（仅 0/1）；否则仅用语义 LLM（失败记 0）；
`scope_collection` / `regulatory_coverage` 为 gold 条目 multiset recall 单一分数」，
evidence 仍为 evidence_line_ids 覆盖率；未命中库的题目仍用 `task_success_score` 语义 LLM。
汇总中额外给出 `inspect_evidence_mean`（仅统计命中 Inspect 的题，nan 跳过）。

Compose：**仅** `compose_answer_llm`（须 `OPENAI_API_KEY` / `OPENAI_BASE_URL` 等）；失败或返回非 JSON 即终止。
会加载 kit 内 Inspect 注册表；任务含 `inspect_id` 命中时，将 `metadata` 中与**输出形态**相关的字段
（`output_requirements`、`output_contract` 仅 mode 等、`answer_policy`）摘要注入 compose user prompt，
**不含** `judge_config`，且不把 Inspect 顶层金标键强塞进 schema。可用 tasks 行 `compose_format_hint` 覆盖。

**改指标（单项输出）**：输出 `score_task` / `score_evidence` / `score_process` 三项，不输出综合总分。

CLI:
    python3 -m agent_delivery.agent.runner_bodyrich \\
        --test_jsonl datasets/realdata/test_data_full_realdata_clean_merged.jsonl \\
        --tasks datasets/realdata/tasks_scope_collection_quick8.jsonl \\
        --out results/bodyrich/realdata/gold_flat_dense_b500.json \\
        --retrieval dense \\
        --budget-chars 500 \\
        [--pred_jsonl path/to/pred_levels.jsonl]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional, Sequence, Tuple

if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    _root = Path(__file__).resolve().parents[2]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from .tasks_loader import _load_tasks
from .types import AgentStep, AgentTask, EpisodeResult
from ..code.embedding_backend import DEFAULT_DENSE_EMBEDDING_MODEL, resolve_embedding_model
from ..code.budget_eval import (
    BudgetFillResult,
    compute_budget_retrieval_metrics,
    evaluate_at_budget,
    gather_flat_candidates,
)
from ..code.hierarchical_tools import HierarchicalTools
from ..code.index_retrieval import Chunk, CorpusIndex
from ..code.load_data import bundles_from_paths, line_node_id
from ..code.metrics import answer_keyword_recall_in_evidence, retrieval_metrics
from ..code.compose_llm import compose_answer_llm
from ..code.inspect_scoring import (
    build_inspect_pred_output,
    default_inspect_task_paths,
    evidence_line_ids_from_runner,
    inspect_compose_format_block,
    load_inspect_registry,
    score_sample,
)
from ..code.judge_llm import task_success_score
from ..code.llm_config import load_llm_env


def _configure_bodyrich_task_judge() -> None:
    """
    Body-rich：compose 与语义判分均强制走 LLM（OPENAI_API_KEY + OPENAI_BASE_URL 等来自 llm_api.env / 环境变量），
    失败即抛错，不使用离线 compose 回退。
    """
    load_llm_env()
    os.environ["JUDGE_SEMANTIC_PRIMARY"] = "1"
    os.environ["COMPOSE_USE_LLM"] = "1"
    os.environ["COMPOSE_STRICT"] = "1"


def _validate_task_gold_nodes_in_corpus(
    tasks: Sequence[AgentTask],
    bundles: Sequence[Any],
    *,
    context: str,
) -> None:
    """Fail fast if task gold evidence points to rows absent from the evaluation corpus."""
    nodes_by_doc: Dict[str, set[str]] = {}
    for b in bundles:
        nodes_by_doc[b.doc_id] = {line_node_id(b.doc_id, r.line_id) for r in b.lines}

    missing: List[str] = []
    for i, task in enumerate(tasks, start=1):
        doc_id = task.doc_id or ""
        available = nodes_by_doc.get(doc_id)
        if available is None:
            missing.append(
                f"task#{i} inspect_id={task.inspect_id or ''} doc_id={doc_id!r} missing document"
            )
            continue
        bad = [n for n in task.gold_nodes if n not in available]
        if bad:
            missing.append(
                f"task#{i} inspect_id={task.inspect_id or ''} doc_id={doc_id!r} missing gold_nodes={bad}"
            )

    if missing:
        preview = "\n".join(missing[:20])
        extra = "" if len(missing) <= 20 else f"\n... {len(missing) - 20} more"
        raise ValueError(
            f"{context}: task gold_nodes are not aligned with the evaluation corpus.\n"
            f"{preview}{extra}"
        )


def _line_id_from_gold_node(node: str) -> Optional[int]:
    m = re.search(r":L(\d+)\s*$", str(node).strip(), flags=re.I)
    return int(m.group(1)) if m else None


def _stratification_fields(tools: HierarchicalTools, task: AgentTask) -> Dict[str, Any]:
    """plan 分层：文档行数桶 + 金证据行 gold_level 桶（来自 gold tree LineRecord）。"""
    doc_id = task.doc_id or ""
    nlines = 0
    gl = 0
    if doc_id and doc_id in tools.index._bundles:
        nlines = len(tools.index._bundles[doc_id].lines)
        if task.gold_nodes:
            lid = _line_id_from_gold_node(task.gold_nodes[0])
            if lid is not None:
                for lr in tools.index._bundles[doc_id].lines:
                    if lr.line_id == lid:
                        gl = int(lr.gold_level)
                        break
    if nlines <= 30:
        dlb = "≤30"
    elif nlines <= 100:
        dlb = "31–100"
    elif nlines <= 300:
        dlb = "101–300"
    else:
        dlb = ">300"
    if gl <= 0:
        glb = "0/unk"
    elif gl <= 3:
        glb = str(gl)
    else:
        glb = "4+"
    return {
        "doc_line_count": nlines,
        "gold_level_primary": gl,
        "doc_lines_bucket": dlb,
        "gold_level_bucket": glb,
    }


def _chunks_to_retrieved_nodes(chunks: Sequence[Chunk]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for c in chunks:
        for lid in c.line_ids:
            node = f"{c.doc_id}:L{lid}"
            if node not in seen:
                seen.add(node)
                out.append(node)
    return out


def _require_inspect_registry_for_judge(
    *,
    use_inspect_judge: bool,
    inspect_by_id: Optional[Dict[str, Any]],
    inspect_paths_resolved: List[Path],
    kit_root: Path,
    tasks: List[AgentTask],
) -> None:
    """--inspect-judge 时禁止空注册表或缺 inspect_id：有问题直接失败，不静默用语义 fallback。"""
    if not use_inspect_judge:
        return
    if not inspect_by_id:
        raise RuntimeError(
            "已开启 inspect 判分但注册表为空：未加载到任何 Inspect JSONL。"
            f" kit_root={kit_root}；解析到的路径={inspect_paths_resolved!r}。"
            "请确认 datasets/realdata 下三套 *_inspect.jsonl 存在，或显式传入 --inspect-tasks。"
        )
    for idx, task in enumerate(tasks):
        iid = (task.inspect_id or "").strip()
        if not iid or iid not in inspect_by_id:
            raise RuntimeError(
                "inspect 判分要求每条任务的 inspect_id 均在注册表内："
                f"行 {idx} inspect_id={iid!r}（registry_size={len(inspect_by_id)}）。"
            )


def _merge_scored_chunk_pools(
    *pools: Sequence[Tuple[Chunk, float]],
) -> List[Tuple[Chunk, float]]:
    """多路候选按 node_id 去重，保留最高分，再按分数降序。"""
    best: Dict[str, Tuple[Chunk, float]] = {}
    for pool in pools:
        for c, s in pool:
            bid = c.node_id
            prev = best.get(bid)
            if prev is None or float(s) > float(prev[1]):
                best[bid] = (c, float(s))
    return sorted(best.values(), key=lambda x: -x[1])


def _compose_format_constraints_for_task(
    task: AgentTask,
    inspect_by_id: Optional[Dict[str, Dict[str, Any]]],
) -> str:
    h = str(getattr(task, "compose_format_hint", "") or "").strip()
    if h:
        return h[:8000]
    iid = str(getattr(task, "inspect_id", None) or "").strip()
    if inspect_by_id and iid and iid in inspect_by_id:
        return inspect_compose_format_block(inspect_by_id[iid])
    return ""


def _effective_route_m_for_retrieval(
    route_m: int,
    task: Optional[AgentTask],
    inspect_by_id: Optional[Dict[str, Dict[str, Any]]],
) -> int:
    """
    multi_hop / scope / regulatory：多节路由略增 m，扩大层级候选池（可用 BODYRICH_ROUTE_M_BONUS_MULTI_SCOPE 调）。
    """
    base = max(1, int(route_m))
    if not task:
        return base
    eff = _effective_task_type_for_compose(task, inspect_by_id)
    bonus = int(os.environ.get("BODYRICH_ROUTE_M_BONUS_MULTI_SCOPE", "1").strip() or "1")
    if eff in ("multi_hop", "scope_collection", "regulatory_coverage"):
        return min(8, base + max(0, bonus))
    return base


def _effective_task_type_for_compose(
    task: AgentTask, inspect_by_id: Optional[Dict[str, Dict[str, Any]]]
) -> str:
    """
    与 Inspect 解析/阅卷一致：任务带 inspect_id 且在注册表命中、且元数据含 task_type 时，
    compose 与非 Inspect 的语义判分采用该类型（避免 tasks 行 task_type 与 Inspect metadata 双源错位）。
    """
    base = (task.task_type or "unknown").strip() or "unknown"
    iid = str(getattr(task, "inspect_id", None) or "").strip()
    if not (inspect_by_id and iid and iid in inspect_by_id):
        return base
    inst = inspect_by_id[iid]
    md = inst.get("metadata") if isinstance(inst.get("metadata"), dict) else {}
    it = str(md.get("task_type", "") or "").strip()
    return it if it else base


def _make_composed_answer(
    task: AgentTask,
    fill: BudgetFillResult,
    *,
    budget_chars: int,
    inspect_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> str:
    """plan：结构化 JSON compose，仅走 OpenAI 兼容 LLM；失败直接抛错。"""
    ev = (fill.evidence_text or "")[: max(1, int(budget_chars))]
    max_ans = min(1024, max(256, int(budget_chars)))
    tt = _effective_task_type_for_compose(task, inspect_by_id)
    fc = _compose_format_constraints_for_task(task, inspect_by_id)
    return compose_answer_llm(
        task.query,
        task_type=tt,
        evidence_text=ev,
        max_answer_chars=max_ans,
        budget_chars=int(budget_chars),
        format_constraints=fc,
    )


def _query_variants_for_flat_react(query: str, task_type: str, max_rounds: int) -> List[str]:
    """Flat-ReAct 的轻量 rewrite/decomposition；只产生查询，不使用层级工具。"""
    q = (query or "").strip()
    if not q or max_rounds <= 0:
        return []
    variants: List[str] = []

    def add(s: str) -> None:
        t = re.sub(r"\s+", " ", (s or "").strip())
        if t and t not in variants:
            variants.append(t)

    add(q)
    stripped = re.sub(
        r"(请|根据|列出|列举|说明|回答|文中|本条例|本方案|所有|哪些|多少|是什么|分别|以及|包括|中提到的)",
        " ",
        q,
    )
    add(stripped)
    for part in re.split(r"[，,；;。?？]|以及|和|与|及|、", q):
        if len(part.strip()) >= 4:
            add(part)
    tt = (task_type or "").lower()
    if tt in ("multi_hop", "scope_collection", "regulatory_coverage"):
        add(q + " 相关条款 定义 条件 范围")
    add(q + " 答案 证据 原文")
    return variants[: max(1, max_rounds)]


def _all_top_section_ids(tools: HierarchicalTools, doc_id: Optional[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for c in tools.index.section_summaries:
        if doc_id is not None and c.doc_id != doc_id:
            continue
        sid = c.section_id or c.node_id
        if sid and sid not in seen:
            seen.add(sid)
            out.append(sid)
    if out or not doc_id:
        return out
    b = tools.index._bundles.get(doc_id)
    if b and b.lines:
        from ..code.load_data import line_node_id

        return [line_node_id(doc_id, b.lines[0].line_id)]
    return []


def _score_top_sections(
    tools: HierarchicalTools,
    query: str,
    *,
    doc_id: Optional[str],
) -> Dict[str, float]:
    pool = [c for c in tools.index.section_summaries if doc_id is None or c.doc_id == doc_id]
    if not pool:
        return {}
    scored = tools.index.search(query, pool, len(pool), doc_id_filter=doc_id)
    score_by_sid: Dict[str, float] = {}
    for c, s in scored:
        sid = c.section_id or c.node_id
        score_by_sid[sid] = max(float(s), score_by_sid.get(sid, float("-inf")))
    return score_by_sid


def _gather_all_section_candidates(
    tools: HierarchicalTools,
    query: str,
    *,
    doc_id: Optional[str],
) -> Tuple[List[Tuple[Chunk, float]], List[str]]:
    section_ids = _all_top_section_ids(tools, doc_id)
    score_by_sid = _score_top_sections(tools, query, doc_id=doc_id)
    scored: List[Tuple[Chunk, float]] = []
    for sid in section_ids:
        pool = list(tools.index.fact_by_section.get(sid, []))
        if not pool:
            continue
        hits = tools.index.search(query, pool, len(pool), doc_id_filter=doc_id)
        sec_weight = 1.0 + max(0.0, score_by_sid.get(sid, 0.0)) * 0.05
        scored.extend((c, float(s) * sec_weight) for c, s in hits)
    return _merge_scored_chunk_pools(scored), section_ids


def run_flat_react_episode(
    tools: HierarchicalTools,
    query: str,
    *,
    doc_id: Optional[str],
    budget_chars: int,
    task: AgentTask,
    inspect_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> EpisodeResult:
    """
    Flat 对照的多步 agent：多轮 search + query rewrite/decomposition + budget_fill + compose。
    不调用 get_map/get_structure/read_chunks(section_path)，避免引入层级语义。
    """
    rounds = int(os.environ.get("FLAT_REACT_SEARCH_ROUNDS", "3").strip() or "3")
    rounds = max(1, min(8, rounds))
    k_each = int(os.environ.get("FLAT_REACT_K_PER_ROUND", "64").strip() or "64")
    k_each = max(8, min(256, k_each))
    tt = _effective_task_type_for_compose(task, inspect_by_id)
    queries = _query_variants_for_flat_react(query, tt, rounds)

    steps: List[AgentStep] = []
    all_scored: List[Tuple[Chunk, float]] = []
    for qi, q in enumerate(queries, start=1):
        scored_q = gather_flat_candidates(tools, q, doc_id=doc_id)[:k_each]
        weight = 1.0 if qi == 1 else max(0.45, 0.82 ** (qi - 1))
        all_scored.extend((c, float(s) * weight) for c, s in scored_q)
        steps.append(
            AgentStep(
                step_idx=len(steps) + 1,
                action="flat_react_search",
                detail={
                    "round": qi,
                    "query": q[:160],
                    "k": k_each,
                    "n_hits": len(scored_q),
                    "weight": weight,
                },
            )
        )

    scored = _merge_scored_chunk_pools(all_scored)
    fill: BudgetFillResult = evaluate_at_budget(scored, budget_chars=budget_chars)
    retrieved_nodes = _chunks_to_retrieved_nodes(fill.kept_chunks)
    composed = _make_composed_answer(task, fill, budget_chars=budget_chars, inspect_by_id=inspect_by_id)
    steps.append(
        AgentStep(
            step_idx=len(steps) + 1,
            action="compose_answer",
            detail={
                "evidence_chars": fill.evidence_chars_actual,
                "n_chunks_kept": fill.n_chunks_kept,
                "truncated_last": fill.truncated_last,
            },
        )
    )
    return EpisodeResult(
        representation="flat_react",
        steps=steps,
        scored_chunks=scored,
        kept_chunks=fill.kept_chunks,
        evidence_text=fill.evidence_text,
        evidence_chars_actual=fill.evidence_chars_actual,
        retrieved_nodes=retrieved_nodes,
        composed_answer=composed,
        section_ids=[],
        trajectory_length=len(steps),
        truncated_last=fill.truncated_last,
        refusal_events=[],
    )


def _select_all_sections_with_confidence(
    tools: HierarchicalTools,
    query: str,
    *,
    doc_id: Optional[str],
    route_m: int,
) -> Tuple[List[str], float, Dict[str, float]]:
    section_ids = _all_top_section_ids(tools, doc_id)
    score_by_sid = _score_top_sections(tools, query, doc_id=doc_id)
    conf_vals = [score_by_sid.get(sid, 0.0) for sid in section_ids]
    confidence = max(conf_vals) if conf_vals else 0.0
    return section_ids, float(confidence), score_by_sid


def _compact_scope_sweep_sections(
    tools: HierarchicalTools,
    base_sections: Sequence[str],
    *,
    doc_id: Optional[str],
    task: Optional[AgentTask],
    inspect_by_id: Optional[Dict[str, Dict[str, Any]]],
) -> List[str]:
    selected: List[str] = []
    for sid in base_sections:
        if sid and sid not in selected:
            selected.append(sid)
    if not task:
        return selected
    tt = _effective_task_type_for_compose(task, inspect_by_id)
    if tt not in ("multi_hop", "scope_collection", "regulatory_coverage"):
        return selected
    limit = int(os.environ.get("HIER_COMPACT_SCOPE_SWEEP_MAX_SECTIONS", "6").strip() or "6")
    for sid, pool in tools.index.fact_by_section.items():
        if len(selected) >= limit:
            break
        if doc_id is not None and (not pool or pool[0].doc_id != doc_id):
            continue
        if sid not in selected:
            selected.append(sid)
    return selected


def _run_hier_compact_episode(
    tools: HierarchicalTools,
    query: str,
    *,
    doc_id: Optional[str],
    budget_chars: int,
    route_m: int,
    task: Optional[AgentTask],
    inspect_by_id: Optional[Dict[str, Dict[str, Any]]],
) -> EpisodeResult:
    rm = _effective_route_m_for_retrieval(route_m, task, inspect_by_id)
    section_ids, confidence, score_by_sid = _select_all_sections_with_confidence(
        tools, query, doc_id=doc_id, route_m=rm
    )
    scoped_sections = _compact_scope_sweep_sections(
        tools, section_ids, doc_id=doc_id, task=task, inspect_by_id=inspect_by_id
    )
    scored: List[Tuple[Chunk, float]] = []
    for sid in scoped_sections:
        pool = list(tools.index.fact_by_section.get(sid, []))
        if not pool:
            continue
        hits = tools.index.search(query, pool, len(pool), doc_id_filter=doc_id)
        sec_weight = 1.0 + max(0.0, score_by_sid.get(sid, 0.0)) * 0.05
        scored.extend((c, float(s) * sec_weight) for c, s in hits)
    scored = _merge_scored_chunk_pools(scored)
    steps: List[AgentStep] = [
        AgentStep(
            step_idx=1,
            action="select_all_top_sections_with_confidence",
            detail={
                "mode": "no_level1_prefilter",
                "route_m_ignored": route_m,
                "effective_route_m_ignored": rm,
                "confidence": confidence,
                "n_sections": len(section_ids),
            },
        ),
        AgentStep(
            step_idx=2,
            action="read_by_path_or_scope_sweep",
            detail={
                "sections": list(scoped_sections),
                "scope_sweep_added": max(0, len(scoped_sections) - len(section_ids)),
                "n_scored": len(scored),
            },
        ),
    ]
    fill: BudgetFillResult = evaluate_at_budget(scored, budget_chars=budget_chars)
    retrieved_nodes = _chunks_to_retrieved_nodes(fill.kept_chunks)
    if task is None:
        task = AgentTask(query=query, doc_id=doc_id, gold_nodes=[], gold_answer="", task_type="niche_fact")
    composed = _make_composed_answer(task, fill, budget_chars=budget_chars, inspect_by_id=inspect_by_id)
    steps.append(
        AgentStep(
            step_idx=3,
            action="compose_answer",
            detail={
                "evidence_chars": fill.evidence_chars_actual,
                "n_chunks_kept": fill.n_chunks_kept,
                "truncated_last": fill.truncated_last,
            },
        )
    )
    return EpisodeResult(
        representation="hierarchical_compact",
        steps=steps,
        scored_chunks=scored,
        kept_chunks=fill.kept_chunks,
        evidence_text=fill.evidence_text,
        evidence_chars_actual=fill.evidence_chars_actual,
        retrieved_nodes=retrieved_nodes,
        composed_answer=composed,
        section_ids=list(scoped_sections),
        trajectory_length=len(steps),
        truncated_last=fill.truncated_last,
        refusal_events=[],
    )


def run_bodyrich_episode(
    tools: HierarchicalTools,
    query: str,
    *,
    doc_id: Optional[str],
    representation: str,
    budget_chars: int,
    route_m: int = 2,
    hier_policy: str = "fixed",
    task: Optional[AgentTask] = None,
    inspect_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
) -> EpisodeResult:
    """
    plan §P1-P2 合规 episode：
      hierarchical: full top-level map → agent/selector chooses paths → budget_fill → compose
      flat:         flat_react 多轮 search/rewrite → budget_fill → compose
    trajectory_length = tool_calls 总数（含 compose）；flat 臂为多轮 search + compose。
    hier_policy=toolspace 时使用 plan §5.3 五工具 + refusal + react_agent 确定性策略。
    """
    if representation == "hierarchical" and hier_policy == "toolspace":
        if not doc_id:
            raise ValueError("hier_policy=toolspace 需要 task.doc_id")
        from .react_agent import run_toolspace_episode

        tt = _effective_task_type_for_compose(task, inspect_by_id) if task else "unknown"
        t_fmt = task or AgentTask(
            query=query,
            doc_id=doc_id,
            gold_nodes=[],
            gold_answer="",
            task_type=tt,
        )
        fc = _compose_format_constraints_for_task(t_fmt, inspect_by_id)
        return run_toolspace_episode(
            tools,
            query,
            doc_id=doc_id,
            budget_chars=budget_chars,
            route_m=route_m,
            task_type=tt,
            compose_format_constraints=fc,
        )

    if representation == "hierarchical" and hier_policy == "compact":
        return _run_hier_compact_episode(
            tools,
            query,
            doc_id=doc_id,
            budget_chars=budget_chars,
            route_m=route_m,
            task=task,
            inspect_by_id=inspect_by_id,
        )

    steps: List[AgentStep] = []
    scored: List[Tuple[Chunk, float]] = []
    section_ids: List[str] = []

    if representation == "hierarchical":
        rm = _effective_route_m_for_retrieval(route_m, task, inspect_by_id)
        scored, section_ids = _gather_all_section_candidates(
            tools, query, doc_id=doc_id
        )
        steps.append(
            AgentStep(
                step_idx=1,
                action="select_all_top_sections",
                detail={
                    "mode": "no_level1_prefilter",
                    "route_m_ignored": route_m,
                    "effective_route_m_ignored": rm,
                    "n_sections": len(section_ids),
                },
            )
        )
        steps.append(
            AgentStep(
                step_idx=2,
                action="retrieve_facts_all",
                detail={"n_scored": len(scored)},
            )
        )
    elif representation == "flat":
        raise ValueError("旧 one-shot flat 已移除；正式 flat 臂请调用 run_flat_react_episode。")
    else:
        raise ValueError(f"unknown representation: {representation}")

    fill: BudgetFillResult = evaluate_at_budget(scored, budget_chars=budget_chars)
    retrieved_nodes = _chunks_to_retrieved_nodes(fill.kept_chunks)
    if task is None:
        # 兼容旧调用：无 task 时用占位 task_type
        task = AgentTask(query=query, doc_id=doc_id, gold_nodes=[], gold_answer="", task_type="niche_fact")
    composed = _make_composed_answer(task, fill, budget_chars=budget_chars, inspect_by_id=inspect_by_id)

    steps.append(
        AgentStep(
            step_idx=len(steps) + 1,
            action="compose_answer",
            detail={
                "evidence_chars": fill.evidence_chars_actual,
                "n_chunks_kept": fill.n_chunks_kept,
                "truncated_last": fill.truncated_last,
            },
        )
    )

    return EpisodeResult(
        representation=representation,
        steps=steps,
        scored_chunks=scored,
        kept_chunks=fill.kept_chunks,
        evidence_text=fill.evidence_text,
        evidence_chars_actual=fill.evidence_chars_actual,
        retrieved_nodes=retrieved_nodes,
        composed_answer=composed,
        section_ids=section_ids,
        trajectory_length=len(steps),
        truncated_last=fill.truncated_last,
        refusal_events=[],
    )


def _empty_agg() -> Dict[str, List[float]]:
    return {
        "chunk_hit_at_1": [],
        "mrr_chunks": [],
        "coverage_budget_lenient": [],
        "evidence_chars_actual": [],
        "trajectory_length": [],
        "n_chunks_kept": [],
        "truncated_last": [],
        "keyword_recall": [],
        # legacy retrieval metrics (line-level)
        "precision@1": [],
        "precision@3": [],
        "precision@5": [],
        "precision@8": [],
        "coverage_line": [],
        "mrr_line": [],
        "ndcg@10": [],
        "hit@5": [],
        "task_success": [],
        # 三层评分（当前不再做加权融合，保持与原子指标一致）
        "score_task": [],
        "score_evidence": [],
        "score_process": [],
        # 原子指标（显式输出）
        "evidence_hit@1": [],
        "evidence_coverage": [],
        "process_recovery": [],
        "process_efficiency": [],
    }


def _trajectory_efficiency(
    trajectory_length: float,
    *,
    hier_policy: str,
    representation: str,
) -> Tuple[float, str]:
    """
    返回 (eff, mode_tag)。eff ∈ [0,1]，越大表示轨迹越「省」。

    toolspace + hierarchical：按 TOOLSPACE_STEP_BUDGET 拉长惩罚区间（默认同倍率），
    不把 9～10 步直接打到接近 0。
    """
    t = float(trajectory_length)
    hp = (hier_policy or "").strip().lower()
    rep = (representation or "").strip().lower()
    # react_agent.run_toolspace_episode 使用 representation="hierarchical_toolspace"
    if hp == "toolspace" and (
        rep == "hierarchical" or rep == "hierarchical_toolspace" or rep.startswith("hierarchical_")
    ):
        opt = float(os.environ.get("PROCESS_OPT_TRAJECTORY_TOOLSPACE", "2").strip() or "2")
        step_budget = float(os.environ.get("TOOLSPACE_STEP_BUDGET", "10").strip() or "10")
        factor = float(os.environ.get("PROCESS_EFF_SPAN_FACTOR_TOOLSPACE", "2").strip() or "2")
        span_env = os.environ.get("PROCESS_EFF_SPAN_TOOLSPACE", "").strip()
        if span_env:
            span = max(1.0, float(span_env))
        else:
            span = max(6.0, (step_budget - opt) * max(1.0, factor))
        eff = max(0.0, 1.0 - min(1.0, max(0.0, t - opt) / span))
        return eff, "toolspace_hierarchical"
    eff = max(0.0, 1.0 - min(1.0, max(0.0, t - 2.0) / 8.0))
    return eff, "default"


def _fill_agg(
    agg: Dict[str, List[float]],
    ep: EpisodeResult,
    task: AgentTask,
    *,
    hier_policy: str = "fixed",
    inspect_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
    use_inspect_judge: bool = False,
) -> Dict[str, Any]:
    budget_m = compute_budget_retrieval_metrics(ep.kept_chunks, task.gold_nodes)
    rline = retrieval_metrics(ep.retrieved_nodes, task.gold_nodes, k_list=(1, 3, 5, 8))
    kw = (
        answer_keyword_recall_in_evidence(ep.evidence_text, task.gold_answer)
        if task.gold_answer
        else None
    )
    composed = ep.composed_answer
    if not composed:
        fill_fb = BudgetFillResult(
            kept_chunks=list(ep.kept_chunks),
            evidence_text=ep.evidence_text or "",
            evidence_chars_actual=int(ep.evidence_chars_actual),
            n_chunks_kept=len(ep.kept_chunks),
            truncated_last=bool(ep.truncated_last),
        )
        b_fb = max(100, int(ep.evidence_chars_actual) or 500)
        composed = _make_composed_answer(
            task, fill_fb, budget_chars=b_fb, inspect_by_id=inspect_by_id
        )
    inspect_meta: Dict[str, Any] = {}
    inspect_evidence_value: Optional[float] = None
    eff_tt = _effective_task_type_for_compose(task, inspect_by_id)
    iid = (task.inspect_id or "").strip() if getattr(task, "inspect_id", None) else ""
    use_inspect_this = bool(
        use_inspect_judge
        and inspect_by_id
        and iid
        and iid in inspect_by_id
    )
    if use_inspect_this:
        insp_task = inspect_by_id[iid]
        eids = evidence_line_ids_from_runner(
            retrieved_nodes=ep.retrieved_nodes,
            kept_chunks=ep.kept_chunks,
            doc_id=task.doc_id,
        )
        pred_out = build_inspect_pred_output(
            composed, evidence_line_ids=eids, inspect_task=insp_task
        )
        c_sc, e_sc, insp_extra = score_sample(insp_task, pred_out)
        ts = float(c_sc)
        inspect_evidence_value = float(e_sc)
        agg.setdefault("inspect_evidence_score", []).append(float(e_sc))
        inspect_meta = {
            "inspect_judge_used": True,
            "inspect_id": iid,
            "inspect_evidence_score": float(e_sc),
            "inspect_content_score": float(c_sc),
            **{f"inspect_{k}": v for k, v in insp_extra.items()},
        }
    else:
        ts = task_success_score(
            eff_tt,
            composed,
            task.gold_answer,
            gold_nodes=task.gold_nodes,
            evidence_text=ep.evidence_text,
        )
        if use_inspect_judge:
            agg.setdefault("inspect_evidence_score", []).append(float("nan"))
        inspect_meta = {
            "inspect_judge_used": False,
            "inspect_id": iid or None,
        }
    # --- 三层评分（无加权）：直接用原子指标 ---
    # 1) Task 层：任务完成度
    score_task = float(ts)
    evidence_hit1 = float(budget_m["chunk_hit@1"])
    evidence_cov = float(budget_m["coverage_budget_lenient"])
    # 2) Evidence 层：Inspect 模式下使用 Inspect evidence 覆盖率；否则使用预算内覆盖率。
    score_evidence = float(inspect_evidence_value) if inspect_evidence_value is not None else evidence_cov
    # 3) Process 层：直接取效率（recovery 单独指标输出）
    refusal_cnt = len(ep.refusal_events or [])
    recovery = 1.0 if refusal_cnt == 0 else (1.0 if float(ts) >= 0.34 else 0.0)
    eff, eff_mode = _trajectory_efficiency(
        float(ep.trajectory_length),
        hier_policy=hier_policy,
        representation=str(ep.representation or ""),
    )
    score_process = float(eff)
    agg["task_success"].append(float(ts))
    agg["score_task"].append(float(score_task))
    agg["score_evidence"].append(float(score_evidence))
    agg["score_process"].append(float(score_process))
    agg["evidence_hit@1"].append(evidence_hit1)
    agg["evidence_coverage"].append(evidence_cov)
    agg["process_recovery"].append(float(recovery))
    agg["process_efficiency"].append(float(eff))
    agg["chunk_hit_at_1"].append(float(budget_m["chunk_hit@1"]))
    agg["mrr_chunks"].append(float(budget_m["mrr_chunks"]))
    agg["coverage_budget_lenient"].append(float(budget_m["coverage_budget_lenient"]))
    agg["evidence_chars_actual"].append(float(ep.evidence_chars_actual))
    agg["trajectory_length"].append(float(ep.trajectory_length))
    agg["n_chunks_kept"].append(float(budget_m["n_chunks_kept"]))
    agg["truncated_last"].append(1.0 if ep.truncated_last else 0.0)
    if kw is not None:
        agg["keyword_recall"].append(float(kw))
    agg["precision@1"].append(float(rline["precision@1"]))
    agg["precision@3"].append(float(rline["precision@3"]))
    agg["precision@5"].append(float(rline["precision@5"]))
    agg["precision@8"].append(float(rline["precision@8"]))
    agg["coverage_line"].append(float(rline["coverage"]))
    agg["mrr_line"].append(float(rline["mrr"]))
    agg["ndcg@10"].append(float(rline["ndcg@10"]))
    agg["hit@5"].append(float(rline["hit@5"]))
    return {
        "budget": budget_m,
        "line_retrieval": rline,
        "keyword_recall": kw,
        "task_success": float(ts),
        "score_task": float(score_task),
        "score_evidence": float(score_evidence),
        "score_process": float(score_process),
        "evidence_hit@1": evidence_hit1,
        "evidence_coverage": evidence_cov,
        "process_recovery": float(recovery),
        "process_efficiency": float(eff),
        "process_efficiency_mode": eff_mode,
        "effective_task_type": eff_tt,
        **inspect_meta,
    }


def _mean(xs: List[float]) -> float:
    return mean(xs) if xs else 0.0


def _mean_skip_nan(xs: List[float]) -> Optional[float]:
    vals = [float(x) for x in xs if isinstance(x, (int, float)) and x == x]
    if not vals:
        return None
    return float(mean(vals))


def _agg_summary(agg: Dict[str, List[float]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        # plan §P6 主表（3 列严格对齐 + 1 列 N/A）
        "evidence_chars_actual_mean": _mean(agg["evidence_chars_actual"]),
        "trajectory_length_mean": _mean(agg["trajectory_length"]),
        "refusal_recovery_rate": None,  # toolspace 时在 _build_summary 中填；固定管线无 refusal
        "task_success_semantic_mean": _mean(agg["task_success"]),
        "task_success_approx_keyword_recall_mean": _mean(agg["keyword_recall"]),
        # 三层评分汇总
        "score_task_mean": _mean(agg["score_task"]),
        "score_evidence_mean": _mean(agg["score_evidence"]),
        "score_process_mean": _mean(agg["score_process"]),
        # 直接输出原子指标（无加权）
        "evidence_hit@1_mean": _mean(agg["evidence_hit@1"]),
        "evidence_coverage_mean": _mean(agg["evidence_coverage"]),
        "process_recovery_mean": _mean(agg["process_recovery"]),
        "process_efficiency_mean": _mean(agg["process_efficiency"]),
        # plan §P7 附录（严格）
        "chunk_hit@1_mean": _mean(agg["chunk_hit_at_1"]),
        "mrr_chunks_mean": _mean(agg["mrr_chunks"]),
        "coverage_budget_lenient_mean": _mean(agg["coverage_budget_lenient"]),
        # 辅助
        "n_chunks_kept_mean": _mean(agg["n_chunks_kept"]),
        "truncated_last_rate": _mean(agg["truncated_last"]),
        # 额外：原 line-level retrieval 指标（与 v1 论文可比）
        "precision@1_mean": _mean(agg["precision@1"]),
        "precision@3_mean": _mean(agg["precision@3"]),
        "precision@5_mean": _mean(agg["precision@5"]),
        "precision@8_mean": _mean(agg["precision@8"]),
        "coverage_line_mean": _mean(agg["coverage_line"]),
        "mrr_line_mean": _mean(agg["mrr_line"]),
        "ndcg@10_mean": _mean(agg["ndcg@10"]),
        "hit@5_mean": _mean(agg["hit@5"]),
    }
    ev_ins = agg.get("inspect_evidence_score")
    if ev_ins:
        m = _mean_skip_nan(ev_ins)
        if m is not None:
            out["inspect_evidence_mean"] = m
    return out


def _per_type_summary(
    rows: List[Dict[str, Any]], system_key: str
) -> Dict[str, Dict[str, Any]]:
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        hg = r.get("hierarchical_gold") or {}
        m0 = hg.get("metrics") if isinstance(hg.get("metrics"), dict) else {}
        t = str(m0.get("effective_task_type") or r.get("task_type") or "unknown")
        by_type.setdefault(t, []).append(r)
    out: Dict[str, Dict[str, Any]] = {}
    for t, rs in by_type.items():
        agg = _empty_agg()
        for r in rs:
            sys_data = r.get(system_key) or {}
            m = sys_data.get("metrics") or {}
            agg["chunk_hit_at_1"].append(float(m.get("budget", {}).get("chunk_hit@1", 0.0)))
            agg["mrr_chunks"].append(float(m.get("budget", {}).get("mrr_chunks", 0.0)))
            agg["coverage_budget_lenient"].append(
                float(m.get("budget", {}).get("coverage_budget_lenient", 0.0))
            )
            agg["evidence_chars_actual"].append(
                float(sys_data.get("evidence_chars_actual", 0))
            )
            agg["trajectory_length"].append(float(sys_data.get("trajectory_length", 0)))
            agg["n_chunks_kept"].append(
                float(m.get("budget", {}).get("n_chunks_kept", 0.0))
            )
            agg["truncated_last"].append(1.0 if sys_data.get("truncated_last") else 0.0)
            kw = m.get("keyword_recall")
            if kw is not None:
                agg["keyword_recall"].append(float(kw))
            tsv = m.get("task_success")
            if tsv is not None:
                agg["task_success"].append(float(tsv))
            st = m.get("score_task")
            if st is not None:
                agg["score_task"].append(float(st))
            se = m.get("score_evidence")
            if se is not None:
                agg["score_evidence"].append(float(se))
            sp = m.get("score_process")
            if sp is not None:
                agg["score_process"].append(float(sp))
            eh = m.get("evidence_hit@1")
            if eh is not None:
                agg["evidence_hit@1"].append(float(eh))
            ec = m.get("evidence_coverage")
            if ec is not None:
                agg["evidence_coverage"].append(float(ec))
            pr = m.get("process_recovery")
            if pr is not None:
                agg["process_recovery"].append(float(pr))
            pe = m.get("process_efficiency")
            if pe is not None:
                agg["process_efficiency"].append(float(pe))
            lr = m.get("line_retrieval") or {}
            agg["precision@1"].append(float(lr.get("precision@1", 0.0)))
            agg["precision@3"].append(float(lr.get("precision@3", 0.0)))
            agg["precision@5"].append(float(lr.get("precision@5", 0.0)))
            agg["precision@8"].append(float(lr.get("precision@8", 0.0)))
            agg["coverage_line"].append(float(lr.get("coverage", 0.0)))
            agg["mrr_line"].append(float(lr.get("mrr", 0.0)))
            agg["ndcg@10"].append(float(lr.get("ndcg@10", 0.0)))
            agg["hit@5"].append(float(lr.get("hit@5", 0.0)))
        out[t] = {"n": len(rs), **_agg_summary(agg)}
    return out


def _run_episodes_for_budget(
    tools_g: HierarchicalTools,
    tools_f: HierarchicalTools,
    tools_p: Optional[HierarchicalTools],
    tasks: List[AgentTask],
    budget_chars: int,
    route_m: int,
    pred_enabled: bool,
    hier_policy: str = "fixed",
    *,
    inspect_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
    use_inspect_judge: bool = False,
) -> Tuple[
    Dict[str, List[float]],
    Dict[str, List[float]],
    Dict[str, List[float]],
    List[Dict[str, Any]],
]:
    agg_g = _empty_agg()
    agg_p = _empty_agg()
    agg_f = _empty_agg()
    rows: List[Dict[str, Any]] = []
    for ti, task in enumerate(tasks, start=1):
        strat = _stratification_fields(tools_g, task)
        ep_g = run_bodyrich_episode(
            tools_g,
            task.query,
            doc_id=task.doc_id,
            representation="hierarchical",
            budget_chars=budget_chars,
            route_m=route_m,
            hier_policy=hier_policy,
            task=task,
            inspect_by_id=inspect_by_id,
        )
        ep_f = run_flat_react_episode(
            tools_f,
            task.query,
            doc_id=task.doc_id,
            budget_chars=budget_chars,
            task=task,
            inspect_by_id=inspect_by_id,
        )
        ep_p: Optional[EpisodeResult] = None
        if tools_p is not None:
            ep_p = run_bodyrich_episode(
                tools_p,
                task.query,
                doc_id=task.doc_id,
                representation="hierarchical",
                budget_chars=budget_chars,
                route_m=route_m,
                hier_policy=hier_policy,
                task=task,
                inspect_by_id=inspect_by_id,
            )
        metrics_g = _fill_agg(
            agg_g,
            ep_g,
            task,
            hier_policy=hier_policy,
            inspect_by_id=inspect_by_id,
            use_inspect_judge=use_inspect_judge,
        )
        metrics_f = _fill_agg(
            agg_f,
            ep_f,
            task,
            hier_policy="flat_react",
            inspect_by_id=inspect_by_id,
            use_inspect_judge=use_inspect_judge,
        )
        metrics_p = (
            _fill_agg(
                agg_p,
                ep_p,
                task,
                hier_policy=hier_policy,
                inspect_by_id=inspect_by_id,
                use_inspect_judge=use_inspect_judge,
            )
            if ep_p is not None
            else None
        )
        row: Dict[str, Any] = {
            "task_idx": ti,
            "query": task.query,
            "doc_id": task.doc_id,
            "task_type": task.task_type,
            "doc_line_count": strat["doc_line_count"],
            "gold_level_primary": strat["gold_level_primary"],
            "doc_lines_bucket": strat["doc_lines_bucket"],
            "gold_level_bucket": strat["gold_level_bucket"],
            "gold_nodes": task.gold_nodes,
            "gold_answer": task.gold_answer,
            "inspect_id": getattr(task, "inspect_id", None),
            "hierarchical_gold": {
                "evidence_chars_actual": ep_g.evidence_chars_actual,
                "evidence_text": ep_g.evidence_text,
                "composed_answer": ep_g.composed_answer,
                "trajectory_length": ep_g.trajectory_length,
                "truncated_last": ep_g.truncated_last,
                "section_ids": ep_g.section_ids,
                "retrieved_nodes": ep_g.retrieved_nodes,
                "refusal_events": list(ep_g.refusal_events),
                "metrics": metrics_g,
                "steps": [s.__dict__ for s in ep_g.steps],
            },
            "flat": {
                "evidence_chars_actual": ep_f.evidence_chars_actual,
                "evidence_text": ep_f.evidence_text,
                "composed_answer": ep_f.composed_answer,
                "trajectory_length": ep_f.trajectory_length,
                "truncated_last": ep_f.truncated_last,
                "retrieved_nodes": ep_f.retrieved_nodes,
                "metrics": metrics_f,
                "steps": [s.__dict__ for s in ep_f.steps],
            },
        }
        if ep_p is not None:
            row["hierarchical_pred"] = {
                "evidence_chars_actual": ep_p.evidence_chars_actual,
                "evidence_text": ep_p.evidence_text,
                "composed_answer": ep_p.composed_answer,
                "trajectory_length": ep_p.trajectory_length,
                "truncated_last": ep_p.truncated_last,
                "section_ids": ep_p.section_ids,
                "retrieved_nodes": ep_p.retrieved_nodes,
                "refusal_events": list(ep_p.refusal_events),
                "metrics": metrics_p,
                "steps": [s.__dict__ for s in ep_p.steps],
            }
        rows.append(row)
    return agg_g, agg_p, agg_f, rows


def _delta_numeric(sum_g: Dict[str, Any], sum_f: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "evidence_chars_actual_mean",
        "trajectory_length_mean",
        "refusal_recovery_rate",
        "task_success_semantic_mean",
        "task_success_approx_keyword_recall_mean",
        "chunk_hit@1_mean",
        "mrr_chunks_mean",
        "coverage_budget_lenient_mean",
        "precision@1_mean",
        "precision@5_mean",
        "coverage_line_mean",
    ]
    out: Dict[str, Any] = {}
    for k in keys:
        a, b = sum_g.get(k), sum_f.get(k)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            out[k] = float(a) - float(b)
    return out


def _build_summary(
    agg_g: Dict[str, List[float]],
    agg_p: Dict[str, List[float]],
    agg_f: Dict[str, List[float]],
    rows: List[Dict[str, Any]],
    config: Dict[str, Any],
    pred_enabled: bool,
) -> Dict[str, Any]:
    sum_g = _agg_summary(agg_g)
    sum_f = _agg_summary(agg_f)
    summary: Dict[str, Any] = {
        "experiment": "bodyrich_gold_flat" if not pred_enabled else "bodyrich_gold_pred_flat",
        "n_tasks": len(rows),
        "config": config,
        "hierarchical_gold": sum_g,
        "flat": sum_f,
        "delta_gold_minus_flat": _delta_numeric(sum_g, sum_f),
        "per_type_hierarchical_gold": _per_type_summary(rows, "hierarchical_gold"),
        "per_type_flat": _per_type_summary(rows, "flat"),
    }
    if pred_enabled:
        sum_p = _agg_summary(agg_p)
        summary["hierarchical_pred"] = sum_p
        summary["delta_pred_minus_flat"] = _delta_numeric(sum_p, sum_f)
        summary["per_type_hierarchical_pred"] = _per_type_summary(rows, "hierarchical_pred")

    def _refusal_recovery_rate(system_key: str) -> Optional[float]:
        with_refusal = 0
        recovered = 0
        for r in rows:
            sd = r.get(system_key) or {}
            ev = sd.get("refusal_events") or []
            if not ev:
                continue
            with_refusal += 1
            m = sd.get("metrics") or {}
            ts = m.get("task_success")
            ok = ts is not None and float(ts) >= 0.34
            if ok:
                recovered += 1
        return recovered / with_refusal if with_refusal else None

    if config.get("hier_policy") == "toolspace":
        summary["hierarchical_gold"]["refusal_recovery_rate"] = _refusal_recovery_rate(
            "hierarchical_gold"
        )
        if pred_enabled:
            summary["hierarchical_pred"]["refusal_recovery_rate"] = _refusal_recovery_rate(
                "hierarchical_pred"
            )
    return summary


def _judge_label_from_rows(
    *,
    use_inspect_judge: bool,
    rows: Sequence[Dict[str, Any]],
) -> str:
    """根据逐题元数据标记真实判分口径。"""
    if not use_inspect_judge:
        return "semantic_llm"
    inspect_expected = 0
    inspect_used = 0
    for row in rows:
        for arm in ("hierarchical_gold", "flat", "hierarchical_pred"):
            arm_obj = row.get(arm)
            if not isinstance(arm_obj, dict):
                continue
            if "inspect_judge_used" in arm_obj:
                used_flag = arm_obj.get("inspect_judge_used")
            else:
                metrics = arm_obj.get("metrics")
                if not isinstance(metrics, dict) or "inspect_judge_used" not in metrics:
                    continue
                used_flag = metrics.get("inspect_judge_used")
            if used_flag is None:
                continue
            inspect_expected += 1
            if bool(used_flag):
                inspect_used += 1
    if inspect_expected > 0 and inspect_used == inspect_expected:
        return "inspect_delivery_strict"
    return "inspect_delivery+semantic_fallback"


def run_bodyrich_experiment(
    *,
    test_jsonl: Path,
    tasks_jsonl: Path,
    pred_jsonl: Optional[Path] = None,
    retrieval: str = "dense",
    embedding_model: str = DEFAULT_DENSE_EMBEDDING_MODEL,
    max_docs: int = 0,
    max_tasks: int = 0,
    budget_chars: int = 500,
    route_m: int = 2,
    hier_policy: str = "fixed",
    inspect_judge: bool = False,
    inspect_tasks_paths: Optional[List[Path]] = None,
) -> Dict[str, Any]:
    """统一入口：Gold vs Flat-ReAct（默认），或 Gold / Pred / Flat-ReAct 三联（提供 pred_jsonl 时）。"""
    _configure_bodyrich_task_judge()
    tasks = _load_tasks(tasks_jsonl)
    if max_tasks > 0:
        tasks = tasks[:max_tasks]

    # default_inspect_task_paths：datasets/realdata/… 在 bodyrich_delivery_kit 根下（与 delivery/ 并列）
    kit_root = Path(__file__).resolve().parents[4]
    use_inspect_judge = bool(inspect_judge)
    inspect_paths_resolved: List[Path] = []
    if use_inspect_judge:
        paths = inspect_tasks_paths if inspect_tasks_paths else default_inspect_task_paths(kit_root)
    else:
        paths = default_inspect_task_paths(kit_root)
    inspect_paths_resolved = [p for p in paths if p.exists()]
    inspect_by_id = load_inspect_registry(inspect_paths_resolved) if inspect_paths_resolved else None
    _require_inspect_registry_for_judge(
        use_inspect_judge=use_inspect_judge,
        inspect_by_id=inspect_by_id,
        inspect_paths_resolved=inspect_paths_resolved,
        kit_root=kit_root,
        tasks=tasks,
    )

    bundles_g = bundles_from_paths(test_jsonl, tree_source="gold", pred_path=None, max_docs=max_docs)
    _validate_task_gold_nodes_in_corpus(
        tasks,
        bundles_g,
        context=f"run_bodyrich_experiment(test_jsonl={test_jsonl}, tasks={tasks_jsonl})",
    )
    bundles_f = bundles_from_paths(test_jsonl, tree_source="flat", pred_path=None, max_docs=max_docs)
    idx_g = CorpusIndex.from_bundles(
        bundles_g, tree_mode="hierarchical", retrieval_backend=retrieval, embedding_model=embedding_model
    )
    idx_f = CorpusIndex.from_bundles(
        bundles_f, tree_mode="flat", retrieval_backend=retrieval, embedding_model=embedding_model
    )
    tools_g = HierarchicalTools(idx_g)
    tools_f = HierarchicalTools(idx_f)

    pred_enabled = bool(pred_jsonl) and pred_jsonl.exists()  # type: ignore[union-attr]
    tools_p: Optional[HierarchicalTools] = None
    if pred_enabled:
        bundles_p = bundles_from_paths(
            test_jsonl, tree_source="pred", pred_path=pred_jsonl, max_docs=max_docs
        )
        idx_p = CorpusIndex.from_bundles(
            bundles_p,
            tree_mode="hierarchical",
            retrieval_backend=retrieval,
            embedding_model=embedding_model,
        )
        tools_p = HierarchicalTools(idx_p)

    agg_g, agg_p, agg_f, rows = _run_episodes_for_budget(
        tools_g,
        tools_f,
        tools_p,
        tasks,
        budget_chars,
        route_m,
        pred_enabled,
        hier_policy,
        inspect_by_id=inspect_by_id,
        use_inspect_judge=use_inspect_judge,
    )
    judge_label = _judge_label_from_rows(
        use_inspect_judge=use_inspect_judge,
        rows=rows,
    )
    config = {
        "test_jsonl": str(test_jsonl),
        "tasks": str(tasks_jsonl),
        "pred_jsonl": str(pred_jsonl) if pred_jsonl else None,
        "pred_enabled": pred_enabled,
        "retrieval": retrieval,
        "embedding_model": embedding_model if retrieval == "dense" else None,
        "max_docs": max_docs,
        "max_tasks": max_tasks,
        "budget_chars": budget_chars,
        "route_m": route_m,
        "hier_policy": hier_policy,
        "flat_policy": "flat_react",
        "flat_react_search_rounds": int(os.environ.get("FLAT_REACT_SEARCH_ROUNDS", "3").strip() or "3"),
        "protocol": "plan_md_P1_to_P8_budget_eval",
        "judge_semantic_primary": True,
        "inspect_judge": use_inspect_judge,
        "inspect_task_files": [str(p) for p in inspect_paths_resolved],
        "inspect_registry_size": len(inspect_by_id or {}),
        "task_success_judge": judge_label,
    }
    summary = _build_summary(agg_g, agg_p, agg_f, rows, config, pred_enabled)
    return {"summary": summary, "rows": rows}


def run_bodyrich_experiment_multi_budget(
    *,
    test_jsonl: Path,
    tasks_jsonl: Path,
    out_template: str,
    budgets: List[int],
    pred_jsonl: Optional[Path] = None,
    retrieval: str = "dense",
    embedding_model: str = DEFAULT_DENSE_EMBEDDING_MODEL,
    max_docs: int = 0,
    max_tasks: int = 0,
    route_m: int = 2,
    hier_policy: str = "fixed",
    inspect_judge: bool = False,
    inspect_tasks_paths: Optional[List[Path]] = None,
) -> List[Path]:
    """一次编码/索引，顺序跑多个 budget。out_template 必须含 '{budget}'。"""
    _configure_bodyrich_task_judge()
    if "{budget}" not in out_template:
        raise ValueError("out_template 必须包含 '{budget}' 占位符")
    tasks = _load_tasks(tasks_jsonl)
    if max_tasks > 0:
        tasks = tasks[:max_tasks]

    kit_root = Path(__file__).resolve().parents[4]
    use_inspect_judge = bool(inspect_judge)
    inspect_paths_resolved: List[Path] = []
    if use_inspect_judge:
        paths = inspect_tasks_paths if inspect_tasks_paths else default_inspect_task_paths(kit_root)
    else:
        paths = default_inspect_task_paths(kit_root)
    inspect_paths_resolved = [p for p in paths if p.exists()]
    inspect_by_id = load_inspect_registry(inspect_paths_resolved) if inspect_paths_resolved else None
    _require_inspect_registry_for_judge(
        use_inspect_judge=use_inspect_judge,
        inspect_by_id=inspect_by_id,
        inspect_paths_resolved=inspect_paths_resolved,
        kit_root=kit_root,
        tasks=tasks,
    )

    bundles_g = bundles_from_paths(test_jsonl, tree_source="gold", pred_path=None, max_docs=max_docs)
    _validate_task_gold_nodes_in_corpus(
        tasks,
        bundles_g,
        context=f"run_bodyrich_experiment_multi_budget(test_jsonl={test_jsonl}, tasks={tasks_jsonl})",
    )
    bundles_f = bundles_from_paths(test_jsonl, tree_source="flat", pred_path=None, max_docs=max_docs)
    idx_g = CorpusIndex.from_bundles(
        bundles_g, tree_mode="hierarchical", retrieval_backend=retrieval, embedding_model=embedding_model
    )
    idx_f = CorpusIndex.from_bundles(
        bundles_f, tree_mode="flat", retrieval_backend=retrieval, embedding_model=embedding_model
    )
    tools_g = HierarchicalTools(idx_g)
    tools_f = HierarchicalTools(idx_f)

    pred_enabled = bool(pred_jsonl) and pred_jsonl.exists()  # type: ignore[union-attr]
    tools_p: Optional[HierarchicalTools] = None
    if pred_enabled:
        bundles_p = bundles_from_paths(
            test_jsonl, tree_source="pred", pred_path=pred_jsonl, max_docs=max_docs
        )
        idx_p = CorpusIndex.from_bundles(
            bundles_p,
            tree_mode="hierarchical",
            retrieval_backend=retrieval,
            embedding_model=embedding_model,
        )
        tools_p = HierarchicalTools(idx_p)

    saved: List[Path] = []
    for budget_chars in budgets:
        out_path = Path(out_template.format(budget=budget_chars))
        print(f"[multi-budget] running budget={budget_chars} -> {out_path}", file=sys.stderr, flush=True)
        agg_g, agg_p, agg_f, rows = _run_episodes_for_budget(
            tools_g,
            tools_f,
            tools_p,
            tasks,
            budget_chars,
            route_m,
            pred_enabled,
            hier_policy,
            inspect_by_id=inspect_by_id,
            use_inspect_judge=use_inspect_judge,
        )
        judge_label = _judge_label_from_rows(
            use_inspect_judge=use_inspect_judge,
            rows=rows,
        )
        config = {
            "test_jsonl": str(test_jsonl),
            "tasks": str(tasks_jsonl),
            "pred_jsonl": str(pred_jsonl) if pred_jsonl else None,
            "pred_enabled": pred_enabled,
            "retrieval": retrieval,
            "embedding_model": embedding_model if retrieval == "dense" else None,
            "max_docs": max_docs,
            "max_tasks": max_tasks,
            "budget_chars": budget_chars,
            "route_m": route_m,
            "hier_policy": hier_policy,
            "flat_policy": "flat_react",
            "flat_react_search_rounds": int(os.environ.get("FLAT_REACT_SEARCH_ROUNDS", "3").strip() or "3"),
            "protocol": "plan_md_P1_to_P8_budget_eval",
            "judge_semantic_primary": True,
            "inspect_judge": use_inspect_judge,
            "inspect_task_files": [str(p) for p in inspect_paths_resolved],
            "inspect_registry_size": len(inspect_by_id or {}),
            "task_success_judge": judge_label,
        }
        summary = _build_summary(agg_g, agg_p, agg_f, rows, config, pred_enabled)
        payload = {"summary": summary, "rows": rows}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[multi-budget] saved: {out_path}", file=sys.stderr, flush=True)
        saved.append(out_path)
    return saved


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Body-rich Gold vs Flat-ReAct (pred optional) main experiment (plan §P1-P8)"
    )
    p.add_argument("--test_jsonl", type=Path, required=True)
    p.add_argument("--tasks", type=Path, required=True)
    p.add_argument("--out", type=Path, required=False, default=None,
                   help="单 budget 模式输出；多 budget 模式忽略（走 --out-template）")
    p.add_argument(
        "--pred_jsonl",
        type=Path,
        default=None,
        help="可选；提供时跑 Gold/Pred/Flat-ReAct 三联，缺省只跑 Gold vs Flat-ReAct",
    )
    p.add_argument("--retrieval", choices=("dense",), default="dense")
    p.add_argument(
        "--embedding-model",
        default=None,
        metavar="MODEL",
        help=f"默认 None=环境变量或内置 DEFAULT（当前 {DEFAULT_DENSE_EMBEDDING_MODEL}）",
    )
    p.add_argument("--max-docs", type=int, default=0)
    p.add_argument("--max-tasks", type=int, default=0)
    p.add_argument("--budget-chars", type=int, default=500, help="plan §P4/P5 headline=500")
    p.add_argument(
        "--budget-chars-list",
        default=None,
        help="可选；逗号分隔多个 budget（如 '300,500,1000'），搭配 --out-template 在同一进程内顺序评估，复用一次索引/编码",
    )
    p.add_argument(
        "--out-template",
        default=None,
        help="多 budget 模式输出文件模板，必须含 '{budget}'，如 'results/bodyrich/arxiv/arxiv_goldflat_dense_b{budget}.json'",
    )
    p.add_argument("--route-m", type=int, default=2)
    p.add_argument(
        "--hier-policy",
        choices=("fixed", "toolspace", "compact"),
        default="toolspace",
        help="hierarchical 分支：toolspace=agent 自主 map/structure/read/search；fixed/compact 为兼容路径，均不再按 route_m 预裁剪 LEVEL 1",
    )
    p.add_argument(
        "--inspect-judge",
        action="store_true",
        help="按 Inspect 任务库（id/input/target/metadata）对带 inspect_id 的题目阅卷；task_success=content_score，并输出 inspect_evidence_mean",
    )
    p.add_argument(
        "--inspect-tasks",
        dest="inspect_tasks",
        action="append",
        type=Path,
        default=None,
        metavar="PATH",
        help="Inspect 格式 JSONL，可多次传入；缺省使用 kit 内 datasets/realdata 下若干 *_inspect.jsonl",
    )
    p.add_argument(
        "--task-outputs-jsonl",
        type=Path,
        default=None,
        help="可选；把每个 task 的关键输出另存为 JSONL（单 budget）。",
    )
    p.add_argument(
        "--task-outputs-template",
        default=None,
        help="可选；多 budget 模式下每个 budget 的 task 输出 JSONL 模板，需含 '{budget}'。",
    )
    return p


def _write_task_outputs_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            out: Dict[str, Any] = {
                "task_idx": r.get("task_idx"),
                "doc_id": r.get("doc_id"),
                "query": r.get("query"),
                "task_type": r.get("task_type"),
                "inspect_id": r.get("inspect_id"),
                "hierarchical_gold": r.get("hierarchical_gold"),
                "hierarchical_pred": r.get("hierarchical_pred"),
                "flat": r.get("flat"),
            }
            f.write(json.dumps(out, ensure_ascii=False) + "\n")


def main(argv: Optional[List[str]] = None) -> None:
    args = _build_argparser().parse_args(argv)
    embedding_model = resolve_embedding_model(args.embedding_model)
    pred_path = args.pred_jsonl if (args.pred_jsonl and args.pred_jsonl.exists()) else None
    if args.budget_chars_list:
        if not args.out_template:
            raise SystemExit("--budget-chars-list 必须搭配 --out-template（含 '{budget}'）")
        if args.task_outputs_template and "{budget}" not in args.task_outputs_template:
            raise SystemExit("--task-outputs-template 必须包含 '{budget}' 占位符")
        budgets = [int(x.strip()) for x in args.budget_chars_list.split(",") if x.strip()]
        saved = run_bodyrich_experiment_multi_budget(
            test_jsonl=args.test_jsonl,
            tasks_jsonl=args.tasks,
            out_template=args.out_template,
            budgets=budgets,
            pred_jsonl=pred_path,
            retrieval=args.retrieval,
            embedding_model=embedding_model,
            max_docs=args.max_docs,
            max_tasks=args.max_tasks,
            route_m=args.route_m,
            hier_policy=args.hier_policy,
            inspect_judge=bool(args.inspect_judge),
            inspect_tasks_paths=list(args.inspect_tasks) if args.inspect_tasks else None,
        )
        for p in saved:
            print(f"saved: {p}", file=sys.stderr)
            if args.task_outputs_template:
                try:
                    payload_i = json.loads(Path(p).read_text(encoding="utf-8"))
                    rows_i = payload_i.get("rows") if isinstance(payload_i, dict) else None
                    if isinstance(rows_i, list):
                        m = re.search(r"_b(\d+)\.json$", str(p))
                        b = m.group(1) if m else "unknown"
                        out_i = Path(args.task_outputs_template.format(budget=b))
                        _write_task_outputs_jsonl(out_i, rows_i)
                        print(f"saved: {out_i}", file=sys.stderr)
                except Exception as e:
                    print(f"[warn] task outputs export failed for {p}: {e}", file=sys.stderr)
        return
    if args.out is None:
        raise SystemExit("单 budget 模式必须提供 --out")
    payload = run_bodyrich_experiment(
        test_jsonl=args.test_jsonl,
        tasks_jsonl=args.tasks,
        pred_jsonl=pred_path,
        retrieval=args.retrieval,
        embedding_model=embedding_model,
        max_docs=args.max_docs,
        max_tasks=args.max_tasks,
        budget_chars=args.budget_chars,
        route_m=args.route_m,
        hier_policy=args.hier_policy,
        inspect_judge=bool(args.inspect_judge),
        inspect_tasks_paths=list(args.inspect_tasks) if args.inspect_tasks else None,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    if args.task_outputs_jsonl:
        _write_task_outputs_jsonl(args.task_outputs_jsonl, payload.get("rows", []))
        print(f"saved: {args.task_outputs_jsonl}", file=sys.stderr)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"saved: {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
