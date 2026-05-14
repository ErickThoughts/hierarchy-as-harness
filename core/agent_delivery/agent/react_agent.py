"""
Plan §3.4 / §5.3：Tool-space + 多步工具调用（ReAct 风格 episode）。

默认策略为 **确定性**（无 LLM API，可完全离线复现），与固定管线共享同一套
`evaluate_at_budget` 预算合并，便于和 `run_bodyrich_episode` 对照。

若 `TOOLSPACE_USE_LLM=1`：工具步由 `_llm_next_tool`（OpenAI 兼容 API）驱动；任一规划/解析/API
失败即抛错，不再接「确定性工具链尾段」补齐。`TOOLSPACE_USE_LLM=0` 时仍为纯确定性工具序列。
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .types import AgentStep, EpisodeResult
from ..code.budget_eval import evaluate_at_budget
from ..code.compose_llm import compose_answer_llm
from ..code.hierarchical_tools import HierarchicalTools, ToolHit
from ..code.index_retrieval import Chunk
from ..code.llm_config import load_llm_env
from ..code.tool_space import Refusal, ToolSpace

load_llm_env()


def _toolspace_tail_search_k(task_type: str) -> int:
    """toolspace 末尾全局 search 的 k：multi/scope 默认更大以抬证据召回。"""
    tt = (task_type or "").lower()
    if tt == "multi_hop":
        return max(8, min(72, int(os.environ.get("TOOLSPACE_TAIL_SEARCH_K_MULTI", "44") or "44")))
    if tt in ("scope_collection", "regulatory_coverage"):
        return max(8, min(72, int(os.environ.get("TOOLSPACE_TAIL_SEARCH_K_SCOPE", "40") or "40")))
    return max(8, min(64, int(os.environ.get("TOOLSPACE_TAIL_SEARCH_K_DEFAULT", "28") or "28")))


def _chunks_to_retrieved_nodes(chunks: List[Chunk]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for c in chunks:
        for lid in c.line_ids:
            node = f"{c.doc_id}:L{lid}"
            if node not in seen:
                seen.add(node)
                out.append(node)
    return out


def _dedupe_scored(hits: List[ToolHit]) -> List[Tuple[Chunk, float]]:
    best: Dict[str, Tuple[Chunk, float]] = {}
    for h in hits:
        cid = h.chunk.node_id
        if cid not in best or h.score > best[cid][1]:
            best[cid] = (h.chunk, h.score)
    out = list(best.values())
    out.sort(key=lambda x: -x[1])
    return out


def _read_priority_hits(hits: List[ToolHit]) -> List[ToolHit]:
    """Promote chunks explicitly selected by read_chunks over background search hits."""
    bonus = float(os.environ.get("TOOLSPACE_READ_CHUNK_SCORE_BONUS", "10.0").strip() or "10.0")
    return [ToolHit(chunk=h.chunk, score=float(h.score) + bonus) for h in hits]


def _hits_observation(label: str, hits: List[ToolHit], *, max_hits: int = 8) -> str:
    lines = [f"{label} n_hits={len(hits)}"]
    for h in hits[:max_hits]:
        txt = (h.chunk.text or "").replace("\n", " ")[:180]
        lines.append(f"- {h.chunk.node_id} score={float(h.score):.4f} :: {txt}")
    return "\n".join(lines)


def _extract_json_obj(text: str) -> Optional[Dict[str, Any]]:
    s = (text or "").strip().replace("```json", "").replace("```", "")
    if not s:
        return None
    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass
    # 提取首个“括号平衡”的 JSON 对象，容忍对象后多余文本（如 "}]..."）。
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escaped = False
    end = -1
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None
    try:
        obj = json.loads(s[start : end + 1])
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _extract_partial_decision(text: str) -> Optional[Dict[str, Any]]:
    """
    当模型输出被截断导致 JSON 未闭合时，尽量提取最小可执行动作。
    仍保持 LLM 驱动，不回退到确定性规划。
    """
    s = (text or "").strip()
    if not s:
        return None
    m_action = re.search(r'"action"\s*:\s*"([^"]+)"', s)
    if not m_action:
        return None
    action = m_action.group(1).strip().lower()
    if not action:
        return None
    out: Dict[str, Any] = {"action": action}
    if action == "search":
        m_kw = re.search(r'"keywords"\s*:\s*"([^"]*)"', s)
        if m_kw:
            out["keywords"] = m_kw.group(1)
        m_k = re.search(r'"k"\s*:\s*(\d+)', s)
        if m_k:
            try:
                out["k"] = int(m_k.group(1))
            except Exception:
                pass
    elif action == "discover_files":
        m_kw = re.search(r'"keywords"\s*:\s*"([^"]*)"', s)
        if m_kw:
            out["keywords"] = m_kw.group(1)
    elif action == "get_structure":
        m_sid = re.search(r'"section_id"\s*:\s*"([^"]*)"', s)
        if m_sid:
            out["section_id"] = m_sid.group(1)
    elif action == "read_chunks":
        # 截断场景下 section_path 经常超长，先取首段，后续逻辑会再规范化。
        m_sp = re.search(r'"section_path"\s*:\s*"([^"]*)"', s)
        if m_sp:
            out["section_path"] = m_sp.group(1).split(",")[0].strip()
        m_kw = re.search(r'"keywords"\s*:\s*"([^"]*)"', s)
        if m_kw:
            out["keywords"] = m_kw.group(1)
    elif action == "finish":
        m_reason = re.search(r'"reason"\s*:\s*"([^"]*)"', s)
        if m_reason:
            out["reason"] = m_reason.group(1)
    return out


def _llm_next_tool(
    query: str,
    *,
    doc_id: str,
    steps: List[AgentStep],
    last_observation: str,
) -> Dict[str, Any]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("TOOLSPACE_USE_LLM=1 但缺少 OPENAI_API_KEY（请配置 llm_api.env 或环境变量）。")
    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError("TOOLSPACE ReAct 需要安装 openai 包。") from e

    base = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = os.environ.get("TOOLSPACE_MODEL", os.environ.get("COMPOSE_MODEL", "gpt-4o-mini")).strip()
    client = OpenAI(api_key=key, base_url=base)
    trace = "\n".join(
        f"- {s.step_idx}:{s.action} {json.dumps(s.detail, ensure_ascii=False)[:180]}"
        for s in steps[-6:]
    )
    prompt = (
        "你是 ReAct 工具规划器。只能输出一个 JSON 对象，不要 markdown。\n"
        "可选 action: get_map, get_structure, read_chunks, discover_files, search, finish。\n"
        "根据 get_map / get_structure / search 的观察自主选择要查看的 section_path；"
        "系统不会预先按 query 截断 LEVEL 1 section。你需要自己决定查看哪些顶层 section、"
        "哪些子 section，以及何时转入 read_chunks 或 search。section_path 可以是顶层 section，"
        "也可以是 get_structure 返回的子 section。不要输出 line id 列表、不要逗号拼接多个路径、不要长字符串。\n"
        "JSON schema:\n"
        '{"action":"read_chunks","section_path":"...","keywords":"..."} 或 '
        '{"action":"search","keywords":"...","k":28} 或 '
        '{"action":"get_structure","section_id":"..."} 或 '
        '{"action":"get_map"} 或 {"action":"discover_files","keywords":"..."} 或 '
        '{"action":"finish","reason":"..."}'
    )
    user = (
        f"query={query}\n"
        f"doc_id={doc_id}\n"
        f"recent_steps:\n{trace or '(none)'}\n"
        f"last_observation:\n{last_observation[:6000]}"
    )
    last_err: Optional[Exception] = None
    rsp = None
    for i in range(3):
        try:
            # 先要求服务端按 JSON object 输出；若网关不支持该参数，再降级为普通调用（仍做本地严格 JSON 解析）。
            rsp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=320,
            )
            break
        except Exception:
            try:
                rsp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user}],
                    temperature=0.1,
                    max_tokens=320,
                )
                break
            except Exception as e:
                last_err = e
                if i < 2:
                    time.sleep(0.6 * (i + 1))
                continue
    if rsp is None:
        raise RuntimeError(f"TOOLSPACE ReAct LLM 调用失败: {last_err}") from last_err
    txt = (rsp.choices[0].message.content or "").strip()
    obj = _extract_json_obj(txt)
    if not isinstance(obj, dict):
        obj = _extract_partial_decision(txt)
    if not isinstance(obj, dict):
        raise RuntimeError(
            "TOOLSPACE ReAct：模型返回无法解析为 JSON 对象，已禁止回退到确定性规划。"
            f" model={model!r} preview={txt[:320]!r}"
        )
    return obj


def run_toolspace_episode(
    tools: HierarchicalTools,
    query: str,
    *,
    doc_id: str,
    budget_chars: int,
    route_m: int = 2,
    step_budget: int = 10,
    task_type: str = "niche_fact",
    compose_format_constraints: str = "",
) -> EpisodeResult:
    """
    在单文档上执行至多 step_budget 次「工具观测」+ 最终 compose（预算填充）。

    工具序列：
      get_map 先暴露完整 top-level map；LLM-ReAct 路径由模型自主
      get_structure/read_chunks/search/finish。正式路径不再预先 route/cap LEVEL 1 section。
    refusal 出现时按 plan 语义收窄重试一次（记入 refusal_events）。
    step_budget 默认 10，为 probe + 多节 read 留余量。
    """
    if not doc_id:
        raise ValueError("toolspace episode 需要非空 doc_id")

    ts = ToolSpace(tools)
    steps: List[AgentStep] = []
    refusal_events: List[Dict[str, object]] = []
    hits_acc: List[ToolHit] = []
    last_observation = ""

    # Agentic flow: expose the full top-level map first, then let the agent
    # decide which top-level and child sections to inspect.
    section_ids = ts.sections_for_doc(doc_id)
    mtxt = ts.get_map(doc_id)
    last_observation = mtxt
    steps.append(
        AgentStep(
            step_idx=len(steps) + 1,
            action="get_map",
            detail={
                "mode": "agent_decides",
                "route_m_ignored": route_m,
                "chars": len(mtxt),
                "n_top_sections": len(section_ids),
            },
        )
    )

    if llm_react_enabled():
        for _ in range(max(0, step_budget - len(steps))):
            if len(steps) >= step_budget:
                break
            decision = _llm_next_tool(
                query,
                doc_id=doc_id,
                steps=steps,
                last_observation=last_observation,
            )
            action = str(decision.get("action") or "").strip().lower()
            if action == "finish":
                steps.append(
                    AgentStep(
                        step_idx=len(steps) + 1,
                        action="react_finish",
                        detail={"reason": str(decision.get("reason") or "")[:120]},
                    )
                )
                break
            if action == "get_map":
                m = ts.get_map(doc_id)
                last_observation = m
                steps.append(
                    AgentStep(
                        step_idx=len(steps) + 1,
                        action="get_map",
                        detail={"chars": len(m), "n_top_sections": len(section_ids)},
                    )
                )
                continue
            if action == "discover_files":
                kws = str(decision.get("keywords") or query).strip()[:96]
                docs = ts.discover_files(kws) if kws else []
                last_observation = f"discover_files n_docs={len(docs)} head={docs[:24]}"
                steps.append(
                    AgentStep(
                        step_idx=len(steps) + 1,
                        action="discover_files",
                        detail={"keywords": kws, "n_docs": len(docs), "head": docs[:8]},
                    )
                )
                continue
            if action == "get_structure":
                sid = str(decision.get("section_id") or "").strip()
                st = ts.get_structure(sid) if sid else {"section_id": "", "exists": False}
                last_observation = json.dumps(st, ensure_ascii=False)[:6000]
                steps.append(AgentStep(step_idx=len(steps) + 1, action="get_structure", detail=st))
                continue
            if action == "search":
                kws = str(decision.get("keywords") or query).strip()
                try:
                    k = int(decision.get("k", 28))
                except Exception:
                    k = 28
                k = max(4, min(64, k))
                sr = ts.search(kws, k, doc_id=doc_id)
                hits_acc.extend(sr)
                last_observation = _hits_observation("search", sr)
                steps.append(
                    AgentStep(step_idx=len(steps) + 1, action="search", detail={"k": k, "n_hits": len(sr)})
                )
                continue
            if action == "read_chunks":
                sid = str(decision.get("section_path") or "").strip()
                kws = str(decision.get("keywords") or query).strip()
                rc = ts.read_chunks(sid, kws, doc_id=doc_id)
                if isinstance(rc, Refusal):
                    refusal_events.append(
                        {
                            "tool": "read_chunks",
                            "section_path": sid,
                            "status": rc.status,
                            "message": rc.message,
                            "available_sections": list(rc.available_sections),
                        }
                    )
                    last_observation = f"read_chunks refusal={rc.status} available={rc.available_sections[:4]}"
                    steps.append(
                        AgentStep(
                            step_idx=len(steps) + 1,
                            action="read_chunks",
                            detail={"section_path": sid, "refusal": rc.status},
                        )
                    )
                else:
                    hits_acc.extend(_read_priority_hits(rc))
                    last_observation = _hits_observation("read_chunks", rc)
                    steps.append(
                        AgentStep(
                            step_idx=len(steps) + 1,
                            action="read_chunks",
                            detail={"section_path": sid, "n_hits": len(rc)},
                        )
                    )
                continue
            raise RuntimeError(
                f"TOOLSPACE ReAct：未知 action={action!r}，已禁止回退到确定性工具链。"
            )

    if not llm_react_enabled() and len(steps) < step_budget:
        rc_probe = ts.read_chunks("", query, doc_id=doc_id)
        if isinstance(rc_probe, Refusal):
            refusal_events.append(
                {
                    "tool": "read_chunks",
                    "section_path": "",
                    "status": rc_probe.status,
                    "message": rc_probe.message,
                    "available_sections": list(rc_probe.available_sections),
                }
            )
            steps.append(
                AgentStep(
                    step_idx=len(steps) + 1,
                    action="read_chunks_probe",
                    detail={"section_path": "", "refusal": rc_probe.status},
                )
            )
        else:
            hits_acc.extend(_read_priority_hits(rc_probe[: min(24, len(rc_probe))]))
            steps.append(
                AgentStep(
                    step_idx=len(steps) + 1,
                    action="read_chunks_probe",
                    detail={"section_path": "", "n_hits": len(rc_probe)},
                )
            )

    if not llm_react_enabled() and len(steps) < step_budget:
        qpeek = (query or "").strip()[:96]
        doc_hits = ts.discover_files(qpeek) if qpeek else []
        steps.append(
            AgentStep(
                step_idx=len(steps) + 1,
                action="discover_files",
                detail={"keywords": qpeek, "n_docs": len(doc_hits), "head": doc_hits[:8]},
            )
        )

    if not llm_react_enabled():
        selected_sections: List[str] = list(section_ids)
        steps.append(
            AgentStep(
                step_idx=len(steps) + 1,
                action="select_sections",
                detail={
                    "mode": "deterministic_all_top_sections",
                    "route_m_ignored": route_m,
                    "n_sections": len(selected_sections),
                },
            )
        )
        if selected_sections:
            st0 = ts.get_structure(selected_sections[0])
            steps.append(
                AgentStep(
                    step_idx=len(steps) + 1,
                    action="get_structure",
                    detail=st0,
                )
            )

        for sid in selected_sections[:4]:
            if len(steps) >= step_budget:
                break
            rc: Union[List[ToolHit], Refusal] = ts.read_chunks(sid, query, doc_id=doc_id)
            if isinstance(rc, Refusal):
                refusal_events.append(
                    {
                        "tool": "read_chunks",
                        "section_path": sid,
                        "status": rc.status,
                        "message": rc.message,
                        "available_sections": list(rc.available_sections),
                    }
                )
                steps.append(
                    AgentStep(
                        step_idx=len(steps) + 1,
                        action="read_chunks",
                        detail={"section_path": sid, "refusal": rc.status},
                    )
                )
                if rc.status == "no_match" and rc.available_sections:
                    sid2 = rc.available_sections[0]
                    rc2 = ts.read_chunks(sid2, query, doc_id=doc_id)
                    if not isinstance(rc2, Refusal):
                        hits_acc.extend(_read_priority_hits(rc2))
                        steps.append(
                            AgentStep(
                                step_idx=len(steps) + 1,
                                action="read_chunks_retry",
                                detail={"section_path": sid2, "n_hits": len(rc2)},
                            )
                        )
                elif rc.status == "too_many" and section_ids:
                    sid2 = section_ids[0]
                    rc2 = ts.read_chunks(sid2, query, doc_id=doc_id)
                    if not isinstance(rc2, Refusal):
                        hits_acc.extend(_read_priority_hits(rc2))
                        steps.append(
                            AgentStep(
                                step_idx=len(steps) + 1,
                                action="read_chunks_retry",
                                detail={"section_path": sid2, "n_hits": len(rc2)},
                            )
                        )
            else:
                hits_acc.extend(_read_priority_hits(rc))
                steps.append(
                    AgentStep(
                        step_idx=len(steps) + 1,
                        action="read_chunks",
                        detail={"section_path": sid, "n_hits": len(rc)},
                    )
                )

    if not llm_react_enabled() and len(steps) < step_budget:
        k_tail = _toolspace_tail_search_k(task_type)
        sr = ts.search(query, k_tail, doc_id=doc_id)
        hits_acc.extend(sr)
        steps.append(
            AgentStep(
                step_idx=len(steps) + 1,
                action="search",
                detail={"k": k_tail, "n_hits": len(sr)},
            )
        )

    scored = _dedupe_scored(hits_acc)
    fill = evaluate_at_budget(scored, budget_chars=budget_chars)

    ev = (fill.evidence_text or "")[: max(1, int(budget_chars))]
    max_ans = min(1024, max(256, int(budget_chars)))
    tt = task_type or "niche_fact"
    composed = compose_answer_llm(
        query,
        task_type=tt,
        evidence_text=ev,
        max_answer_chars=max_ans,
        budget_chars=int(budget_chars),
        format_constraints=compose_format_constraints,
    )

    retrieved = _chunks_to_retrieved_nodes(list(fill.kept_chunks))
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
        representation="hierarchical_toolspace",
        steps=steps,
        scored_chunks=scored,
        kept_chunks=fill.kept_chunks,
        evidence_text=fill.evidence_text,
        evidence_chars_actual=fill.evidence_chars_actual,
        retrieved_nodes=retrieved,
        composed_answer=composed,
        section_ids=list(section_ids),
        trajectory_length=len(steps),
        truncated_last=fill.truncated_last,
        refusal_events=refusal_events,
    )


def llm_react_enabled() -> bool:
    return os.environ.get("TOOLSPACE_USE_LLM", "").strip() in ("1", "true", "yes")
