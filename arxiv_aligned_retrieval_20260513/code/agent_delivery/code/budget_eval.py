"""
Budget-Constrained 评估：对齐 plan.md §P1–P8。

- P1: 取消 per-path k 上限。调用方应把全部候选（非截断）传进来。
- P2: 字符级截断——超出预算的最后一块切到 `budget_chars - used`。
- P3: 路由摘要文本不计入预算（调用方负责把 section_summaries 排除在候选之外）。
- P4/P5: budget_chars 由调用方传入（arXiv/realdata 主表 headline=500）。
- P6: 主表 4 列由 runner 汇总；本模块产出 `evidence_chars_actual / n_chunks_kept`。
- P7: 附录诊断指标 `ChunkHit@1 / MRR@chunks / Coverage@budget_lenient` 在本模块产出。
- P8: Lenient 半截行命中——完整 chunk 按其 `line_ids` 计入；截断 chunk 仅按可见前缀估计覆盖到的
  `line_ids` 计入，避免“文本被截断但整块行号全算”。

本模块故意不侵入 `index_retrieval.merge_evidence`，也不依赖 agent loop 结构；
仅消费 `(chunk, score)` 序列 + `budget_chars`，产出保留块列表 + evidence 文本 + 字符数 + 附录指标。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .index_retrieval import Chunk


def _line_overlap_jaccard(a: Chunk, b: Chunk) -> float:
    sa = set(a.line_ids)
    sb = set(b.line_ids)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    uni = len(sa | sb)
    return float(inter) / float(uni) if uni else 0.0


def _max_overlap_to_kept(c: Chunk, kept: Sequence[Chunk]) -> float:
    worst = 0.0
    for kc in kept:
        worst = max(worst, _line_overlap_jaccard(c, kc))
    return worst


@dataclass
class BudgetFillResult:
    kept_chunks: List[Chunk]
    """按 score 降序、去重后，实际被写入 evidence 的 chunk 序列；若有字符级截断，最后一项可能是部分文本。"""

    evidence_text: str
    """拼接后的 evidence（[node_id]\\n<text> 组块，以空行分隔），总长 ≤ budget_chars。"""

    evidence_chars_actual: int
    """`len(evidence_text)`，对应 plan §P6 主表列。"""

    n_chunks_kept: int
    """`len(kept_chunks)`，对应 plan §P6 注释里的 n_chunks_kept。"""

    truncated_last: bool
    """最后一个 chunk 是否被字符级截断（P2）。"""


def _block_for(chunk: Chunk) -> str:
    return f"[{chunk.node_id}]\n{chunk.text or ''}"


def _partial_chunk_for_block(chunk: Chunk, visible_block: str) -> Chunk:
    """
    为字符级截断后的最后一个 evidence block 生成只含可见前缀行号的 Chunk。

    Chunk 当前没有逐行文本 offset 元数据；这里用可见正文长度占比映射到有序 line_ids 前缀。
    对 line chunk 精确等价，对 leaf/path chunk 保守地避免把未进入预算的尾部行号全算进 evidence。
    """
    header = f"[{chunk.node_id}]\n"
    text = chunk.text or ""
    if not chunk.line_ids:
        visible_line_ids: Tuple[int, ...] = ()
    elif not text:
        visible_line_ids = tuple(chunk.line_ids[:1]) if visible_block else ()
    else:
        visible_text_len = max(0, len(visible_block) - len(header))
        if visible_text_len <= 0:
            visible_line_ids = ()
        else:
            ratio = min(1.0, float(visible_text_len) / float(max(1, len(text))))
            n_visible = max(1, min(len(chunk.line_ids), int((len(chunk.line_ids) * ratio) + 0.999999)))
            visible_line_ids = tuple(chunk.line_ids[:n_visible])
    return Chunk(
        node_id=f"{chunk.node_id}__partial",
        doc_id=chunk.doc_id,
        text=visible_block[len(header) :] if visible_block.startswith(header) else visible_block,
        line_ids=visible_line_ids,
        section_id=chunk.section_id,
    )


def evaluate_at_budget(
    scored_chunks: Sequence[Tuple[Chunk, float]],
    budget_chars: int,
    *,
    min_partial_chars: int = 20,
    block_sep: str = "\n\n",
) -> BudgetFillResult:
    """
    plan §P1–P2：对 `scored_chunks` 去重后按 score 降序填充，直到 `budget_chars` 用尽；
    若最后一块放不下就字符级截断到 `budget_chars - used`（至少保留 `min_partial_chars` 才写入）。

    共用增益：`BODYRICH_PACK_LINE_OVERLAP_PENALTY`（默认 0.09）>0 时，在预算内贪心选取 chunk，
    对与已选块 line_ids Jaccard 重叠高的候选降权，减少同质窗口挤占预算；置 0 恢复纯 score 顺序。

    Parameters
    ----------
    scored_chunks : Sequence[Tuple[Chunk, float]]
        候选池，可以无序；本函数自己排序。
    budget_chars : int
        主表预算上限（plan §P4/P5 的 b ∈ {300, 500, 1000}）。

    Returns
    -------
    BudgetFillResult
    """
    if budget_chars <= 0:
        return BudgetFillResult([], "", 0, 0, False)

    ranked = sorted(scored_chunks, key=lambda x: -float(x[1]))
    seen: Dict[str, Tuple[Chunk, float]] = {}
    for c, s in ranked:
        prev = seen.get(c.node_id)
        if prev is None or float(s) > float(prev[1]):
            seen[c.node_id] = (c, float(s))
    uniq_ranked = sorted(seen.values(), key=lambda x: -x[1])

    parts: List[str] = []
    kept: List[Chunk] = []
    used = 0
    sep_len = len(block_sep)
    truncated_last = False

    pack_penalty = float(_env_float("BODYRICH_PACK_LINE_OVERLAP_PENALTY", 0.09))

    if pack_penalty <= 0:
        for c, _score in uniq_ranked:
            block = _block_for(c)
            add_len = len(block) + (sep_len if parts else 0)
            if used + add_len <= budget_chars:
                parts.append(block)
                kept.append(c)
                used += add_len
                if used == budget_chars:
                    break
                continue
            remain = budget_chars - used - (sep_len if parts else 0)
            if remain >= min_partial_chars:
                visible_block = block[:remain]
                parts.append(visible_block)
                kept.append(_partial_chunk_for_block(c, visible_block))
                used = budget_chars
                truncated_last = True
            break
    else:
        candidates = list(uniq_ranked)
        picked: set = set()
        while used < budget_chars:
            best_i: Optional[int] = None
            best_mode: Optional[str] = None
            best_eff = -1e18
            for i, (c, s) in enumerate(candidates):
                if i in picked:
                    continue
                ov = _max_overlap_to_kept(c, kept)
                eff = float(s) - pack_penalty * ov
                block = _block_for(c)
                add_len = len(block) + (sep_len if parts else 0)
                if used + add_len <= budget_chars:
                    if eff > best_eff:
                        best_eff = eff
                        best_i = i
                        best_mode = "full"
                else:
                    remain = budget_chars - used - (sep_len if parts else 0)
                    if remain >= min_partial_chars and eff > best_eff:
                        best_eff = eff
                        best_i = i
                        best_mode = "partial"
            if best_i is None:
                break
            c, _s = candidates[best_i]
            picked.add(best_i)
            block = _block_for(c)
            if best_mode == "full":
                add_len = len(block) + (sep_len if parts else 0)
                parts.append(block)
                kept.append(c)
                used += add_len
                if used >= budget_chars:
                    break
                continue
            remain = budget_chars - used - (sep_len if parts else 0)
            visible_block = block[:remain]
            parts.append(visible_block)
            kept.append(_partial_chunk_for_block(c, visible_block))
            used = budget_chars
            truncated_last = True
            break

    evidence = block_sep.join(parts)
    return BudgetFillResult(
        kept_chunks=kept,
        evidence_text=evidence,
        evidence_chars_actual=len(evidence),
        n_chunks_kept=len(kept),
        truncated_last=truncated_last,
    )


def compute_budget_retrieval_metrics(
    kept_chunks: Sequence[Chunk],
    gold_node_ids: Sequence[str],
) -> Dict[str, float]:
    """
    plan §P7/P8：对 `evaluate_at_budget` 的 `kept_chunks` 计算附录诊断指标。
    - ChunkHit@1: rank=1 的 chunk 的 line_ids 是否与 gold 相交（lenient）
    - MRR@chunks: 第一个命中 chunk 的倒数 rank；无命中返回 0
    - Coverage@budget_lenient: |gold ∩ kept 行集合| / |gold|；gold 空返回 1.0
    """
    gold_set = {str(g) for g in gold_node_ids}
    if not gold_set:
        return {
            "chunk_hit@1": 0.0,
            "mrr_chunks": 0.0,
            "coverage_budget_lenient": 1.0,
            "n_chunks_kept": float(len(kept_chunks)),
        }

    kept_lines: set = set()
    first_hit_rank = 0
    chunk_hit_at_1 = 0.0
    mrr_chunks = 0.0

    for rank, c in enumerate(kept_chunks, start=1):
        chunk_gold_match = False
        for lid in c.line_ids:
            node = f"{c.doc_id}:L{lid}"
            kept_lines.add(node)
            if node in gold_set:
                chunk_gold_match = True
        if chunk_gold_match and first_hit_rank == 0:
            first_hit_rank = rank
            mrr_chunks = 1.0 / float(rank)
            if rank == 1:
                chunk_hit_at_1 = 1.0

    coverage = len(kept_lines & gold_set) / float(len(gold_set))
    return {
        "chunk_hit@1": chunk_hit_at_1,
        "mrr_chunks": mrr_chunks,
        "coverage_budget_lenient": coverage,
        "n_chunks_kept": float(len(kept_chunks)),
    }


def _norm_ws(s: str) -> str:
    return " ".join((s or "").split())


def compute_coverage_budget_strict_substring(
    evidence_text: str,
    gold_nodes: Sequence[str],
    line_text_by_node: Dict[str, str],
    *,
    min_line_chars: int = 12,
) -> float:
    """
    plan §P8 appendix strict sanity：每条 gold 行正文（规范化空白）须作为子串出现在 evidence 中。
    gold_nodes 形如 ``doc_id:L{line_id}``；``line_text_by_node`` 与 gold_nodes 同键。
    """
    gold_set = {str(g) for g in gold_nodes}
    if not gold_set:
        return 1.0
    ev = _norm_ws(evidence_text)
    hit = 0
    for gn in gold_set:
        raw = line_text_by_node.get(gn) or ""
        t = _norm_ws(raw)
        if len(t) < min_line_chars:
            if t and t in ev.replace(" ", ""):
                hit += 1
            continue
        if t in ev:
            hit += 1
    return hit / float(len(gold_set))


def gather_hierarchical_candidates(
    tools,
    query: str,
    *,
    doc_id: Optional[str],
    route_m: int,
) -> Tuple[List[Tuple[Chunk, float]], List[str]]:
    """
    plan §3.3 Expose 风格的候选汇聚（无 k 上限版本）：
      1. route_global(query, m=route_m) 选 m 个 section
      2. 对这 m 个 section 的 fact_by_section 全量小块打分
    返回 `(scored_chunks, section_ids)`；不再做 per-section top-k 截断，交给 `evaluate_at_budget`。
    """
    queries = _build_retrieval_queries(query)
    section_ids = tools.route_global(queries[0], route_m, doc_id=doc_id)
    scored: List[Tuple[Chunk, float]] = []
    seen: set = set()
    for sid in section_ids:
        pool = tools.index.fact_by_section.get(sid, [])
        for c in pool:
            if c.node_id in seen:
                continue
            seen.add(c.node_id)
        pool_list: List[Chunk] = list(pool)
        if not pool_list:
            continue
        k = max(1, len(pool_list))
        for qi, q in enumerate(queries):
            hits = tools.index.search(q, pool_list, k, doc_id_filter=doc_id)
            q_weight = _query_weight(qi)
            scored.extend((c, float(s) * q_weight) for c, s in hits)
    return _merge_max_by_node(scored), list(section_ids)


def gather_flat_candidates(
    tools,
    query: str,
    *,
    doc_id: Optional[str],
) -> List[Tuple[Chunk, float]]:
    """
    flat 基线：对 flat_chunks（若无则 small_chunks）全量打分；plan §P1 要求无 k 上限。
    """
    pool = tools.index.flat_chunks if tools.index.flat_chunks else tools.index.small_chunks
    pool_list = [c for c in pool if (doc_id is None or c.doc_id == doc_id)]
    if not pool_list:
        return []
    k = max(1, len(pool_list))
    queries = _build_retrieval_queries(query)
    all_hits: List[Tuple[Chunk, float]] = []
    for qi, q in enumerate(queries):
        q_weight = _query_weight(qi)
        hits = tools.index.search(q, pool_list, k, doc_id_filter=doc_id)
        all_hits.extend((c, float(s) * q_weight) for c, s in hits)
    return _merge_max_by_node(all_hits)


def _merge_max_by_node(scored: Sequence[Tuple[Chunk, float]]) -> List[Tuple[Chunk, float]]:
    best: Dict[str, Tuple[Chunk, float]] = {}
    for c, s in scored:
        prev = best.get(c.node_id)
        if prev is None or float(s) > float(prev[1]):
            best[c.node_id] = (c, float(s))
    out = list(best.values())
    out.sort(key=lambda x: -x[1])
    return out


def _query_weight(query_idx: int) -> float:
    """
    原始 query 权重最高；rewrite / HyDE 补充召回。
    默认：
      q0(raw)=1.0, q1(rewrite)=0.75, q2+(HyDE)=0.60
    """
    if query_idx <= 0:
        return 1.0
    if query_idx == 1:
        return float(_env_float("BODYRICH_QUERY_REWRITE_WEIGHT", 0.75))
    return float(_env_float("BODYRICH_QUERY_HYDE_WEIGHT", 0.60))


def _env_on(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "")
    if not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _heuristic_rewrite(query: str) -> str:
    q = re.sub(r"\s+", " ", (query or "").strip())
    # 轻量重写：去除中文口语词与问句尾巴，保留关键词。
    q = re.sub(r"(请问|帮我|能不能|可以|一下|谢谢)$", "", q).strip()
    return q or (query or "").strip()


def _llm_rewrite_query(query: str) -> Optional[str]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return None
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None
    model = os.environ.get("BODYRICH_REWRITE_MODEL", os.environ.get("COMPOSE_MODEL", "gpt-4o-mini")).strip()
    base = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    client = OpenAI(api_key=key, base_url=base)
    try:
        rsp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Rewrite query into concise retrieval query with key entities/constraints only."},
                {"role": "user", "content": query},
            ],
            temperature=0.1,
            max_tokens=64,
        )
        txt = (rsp.choices[0].message.content or "").strip()
        return txt if txt else None
    except Exception:
        return None


def _llm_hyde_queries(query: str, n: int = 1) -> List[str]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key or n <= 0:
        return []
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return []
    model = os.environ.get("BODYRICH_HYDE_MODEL", os.environ.get("COMPOSE_MODEL", "gpt-4o-mini")).strip()
    base = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    client = OpenAI(api_key=key, base_url=base)
    out: List[str] = []
    for _ in range(n):
        try:
            rsp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Write a short factual passage likely to contain answer evidence for retrieval."},
                    {"role": "user", "content": query},
                ],
                temperature=0.8,
                max_tokens=96,
            )
            txt = (rsp.choices[0].message.content or "").strip()
            if txt:
                out.append(txt)
        except Exception:
            continue
    return out


def _build_retrieval_queries(query: str) -> List[str]:
    """
    参考 wiki-rag：raw -> rewrite -> (optional) HyDE，多查询融合召回。
    默认仅 raw；通过环境变量逐步开启：
      BODYRICH_QUERY_REWRITE=1
      BODYRICH_QUERY_HYDE=1
      BODYRICH_QUERY_HYDE_N=1
    """
    raw = (query or "").strip()
    out = [raw]
    if _env_on("BODYRICH_QUERY_REWRITE", default=True):
        rewritten = _llm_rewrite_query(raw) if _env_on("BODYRICH_QUERY_REWRITE_LLM", default=False) else None
        if not rewritten:
            rewritten = _heuristic_rewrite(raw)
        if rewritten and rewritten != raw:
            out.append(rewritten)
    if _env_on("BODYRICH_QUERY_HYDE", default=False):
        n = int(max(1, _env_float("BODYRICH_QUERY_HYDE_N", 1)))
        out.extend(_llm_hyde_queries(raw, n=n))
    # 去重保序
    dedup: List[str] = []
    seen = set()
    for q in out:
        qq = (q or "").strip()
        if not qq or qq in seen:
            continue
        seen.add(qq)
        dedup.append(qq)
    return dedup or [raw]
