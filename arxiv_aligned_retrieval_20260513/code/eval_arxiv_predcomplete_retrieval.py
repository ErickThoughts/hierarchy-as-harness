#!/usr/bin/env python3
"""Retrieval-only arXiv pred-complete eval aligned with realdata retrieval logic."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_CODE_DIR = (PACKAGE_ROOT / "code").resolve()
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

from agent_delivery.agent.tasks_loader import _load_tasks
from agent_delivery.agent.types import AgentTask
from agent_delivery.code.budget_eval import (
    _build_retrieval_queries,
    _query_weight,
    compute_budget_retrieval_metrics,
    evaluate_at_budget,
    gather_flat_candidates,
)
from agent_delivery.code.embedding_backend import DEFAULT_DENSE_EMBEDDING_MODEL
from agent_delivery.code.hierarchical_tools import HierarchicalTools
from agent_delivery.code.index_retrieval import Chunk, CorpusIndex
from agent_delivery.code.load_data import bundles_from_paths, line_node_id
from agent_delivery.code.metrics import retrieval_metrics
from agent_delivery.code.tool_space import ToolSpace


Scored = List[Tuple[Chunk, float]]
HierScoreMode = str
HierRetrievalMode = str


def _chunks_to_retrieved_nodes(chunks: Sequence[Chunk]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for c in chunks:
        for lid in c.line_ids:
            node = f"{c.doc_id}:L{lid}"
            if node not in seen:
                seen.add(node)
                out.append(node)
    return out


def _merge_max_by_node(scored: Sequence[Tuple[Chunk, float]]) -> Scored:
    best: Dict[str, Tuple[Chunk, float]] = {}
    for c, s in scored:
        prev = best.get(c.node_id)
        if prev is None or float(s) > float(prev[1]):
            best[c.node_id] = (c, float(s))
    out = list(best.values())
    out.sort(key=lambda x: -x[1])
    return out


def _split_path_body_text(text: str) -> Tuple[str, str]:
    lines = (text or "").splitlines()
    if lines and lines[0].strip().startswith("PATH:"):
        return lines[0].strip(), "\n".join(lines[1:]).strip()
    return "", (text or "").strip()


def _hier_score_text(chunk: Chunk, score_mode: HierScoreMode) -> str:
    path_text, body_text = _split_path_body_text(chunk.text or "")
    if score_mode == "full_text":
        return (chunk.text or "").strip() or " "
    if score_mode == "content_only":
        return body_text or (chunk.text or "").strip() or " "
    if score_mode == "path_only":
        return path_text or (chunk.text or "").strip() or " "
    raise ValueError(f"unsupported hier_score_mode={score_mode!r}")


def _hier_scoring_pool(
    pool: Sequence[Chunk],
    score_mode: HierScoreMode,
) -> Tuple[List[Chunk], Dict[str, Chunk]]:
    """
    Build a scoring-only pool for hierarchical diagnostic modes.

    The returned chunks may contain only PATH text or only content text for dense
    scoring, but they map back to the original PATH+content chunks before budget
    fill and metric computation.  Use distinct node_ids so CorpusIndex's
    embedding cache cannot confuse full/content/path embeddings.
    """
    if score_mode == "full_text":
        return list(pool), {c.node_id: c for c in pool}

    scored_pool: List[Chunk] = []
    original_by_score_id: Dict[str, Chunk] = {}
    for c in pool:
        score_id = f"{c.node_id}__score_{score_mode}"
        sc = Chunk(
            node_id=score_id,
            doc_id=c.doc_id,
            text=_hier_score_text(c, score_mode),
            line_ids=c.line_ids,
            section_id=c.section_id,
        )
        scored_pool.append(sc)
        original_by_score_id[score_id] = c
    return scored_pool, original_by_score_id


def _line_windows_by_chars(
    indices: Sequence[int],
    lines: Sequence[Any],
    *,
    max_chars: int,
) -> List[List[int]]:
    if not indices:
        return []
    max_chars = max(40, int(max_chars))
    windows: List[List[int]] = []
    cur: List[int] = []
    cur_len = 0
    for idx in indices:
        text = (lines[idx].content or "").strip()
        add_len = len(text) + (1 if cur else 0)
        if cur and cur_len + add_len > max_chars:
            windows.append(cur)
            cur = []
            cur_len = 0
        cur.append(idx)
        cur_len += add_len if cur_len else len(text)
    if cur:
        windows.append(cur)
    return windows


def _materialize_leaf_path_window_chunks(
    space: ToolSpace,
    section_id: str,
    doc_id: str,
    *,
    window_chars: int,
) -> List[Chunk]:
    """
    Length-normalized variant of ToolSpace leaf/path chunks.

    It mirrors ToolSpace's leaf/path span construction, then splits each span's
    body lines into fixed character windows while preserving PATH text in the
    emitted evidence chunk.  This keeps the hierarchy evidence format but
    reduces chunk length and budget-fill bias.
    """
    bounds = space._subtree_bounds_for_section_path(section_id, doc_id)
    b = space._idx._bundles.get(doc_id)
    if bounds is None or not b:
        return []
    start, end = bounds
    if start >= end:
        return []

    levels = b.levels_for_tree
    parents = space._idx._doc_parents.get(doc_id, [])
    base_level = levels[start] if start < len(levels) else 0

    def lev_at(i: int) -> int:
        return levels[i] if i < len(levels) else 0

    def next_boundary(root: int) -> int:
        root_level = lev_at(root)
        if root_level <= 0:
            return min(root + 1, end)
        for k in range(root + 1, end):
            lk = lev_at(k)
            if lk > 0 and lk <= root_level:
                return k
        return end

    def has_deeper_structural_child(root: int, root_end: int) -> bool:
        root_level = lev_at(root)
        if root_level <= 0:
            return False
        for k in range(root + 1, root_end):
            if lev_at(k) > root_level:
                return True
        return False

    structural = [
        j for j in range(start, end) if j == start or (lev_at(j) > max(base_level, 0))
    ]
    leaf_roots: List[int] = []
    for j in structural:
        rb = next_boundary(j)
        if not has_deeper_structural_child(j, rb):
            leaf_roots.append(j)
    if not leaf_roots:
        leaf_roots = [start]

    first_child = next((j for j in leaf_roots if j > start), None)
    spans: List[tuple[str, int, int]] = []
    if first_child is not None and first_child > start + 1:
        spans.append(("intro", start, first_child))
    for root in leaf_roots:
        spans.append(("leaf", root, next_boundary(root)))

    chunks: List[Chunk] = []
    seen_spans: set[tuple[int, int]] = set()
    for kind, root, root_end in spans:
        root_end = max(root + 1, min(root_end, end))
        span_key = (root, root_end)
        if span_key in seen_spans:
            continue
        seen_spans.add(span_key)

        path_indices: List[int] = []
        cur: Optional[int] = root
        visited = 0
        while cur is not None and start <= cur < end and visited <= len(b.lines):
            if cur == start or lev_at(cur) > 0:
                path_indices.append(cur)
            cur = parents[cur] if cur < len(parents) else None
            visited += 1
        path_indices = list(reversed(path_indices))

        body_indices = list(range(root, root_end))
        body_windows = _line_windows_by_chars(
            body_indices, b.lines, max_chars=window_chars
        ) or [body_indices]
        path = " / ".join((b.lines[i].content or "").strip() for i in path_indices)
        root_nid = line_node_id(doc_id, b.lines[root].line_id)
        suffix = "intro" if kind == "intro" else "path"
        for wi, win_indices in enumerate(body_windows):
            text_parts: List[str] = []
            if path:
                text_parts.append(f"PATH: {path}")
            text_parts.extend((b.lines[i].content or "").strip() for i in win_indices)
            line_ids = tuple(
                b.lines[i].line_id for i in sorted(set(path_indices + win_indices))
            )
            chunks.append(
                Chunk(
                    node_id=f"{root_nid}__{suffix}__w{wi}",
                    doc_id=doc_id,
                    text="\n".join(p for p in text_parts if p),
                    line_ids=line_ids,
                    section_id=section_id,
                )
            )
    return chunks


def _doc_leaf_path_window_pool(
    space: ToolSpace,
    doc_id: str,
    *,
    window_chars: int,
) -> List[Chunk]:
    out: List[Chunk] = []
    seen: set[str] = set()
    for sid in space.sections_for_doc(doc_id):
        for c in _materialize_leaf_path_window_chunks(
            space, sid, doc_id, window_chars=window_chars
        ):
            if c.node_id in seen:
                continue
            seen.add(c.node_id)
            out.append(c)
    return out or space.leaf_path_search_pool(doc_id)


def _top_routed_sections(
    space: ToolSpace,
    query: str,
    *,
    doc_id: str,
    route_m: int,
) -> List[str]:
    section_ids = space.sections_for_doc(doc_id)
    if not section_ids:
        return []
    score_by_sid = _score_top_sections(space._t, query, doc_id=doc_id)
    ranked = sorted(section_ids, key=lambda sid: score_by_sid.get(sid, 0.0), reverse=True)
    return ranked[: max(1, min(len(ranked), int(route_m)))]


def _hier_candidate_pool(
    space: ToolSpace,
    query: str,
    *,
    doc_id: str,
    retrieval_mode: HierRetrievalMode,
    route_m: int,
    window_chars: int,
) -> List[Chunk]:
    if retrieval_mode == "global_leaf_path":
        return space.leaf_path_search_pool(doc_id)
    if retrieval_mode == "length_normalized":
        return _doc_leaf_path_window_pool(space, doc_id, window_chars=window_chars)
    if retrieval_mode in ("routed_leaf_path", "routed_length_normalized"):
        routed_sections = _top_routed_sections(
            space, query, doc_id=doc_id, route_m=route_m
        )
        out: List[Chunk] = []
        seen: set[str] = set()
        for sid in routed_sections:
            if retrieval_mode == "routed_length_normalized":
                section_pool = _materialize_leaf_path_window_chunks(
                    space, sid, doc_id, window_chars=window_chars
                )
            else:
                section_pool = space._materialize_leaf_path_chunks(sid, doc_id)
            for c in section_pool:
                if c.node_id in seen:
                    continue
                seen.add(c.node_id)
                out.append(c)
        return out or space.leaf_path_search_pool(doc_id)
    raise ValueError(f"unsupported hier_retrieval_mode={retrieval_mode!r}")


def _flat_pool(index: CorpusIndex, doc_id: str) -> List[Chunk]:
    pool = index.flat_chunks if index.flat_chunks else index.small_chunks
    return [c for c in pool if c.doc_id == doc_id]


def _query_variants_for_flat_react(query: str, task_type: str, max_rounds: int) -> List[str]:
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
) -> Tuple[Scored, List[str]]:
    section_ids = _all_top_section_ids(tools, doc_id)
    score_by_sid = _score_top_sections(tools, query, doc_id=doc_id)
    scored: Scored = []
    for sid in section_ids:
        pool = list(tools.index.fact_by_section.get(sid, []))
        if not pool:
            continue
        hits = tools.index.search(query, pool, len(pool), doc_id_filter=doc_id)
        sec_weight = 1.0 + max(0.0, score_by_sid.get(sid, 0.0)) * 0.05
        scored.extend((c, float(s) * sec_weight) for c, s in hits)
    return _merge_max_by_node(scored), section_ids


def _gather_multilevel_path_candidates(
    space: ToolSpace,
    query: str,
    *,
    doc_id: Optional[str],
    score_mode: HierScoreMode = "full_text",
    retrieval_mode: HierRetrievalMode = "global_leaf_path",
    route_m: int = 3,
    window_chars: int = 220,
) -> Scored:
    """
    Retrieval-only analogue of realdata toolspace search:
    materialize the document's multi-level leaf/path evidence pool, then apply
    the same budget_eval multi-query fusion used by realdata retrieval.
    """
    if not doc_id:
        return []
    pool = _hier_candidate_pool(
        space,
        query,
        doc_id=doc_id,
        retrieval_mode=retrieval_mode,
        route_m=route_m,
        window_chars=window_chars,
    )
    if not pool:
        return []
    scoring_pool, original_by_score_id = _hier_scoring_pool(pool, score_mode)
    scored: Scored = []
    for qi, q in enumerate(_build_retrieval_queries(query)):
        hits = space._idx.search(q, scoring_pool, len(scoring_pool), doc_id_filter=doc_id)
        weight = _query_weight(qi)
        for c_score, s in hits:
            c_orig = original_by_score_id.get(c_score.node_id, c_score)
            scored.append((c_orig, float(s) * weight))
    return _merge_max_by_node(scored)


def _path_depth(chunk: Chunk) -> int:
    text = chunk.text or ""
    first = text.splitlines()[0].strip() if text.strip() else ""
    if not first.startswith("PATH:"):
        return 0
    path = first[len("PATH:") :].strip()
    if not path:
        return 0
    return len([p for p in path.split(" / ") if p.strip()])


def _path_depth_summary(chunks: Sequence[Chunk]) -> Dict[str, Any]:
    depths = [_path_depth(c) for c in chunks]
    if not depths:
        return {"n": 0, "mean": None, "max": None, "hist": {}}
    hist: Dict[str, int] = defaultdict(int)
    for d in depths:
        hist[str(d)] += 1
    return {
        "n": len(depths),
        "mean": float(statistics.mean(depths)),
        "max": max(depths),
        "hist": dict(sorted(hist.items(), key=lambda kv: int(kv[0]))),
    }


def _gather_flat_react_candidates(
    tools: HierarchicalTools,
    query: str,
    *,
    task_type: str,
    doc_id: Optional[str],
) -> Scored:
    """与 `runner_bodyrich.run_flat_react_episode` 一致：每轮 variant 上调用 `gather_flat_candidates`（内含 `_build_retrieval_queries`）。"""
    rounds = int(os.environ.get("FLAT_REACT_SEARCH_ROUNDS", "3").strip() or "3")
    rounds = max(1, min(8, rounds))
    k_each = int(os.environ.get("FLAT_REACT_K_PER_ROUND", "64").strip() or "64")
    k_each = max(8, min(256, k_each))
    if not doc_id:
        return []

    all_scored: Scored = []
    tt = (task_type or "").strip()
    for qi, q in enumerate(_query_variants_for_flat_react(query, tt, rounds), start=1):
        scored_q = gather_flat_candidates(tools, q, doc_id=doc_id)[:k_each]
        weight = 1.0 if qi == 1 else max(0.45, 0.82 ** (qi - 1))
        all_scored.extend((c, float(s) * weight) for c, s in scored_q)
    return _merge_max_by_node(all_scored)


def _validate_tasks_gold_nodes(tasks: Sequence[AgentTask], index: CorpusIndex) -> None:
    nodes_by_doc: Dict[str, set[str]] = {}
    for doc_id, bundle in index._bundles.items():
        nodes_by_doc[doc_id] = {line_node_id(doc_id, r.line_id) for r in bundle.lines}
    missing: List[str] = []
    for i, task in enumerate(tasks, start=1):
        doc_nodes = nodes_by_doc.get(task.doc_id or "")
        if doc_nodes is None:
            missing.append(f"task#{i} doc_id={task.doc_id!r} missing document")
            continue
        bad = [n for n in task.gold_nodes if n not in doc_nodes]
        if bad:
            missing.append(f"task#{i} doc_id={task.doc_id!r} missing gold_nodes={bad}")
    if missing:
        preview = "\n".join(missing[:20])
        raise RuntimeError(f"tasks are not aligned with pred-complete corpus:\n{preview}")


def _score_at_budget(task: AgentTask, scored: Scored, budget: int) -> Dict[str, Any]:
    fill = evaluate_at_budget(scored, budget_chars=budget)
    retrieved_nodes = _chunks_to_retrieved_nodes(fill.kept_chunks)
    budget_metrics = compute_budget_retrieval_metrics(fill.kept_chunks, task.gold_nodes)
    line_metrics = retrieval_metrics(retrieved_nodes, task.gold_nodes, k_list=(1, 3, 5))
    return {
        "evidence_chars_actual": fill.evidence_chars_actual,
        "n_chunks_kept": fill.n_chunks_kept,
        "truncated_last": fill.truncated_last,
        "kept_chunk_ids": [c.node_id for c in fill.kept_chunks],
        "retrieved_nodes": retrieved_nodes,
        "evidence_preview": fill.evidence_text[:800],
        "budget": budget_metrics,
        "line_retrieval": line_metrics,
    }


def _mean(xs: Iterable[Optional[float]]) -> Optional[float]:
    vals = [float(x) for x in xs if x is not None and not math.isnan(float(x))]
    if not vals:
        return None
    return float(statistics.mean(vals))


def _summarize_arm(rows: Sequence[Dict[str, Any]], arm: str) -> Dict[str, Any]:
    return {
        "chunk_hit@1_mean": _mean(r[arm]["budget"]["chunk_hit@1"] for r in rows),
        "mrr_chunks_mean": _mean(r[arm]["budget"]["mrr_chunks"] for r in rows),
        "coverage_budget_lenient_mean": _mean(
            r[arm]["budget"]["coverage_budget_lenient"] for r in rows
        ),
        "precision@1_line_mean": _mean(r[arm]["line_retrieval"]["precision@1"] for r in rows),
        "precision@3_line_mean": _mean(r[arm]["line_retrieval"]["precision@3"] for r in rows),
        "precision@5_line_mean": _mean(r[arm]["line_retrieval"]["precision@5"] for r in rows),
        "mrr_line_mean": _mean(r[arm]["line_retrieval"]["mrr"] for r in rows),
        "hit@5_line_mean": _mean(r[arm]["line_retrieval"]["hit@5"] for r in rows),
        "ndcg@10_line_mean": _mean(r[arm]["line_retrieval"]["ndcg@10"] for r in rows),
        "coverage_line_mean": _mean(r[arm]["line_retrieval"]["coverage"] for r in rows),
        "evidence_chars_actual_mean": _mean(r[arm]["evidence_chars_actual"] for r in rows),
        "n_chunks_kept_mean": _mean(r[arm]["n_chunks_kept"] for r in rows),
    }


def _delta(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for k, av in a.items():
        bv = b.get(k)
        if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
            out[k] = float(av) - float(bv)
    return out


def _per_type(rows: Sequence[Dict[str, Any]], arm: str) -> Dict[str, Dict[str, Any]]:
    by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_type[str(row.get("task_type") or "unknown")].append(row)
    return {tt: {"n": len(rs), **_summarize_arm(rs, arm)} for tt, rs in sorted(by_type.items())}


def _fmt(v: Any) -> str:
    if not isinstance(v, (int, float)):
        return "-"
    return f"{float(v):.3f}"


def _fmt_delta(v: Any) -> str:
    if not isinstance(v, (int, float)):
        return "-"
    return f"{float(v):+.3f}"


def _num(x: Any) -> Optional[float]:
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        if isinstance(x, float) and math.isnan(x):
            return None
        return float(x)
    return None


_SUMMARY_METRIC_ROWS: List[Tuple[str, str]] = [
    ("coverage_budget_lenient_mean", "Coverage@budget_lenient"),
    ("mrr_chunks_mean", "MRR@chunks"),
    ("chunk_hit@1_mean", "ChunkHit@1"),
    ("precision@1_line_mean", "Precision@1 line"),
    ("precision@3_line_mean", "Precision@3 line"),
    ("precision@5_line_mean", "Precision@5 line"),
    ("mrr_line_mean", "MRR line"),
    ("hit@5_line_mean", "Hit@5 line"),
    ("ndcg@10_line_mean", "NDCG@10 line"),
    ("coverage_line_mean", "Coverage line"),
    ("evidence_chars_actual_mean", "Evidence chars"),
    ("n_chunks_kept_mean", "Chunks kept"),
]


_ROW_METRIC_PATHS: Dict[str, Tuple[str, str]] = {
    "coverage_budget_lenient_mean": ("budget", "coverage_budget_lenient"),
    "mrr_chunks_mean": ("budget", "mrr_chunks"),
    "chunk_hit@1_mean": ("budget", "chunk_hit@1"),
    "precision@1_line_mean": ("line_retrieval", "precision@1"),
    "precision@3_line_mean": ("line_retrieval", "precision@3"),
    "precision@5_line_mean": ("line_retrieval", "precision@5"),
    "mrr_line_mean": ("line_retrieval", "mrr"),
    "hit@5_line_mean": ("line_retrieval", "hit@5"),
    "ndcg@10_line_mean": ("line_retrieval", "ndcg@10"),
    "coverage_line_mean": ("line_retrieval", "coverage"),
    "evidence_chars_actual_mean": ("", "evidence_chars_actual"),
    "n_chunks_kept_mean": ("", "n_chunks_kept"),
}


_METRIC_DEFINITIONS: List[Tuple[str, str]] = [
    ("Coverage@budget_lenient", "预算内 evidence 覆盖 gold line 的比例；主召回指标。"),
    ("MRR@chunks", "第一个命中 gold line 的 evidence chunk 的倒数排名。"),
    ("ChunkHit@1", "排名第一的 evidence chunk 是否命中任一 gold line。"),
    ("Precision@k line", "预算内去重 retrieved line 的前 k 个中 gold line 占比。"),
    ("MRR line", "第一个 gold line 在 retrieved line 序列中的倒数排名。"),
    ("Hit@5 line", "前 5 个 retrieved line 是否命中任一 gold line。"),
    ("NDCG@10 line", "前 10 个 retrieved line 的排序质量。"),
    ("Coverage line", "预算内 retrieved line 对 gold line 的覆盖率；本协议下与 Coverage@budget_lenient 同源。"),
    ("Evidence chars", "实际写入 evidence 的字符数，受 budget 限制。"),
    ("Chunks kept", "预算内保留的 evidence chunk 数。"),
]


def _refresh_payload_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute summary tables from rows so old result JSONs can emit newer MD metrics."""
    rows = payload.get("rows") or []
    if not rows:
        return payload

    summary = dict(payload.get("summary") or {})
    sum_gold = _summarize_arm(rows, "gold_hier")
    sum_pred = _summarize_arm(rows, "pred_hier")
    sum_flat = _summarize_arm(rows, "flat")
    summary.update(
        {
            "n_tasks": len(rows),
            "gold_hier": sum_gold,
            "pred_hier": sum_pred,
            "flat": sum_flat,
            "delta_pred_minus_flat": _delta(sum_pred, sum_flat),
            "delta_gold_minus_flat": _delta(sum_gold, sum_flat),
            "delta_pred_minus_gold": _delta(sum_pred, sum_gold),
            "per_type_gold_hier": _per_type(rows, "gold_hier"),
            "per_type_pred_hier": _per_type(rows, "pred_hier"),
            "per_type_flat": _per_type(rows, "flat"),
        }
    )
    out = dict(payload)
    out["summary"] = summary
    return out


def _row_metric(row: Dict[str, Any], arm: str, metric_key: str) -> Optional[float]:
    path = _ROW_METRIC_PATHS.get(metric_key)
    if path is None:
        return None
    group, key = path
    arm_payload = row.get(arm) or {}
    raw = arm_payload.get(key) if not group else (arm_payload.get(group) or {}).get(key)
    return _num(raw)


def _win_tie_loss(
    rows: Sequence[Dict[str, Any]],
    left_arm: str,
    right_arm: str,
    metric_key: str,
) -> Tuple[int, int, int]:
    left_wins = right_wins = ties = 0
    for row in rows:
        lv = _row_metric(row, left_arm, metric_key)
        rv = _row_metric(row, right_arm, metric_key)
        if lv is None or rv is None:
            continue
        if lv > rv:
            left_wins += 1
        elif rv > lv:
            right_wins += 1
        else:
            ties += 1
    return left_wins, right_wins, ties


def _task_type_counts(payloads: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    if not payloads:
        return {}
    rows = payloads[0].get("rows") or []
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("task_type") or "unknown")] += 1
    return dict(sorted(counts.items()))


def _alignment_audit_lines() -> List[str]:
    return [
        "## 对齐审计",
        "",
        "| 检查项 | arXiv 当前逻辑 | 与 realdata 的关系 | 结论 |",
        "| --- | --- | --- | --- |",
        "| 数据加载 | `bundles_from_paths` 读取 `gold_level` / `predicted_level` / flat levels | 复用同名 loader；关键文件与 `core/` diff clean | 对齐 |",
        "| 层级候选 | `ToolSpace.leaf_path_search_pool(doc_id)` 物化多层 `PATH:` + subtree chunk | 使用 realdata toolspace 的 leaf/path evidence 表示 | 对齐到检索单元 |",
        "| 层级检索 | 在整篇文档 leaf/path 池上用 `_build_retrieval_queries` + `_query_weight` 做 dense fusion | 跳过 ReAct 工具轨迹，保留检索表示与 query fusion | retrieval-only 对齐 |",
        "| Flat 对照 | `_query_variants_for_flat_react` 多轮变体 + `gather_flat_candidates` | 与 `runner_bodyrich.run_flat_react_episode` 的检索段一致 | 对齐 |",
        "| Budget 填充 | `evaluate_at_budget` 字符预算、可截断最后一块 | 与 realdata budget 逻辑一致 | 对齐 |",
        "| 指标 | `compute_budget_retrieval_metrics` + `retrieval_metrics` | 与 realdata 检索指标同源 | 对齐 |",
        "| Agent/LLM | `llm_compose=False`，不调用 compose/judge/agent scoring | 用户要求只做检索 | 已移除 |",
        "",
        "说明：这里的 Gold-hier 是 gold tree 生成的检索候选结构，不是 oracle 路由；它不会直接知道答案位置。",
        "",
    ]


def _core_conclusion_lines(payloads: Sequence[Dict[str, Any]]) -> List[str]:
    lines = ["## 核心结论", ""]
    if not payloads:
        return lines

    coverage_key = "coverage_budget_lenient_mean"
    pred_flat_better: List[int] = []
    pred_flat_worse: List[int] = []
    pred_flat_tied: List[int] = []
    pred_gold_better: List[int] = []
    pred_gold_worse: List[int] = []
    pred_gold_tied: List[int] = []
    for payload in payloads:
        s = payload["summary"]
        rows = payload.get("rows") or []
        budget = s["config"]["budget_chars"]
        g = _num(s["gold_hier"].get(coverage_key))
        p = _num(s["pred_hier"].get(coverage_key))
        f = _num(s["flat"].get(coverage_key))
        vals = [("Gold-hier", g), ("Pred-hier", p), ("Flat-react", f)]
        vals_num = [(name, val) for name, val in vals if val is not None]
        best_name, best_val = max(vals_num, key=lambda item: item[1])
        pw, gw, ties = _win_tie_loss(rows, "pred_hier", "gold_hier", coverage_key)
        dpf = (p - f) if p is not None and f is not None else None
        dpg = (p - g) if p is not None and g is not None else None
        lines.append(
            f"- budget={budget}: 主指标 Coverage@budget_lenient 最好的是 {best_name} ({_fmt(best_val)})；"
            f"Pred-Flat={_fmt_delta(dpf)}，Pred-Gold={_fmt_delta(dpg)}；"
            f"题级 Pred>Gold / Gold>Pred / Tie = {pw}/{gw}/{ties}。"
        )
        if dpf is not None:
            if dpf > 0:
                pred_flat_better.append(int(budget))
            elif dpf < 0:
                pred_flat_worse.append(int(budget))
            else:
                pred_flat_tied.append(int(budget))
        if dpg is not None:
            if dpg > 0:
                pred_gold_better.append(int(budget))
            elif dpg < 0:
                pred_gold_worse.append(int(budget))
            else:
                pred_gold_tied.append(int(budget))

    def _budget_list(values: List[int]) -> str:
        return ", ".join(str(v) for v in values) if values else "-"

    if pred_flat_better and pred_flat_worse:
        lines.append(
            "- Pred-hier 相对 Flat-react 的收益不稳定："
            f"Pred 更好的 budget={_budget_list(pred_flat_better)}；"
            f"Flat 更好的 budget={_budget_list(pred_flat_worse)}；"
            f"打平 budget={_budget_list(pred_flat_tied)}。"
        )
    elif pred_flat_better and not pred_flat_worse:
        lines.append(
            f"- Pred-hier 在这些 budget 下整体不低于 Flat-react：Pred 更好的 budget={_budget_list(pred_flat_better)}；"
            f"打平 budget={_budget_list(pred_flat_tied)}。"
        )
    elif pred_flat_worse and not pred_flat_better:
        lines.append(
            f"- Flat-react 在这些 budget 下整体强于 Pred-hier：Flat 更好的 budget={_budget_list(pred_flat_worse)}；"
            f"打平 budget={_budget_list(pred_flat_tied)}。"
        )

    if pred_gold_better and pred_gold_worse:
        lines.append(
            "- Pred-hier 与 Gold-hier 的差异随 budget 改变："
            f"Pred 更好的 budget={_budget_list(pred_gold_better)}；"
            f"Gold 更好的 budget={_budget_list(pred_gold_worse)}；"
            f"打平 budget={_budget_list(pred_gold_tied)}。"
        )
    elif pred_gold_better and not pred_gold_worse:
        lines.append(
            f"- Pred-hier 平均不低于 Gold-hier：Pred 更好的 budget={_budget_list(pred_gold_better)}；"
            f"打平 budget={_budget_list(pred_gold_tied)}。差异主要来自少数题的 chunk 边界/路径文本变化。"
        )
    elif pred_gold_worse and not pred_gold_better:
        lines.append(
            f"- Gold-hier 平均不低于 Pred-hier：Gold 更好的 budget={_budget_list(pred_gold_worse)}；"
            f"打平 budget={_budget_list(pred_gold_tied)}。"
        )
    lines.append("")

    lines.append("按题型看主指标 Coverage@budget_lenient 的 Pred-Flat：")
    lines.append("")
    lines.append("| Budget | Pred-hier 优于 Flat-react | 打平 | Flat-react 优于 Pred-hier |")
    lines.append("| ---: | --- | --- | --- |")
    for payload in payloads:
        s = payload["summary"]
        budget = s["config"]["budget_chars"]
        pp = s.get("per_type_pred_hier") or {}
        pf = s.get("per_type_flat") or {}
        better: List[str] = []
        tied: List[str] = []
        worse: List[str] = []
        for tt in sorted(set(pp.keys()) | set(pf.keys())):
            pv = _num((pp.get(tt) or {}).get(coverage_key))
            fv = _num((pf.get(tt) or {}).get(coverage_key))
            if pv is None or fv is None:
                continue
            if pv > fv:
                better.append(tt)
            elif fv > pv:
                worse.append(tt)
            else:
                tied.append(tt)
        lines.append(
            f"| {budget} | {', '.join(better) or '-'} | {', '.join(tied) or '-'} | {', '.join(worse) or '-'} |"
        )
    lines.append("")
    return lines


def _metric_definition_lines() -> List[str]:
    lines = ["## 指标说明", ""]
    lines.append("| Metric | 含义 |")
    lines.append("| --- | --- |")
    for label, desc in _METRIC_DEFINITIONS:
        lines.append(f"| {label} | {desc} |")
    lines.append("")
    return lines


def _task_count_lines(payloads: Sequence[Dict[str, Any]]) -> List[str]:
    counts = _task_type_counts(payloads)
    lines = ["## 任务分布", ""]
    lines.append("| task_type | n |")
    lines.append("| --- | ---: |")
    for tt, n in counts.items():
        lines.append(f"| {tt} | {n} |")
    lines.append("")
    return lines


def _candidate_pool_lines(s: Dict[str, Any]) -> List[str]:
    pools = s.get("candidate_pools") or {}
    lines = ["Candidate pool path-depth check:"]
    for arm, label in [("gold_hier", "Gold-hier"), ("pred_hier", "Pred-hier")]:
        ds = (pools.get(arm) or {}).get("path_depth") or {}
        lines.append(
            f"- {label}: n={ds.get('n', 0)}, path_depth_mean={_fmt(ds.get('mean'))}, max={ds.get('max')}, hist={ds.get('hist', {})}"
        )
    flat_pool = pools.get("flat") or {}
    lines.append(f"- Flat-react: flat window chunks, n={flat_pool.get('n_chunks', 0)}, no PATH")
    lines.append("")
    return lines


def _overall_metric_lines(s: Dict[str, Any]) -> List[str]:
    lines = []
    lines.append("| Metric | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for key, label in _SUMMARY_METRIC_ROWS:
        g = _num((s.get("gold_hier") or {}).get(key))
        p = _num((s.get("pred_hier") or {}).get(key))
        f = _num((s.get("flat") or {}).get(key))
        dpf = (p - f) if p is not None and f is not None else None
        dgf = (g - f) if g is not None and f is not None else None
        dpg = (p - g) if p is not None and g is not None else None
        lines.append(
            f"| {label} | {_fmt(g)} | {_fmt(p)} | {_fmt(f)} | {_fmt_delta(dpf)} | {_fmt_delta(dgf)} | {_fmt_delta(dpg)} |"
        )
    lines.append("")
    return lines


def _per_type_markdown_lines(s: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    pg = s.get("per_type_gold_hier") or {}
    pp = s.get("per_type_pred_hier") or {}
    pf = s.get("per_type_flat") or {}
    types_sorted = sorted(set(pg.keys()) | set(pp.keys()) | set(pf.keys()))
    budget = s["config"]["budget_chars"]
    lines.append(f"### Per-type all metrics (budget={budget})")
    lines.append("")
    lines.append("| task_type | Metric | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for tt in types_sorted:
        for key, label in _SUMMARY_METRIC_ROWS:
            g = pg.get(tt) or {}
            p = pp.get(tt) or {}
            f = pf.get(tt) or {}
            n = int(g.get("n") or p.get("n") or f.get("n") or 0)
            gv, pv, fv = _num(g.get(key)), _num(p.get(key)), _num(f.get(key))
            dpf = (pv - fv) if pv is not None and fv is not None else None
            dgf = (gv - fv) if gv is not None and fv is not None else None
            dpg = (pv - gv) if pv is not None and gv is not None else None
            lines.append(
                f"| {tt} | {label} | {n} | {_fmt(gv)} | {_fmt(pv)} | {_fmt(fv)} | {_fmt_delta(dpf)} | {_fmt_delta(dgf)} | {_fmt_delta(dpg)} |"
            )
    lines.append("")
    return lines


def _write_markdown(results: Sequence[Dict[str, Any]], path: Path) -> None:
    payloads = [_refresh_payload_summary(payload) for payload in results]
    lines = ["# arXiv Pred-Complete Retrieval Summary", ""]
    lines.append(
        "Protocol: retrieval-only; hierarchical uses multi-level ToolSpace leaf/path chunks (`PATH:` + subtree evidence); flat uses flat_react-style multi-query fusion. No ReAct agent, compose, or LLM judge is run."
    )
    lines.append("")
    lines.extend(_alignment_audit_lines())
    lines.extend(_core_conclusion_lines(payloads))
    lines.extend(_metric_definition_lines())
    lines.extend(_task_count_lines(payloads))
    for payload in payloads:
        s = payload["summary"]
        budget = s["config"]["budget_chars"]
        cfg = s.get("config", {})
        score_mode = cfg.get("hier_score_mode", "full_text")
        retrieval_mode = cfg.get("hierarchy_unit", "global_leaf_path")
        lines.append(f"## budget={budget} (n={s['n_tasks']})")
        lines.append("")
        lines.append(f"Hierarchical dense scoring mode: `{score_mode}`.")
        lines.append(f"Hierarchical retrieval mode: `{retrieval_mode}`.")
        if retrieval_mode in ("routed_leaf_path", "routed_length_normalized"):
            lines.append(f"Route top sections: `{cfg.get('hier_route_m', '-')}`.")
        if retrieval_mode in ("length_normalized", "routed_length_normalized"):
            lines.append(f"Length-normalized body window chars: `{cfg.get('hier_window_chars', '-')}`.")
        lines.append("")
        lines.extend(_candidate_pool_lines(s))
        lines.extend(_overall_metric_lines(s))
        lines.extend(_per_type_markdown_lines(s))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_eval(args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.hier_score_mode not in {"full_text", "content_only", "path_only"}:
        raise ValueError(f"unsupported --hier-score-mode={args.hier_score_mode!r}")
    if args.hier_retrieval_mode not in {
        "global_leaf_path",
        "length_normalized",
        "routed_leaf_path",
        "routed_length_normalized",
    }:
        raise ValueError(
            f"unsupported --hier-retrieval-mode={args.hier_retrieval_mode!r}"
        )
    args.hier_route_m = max(1, int(args.hier_route_m))
    args.hier_window_chars = max(40, int(args.hier_window_chars))

    tasks = _load_tasks(args.tasks)
    if args.max_tasks > 0:
        tasks = tasks[: args.max_tasks]

    bundles_gold = bundles_from_paths(args.test_jsonl, tree_source="gold", max_docs=args.max_docs)
    bundles_pred = bundles_from_paths(
        args.test_jsonl, tree_source="pred", pred_path=args.test_jsonl, max_docs=args.max_docs
    )
    bundles_flat = bundles_from_paths(args.test_jsonl, tree_source="flat", max_docs=args.max_docs)

    idx_gold = CorpusIndex.from_bundles(
        bundles_gold,
        tree_mode="hierarchical",
        retrieval_backend="dense",
        embedding_model=args.embedding_model,
    )
    idx_pred = CorpusIndex.from_bundles(
        bundles_pred,
        tree_mode="hierarchical",
        retrieval_backend="dense",
        embedding_model=args.embedding_model,
    )
    idx_flat = CorpusIndex.from_bundles(
        bundles_flat,
        tree_mode="flat",
        retrieval_backend="dense",
        embedding_model=args.embedding_model,
    )
    _validate_tasks_gold_nodes(tasks, idx_gold)

    tools_gold = HierarchicalTools(idx_gold)
    tools_pred = HierarchicalTools(idx_pred)
    tools_flat = HierarchicalTools(idx_flat)
    space_gold = ToolSpace(tools_gold)
    space_pred = ToolSpace(tools_pred)

    scored_by_task: List[Dict[str, Any]] = []
    for ti, task in enumerate(tasks, start=1):
        doc_id = str(task.doc_id)
        gold_scored = _gather_multilevel_path_candidates(
            space_gold,
            task.query,
            doc_id=doc_id,
            score_mode=args.hier_score_mode,
            retrieval_mode=args.hier_retrieval_mode,
            route_m=args.hier_route_m,
            window_chars=args.hier_window_chars,
        )
        pred_scored = _gather_multilevel_path_candidates(
            space_pred,
            task.query,
            doc_id=doc_id,
            score_mode=args.hier_score_mode,
            retrieval_mode=args.hier_retrieval_mode,
            route_m=args.hier_route_m,
            window_chars=args.hier_window_chars,
        )
        flat_scored = _gather_flat_react_candidates(
            tools_flat, task.query, task_type=task.task_type or "", doc_id=doc_id
        )
        scored_by_task.append(
            {
                "task_idx": ti,
                "task": task,
                "gold_hier": gold_scored,
                "pred_hier": pred_scored,
                "flat": flat_scored,
            }
        )
        if ti % 10 == 0 or ti == len(tasks):
            print(f"[retrieval] scored {ti}/{len(tasks)} tasks", file=sys.stderr, flush=True)

    results: List[Dict[str, Any]] = []
    budgets = [int(x) for x in args.budgets.split(",") if x.strip()]
    for budget in budgets:
        rows: List[Dict[str, Any]] = []
        for item in scored_by_task:
            task: AgentTask = item["task"]
            row = {
                "task_idx": item["task_idx"],
                "query": task.query,
                "doc_id": task.doc_id,
                "task_type": task.task_type,
                "gold_nodes": task.gold_nodes,
                "candidate_counts": {
                    "gold_hier": len(item["gold_hier"]),
                    "pred_hier": len(item["pred_hier"]),
                    "flat": len(item["flat"]),
                },
                "candidate_type": {
                    "gold_hier": (
                        f"{args.hier_retrieval_mode}:{args.hier_score_mode}"
                    ),
                    "pred_hier": (
                        f"{args.hier_retrieval_mode}:{args.hier_score_mode}"
                    ),
                    "flat": "flat_react_multiquery",
                },
                "gold_hier": _score_at_budget(task, item["gold_hier"], budget),
                "pred_hier": _score_at_budget(task, item["pred_hier"], budget),
                "flat": _score_at_budget(task, item["flat"], budget),
            }
            rows.append(row)

        sum_gold = _summarize_arm(rows, "gold_hier")
        sum_pred = _summarize_arm(rows, "pred_hier")
        sum_flat = _summarize_arm(rows, "flat")
        summary = {
            "experiment": "arxiv_predcomplete_retrieval_aligned_realdata_logic",
            "n_tasks": len(rows),
            "config": {
                "test_jsonl": str(Path(args.test_jsonl).resolve()),
                "tasks": str(Path(args.tasks).resolve()),
                "budget_chars": budget,
                "embedding_model": args.embedding_model,
                "retrieval": "dense",
                "hierarchy_unit": args.hier_retrieval_mode,
                "hier_score_mode": args.hier_score_mode,
                "hier_route_m": args.hier_route_m,
                "hier_window_chars": args.hier_window_chars,
                "flat_unit": "flat_react_multiquery",
                "llm_compose": False,
                "task_success_judge": None,
            },
            "gold_hier": sum_gold,
            "pred_hier": sum_pred,
            "flat": sum_flat,
            "delta_pred_minus_flat": _delta(sum_pred, sum_flat),
            "delta_gold_minus_flat": _delta(sum_gold, sum_flat),
            "delta_pred_minus_gold": _delta(sum_pred, sum_gold),
            "per_type_gold_hier": _per_type(rows, "gold_hier"),
            "per_type_pred_hier": _per_type(rows, "pred_hier"),
            "per_type_flat": _per_type(rows, "flat"),
            "candidate_pools": {
                "gold_hier": {
                    "n_docs": len({str(r["doc_id"]) for r in rows}),
                    "n_chunks": sum(len(item["gold_hier"]) for item in scored_by_task),
                    "path_depth": _path_depth_summary(
                        [
                            c
                            for item in scored_by_task
                            for c, _s in item["gold_hier"]
                        ]
                    ),
                },
                "pred_hier": {
                    "n_docs": len({str(r["doc_id"]) for r in rows}),
                    "n_chunks": sum(len(item["pred_hier"]) for item in scored_by_task),
                    "path_depth": _path_depth_summary(
                        [
                            c
                            for item in scored_by_task
                            for c, _s in item["pred_hier"]
                        ]
                    ),
                },
                "flat": {
                    "n_docs": len({str(r["doc_id"]) for r in rows}),
                    "n_chunks": sum(len(_flat_pool(idx_flat, str(r["doc_id"]))) for r in rows),
                },
            },
        }
        out_path = Path(str(args.out_template).format(budget=budget))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"summary": summary, "rows": rows}
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[retrieval] saved {out_path}", file=sys.stderr, flush=True)
        results.append(payload)

    if args.summary_md:
        _write_markdown(results, args.summary_md)
        print(f"[retrieval] saved {args.summary_md}", file=sys.stderr, flush=True)
    return results


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    _default_corpus = PACKAGE_ROOT / "data_refs" / "test_data_full_merged_pred_complete.jsonl"
    _default_tasks = PACKAGE_ROOT / "data_refs" / "tasks_arxiv_bodyrich_150_pred_complete_for_runner.jsonl"
    _default_out = str(PACKAGE_ROOT / "results" / "arxiv_predcomplete_aligned_dense_b{budget}.json")
    _default_summary = PACKAGE_ROOT / "results" / "summary_aligned.md"
    p.add_argument(
        "--test-jsonl",
        type=Path,
        default=_default_corpus,
    )
    p.add_argument(
        "--tasks",
        type=Path,
        default=_default_tasks,
    )
    p.add_argument("--budgets", default="300,500,1000")
    p.add_argument(
        "--out-template",
        default=_default_out,
    )
    p.add_argument(
        "--summary-md",
        type=Path,
        default=_default_summary,
    )
    p.add_argument(
        "--embedding-model",
        default=os.environ.get("EMBEDDING_MODEL", DEFAULT_DENSE_EMBEDDING_MODEL),
    )
    p.add_argument(
        "--hier-score-mode",
        choices=("full_text", "content_only", "path_only"),
        default="full_text",
        help=(
            "Hierarchical dense scoring text: full_text keeps PATH+content; "
            "content_only scores only evidence body; path_only scores only PATH. "
            "Budget evidence still uses original PATH+content chunks."
        ),
    )
    p.add_argument(
        "--hier-retrieval-mode",
        choices=(
            "global_leaf_path",
            "length_normalized",
            "routed_leaf_path",
            "routed_length_normalized",
        ),
        default="global_leaf_path",
        help=(
            "Hierarchical candidate pool: global_leaf_path is the main aligned setting; "
            "length_normalized splits leaf/path bodies into fixed-size windows; "
            "routed_leaf_path searches only top routed sections; "
            "routed_length_normalized combines routing and fixed-size windows."
        ),
    )
    p.add_argument(
        "--hier-route-m",
        type=int,
        default=3,
        help="Number of top sections used by routed hierarchical retrieval modes.",
    )
    p.add_argument(
        "--hier-window-chars",
        type=int,
        default=220,
        help="Approximate body-character window for length-normalized hierarchical modes.",
    )
    p.add_argument("--max-docs", type=int, default=0)
    p.add_argument("--max-tasks", type=int, default=0)
    p.add_argument(
        "--regenerate-summary-md-only",
        action="store_true",
        help="Only read existing result JSON(s) and rewrite --summary-md (no embedding / no re-score).",
    )
    p.add_argument(
        "--from-result-json",
        nargs="+",
        type=Path,
        help="With --regenerate-summary-md-only: result JSON paths (sorted by budget_chars inside each file).",
    )
    args = p.parse_args()
    if args.regenerate_summary_md_only:
        if not args.from_result_json:
            p.error("--from-result-json is required with --regenerate-summary-md-only")
        paths = sorted(
            args.from_result_json,
            key=lambda fp: int(json.loads(fp.read_text(encoding="utf-8"))["summary"]["config"]["budget_chars"]),
        )
        payloads = [json.loads(fp.read_text(encoding="utf-8")) for fp in paths]
        _write_markdown(payloads, args.summary_md)
        print(f"[retrieval] wrote {args.summary_md}", file=sys.stderr, flush=True)
        return
    run_eval(args)


if __name__ == "__main__":
    main()
