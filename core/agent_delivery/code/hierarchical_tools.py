"""
层级 RAG 工具：search_small / search_large / expand_parent / route_global / retrieve_facts / search_flat。
与 hierarchical_rag_experiment_plan.md 第 4 节对齐；底层为 CorpusIndex 词重叠检索。
"""
from __future__ import annotations

import re
import random
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .index_retrieval import Chunk, CorpusIndex


@dataclass
class ToolHit:
    chunk: Chunk
    score: float


@dataclass
class HierarchicalTools:
    index: CorpusIndex

    def search_small(
        self,
        query: str,
        k: int,
        *,
        doc_id: Optional[str] = None,
    ) -> List[ToolHit]:
        scored = self.index.search(query, self.index.small_chunks, k, doc_id_filter=doc_id)
        return [ToolHit(chunk=c, score=s) for c, s in scored]

    def search_large(
        self,
        query: str,
        k: int,
        *,
        doc_id: Optional[str] = None,
    ) -> List[ToolHit]:
        scored = self.index.search(query, self.index.large_chunks, k, doc_id_filter=doc_id)
        return [ToolHit(chunk=c, score=s) for c, s in scored]

    def expand_parent(
        self,
        node_id: str,
        *,
        max_chars: int = 2000,
        random_parent: bool = False,
    ) -> str:
        return self.index.expand_parent_text(
            node_id, max_chars=max_chars, random_parent=random_parent
        )

    def route_global(
        self,
        query: str,
        m: int,
        *,
        doc_id: Optional[str] = None,
        random_route: bool = False,
    ) -> List[str]:
        """返回 section_id（节锚点 node_id）。无摘要层时退化为在 small 上按节分组不可用，故需 hierarchical 索引。"""
        pool = self.index.section_summaries
        if not pool:
            # 扁平索引：无节，退化为全库 small 的 doc 级伪节（整文档一节）
            if doc_id and doc_id in self.index._bundles:
                b = self.index._bundles[doc_id]
                if b.lines:
                    from .load_data import line_node_id

                    return [line_node_id(doc_id, b.lines[0].line_id)]
            return []

        if random_route and pool:
            picks = [c for c in pool if (doc_id is None or c.doc_id == doc_id)]
            if not picks:
                return []
            random.shuffle(picks)
            return [p.section_id or p.node_id for p in picks[:m]]

        # 基础召回先放宽，再做 MMR 多样化路由，避免 top-m 都落在近邻同质 section。
        scored = self.index.search(query, pool, max(m * 8, 12), doc_id_filter=doc_id)
        if not scored:
            return []

        def _tok(text: str) -> set:
            return set(re.findall(r"[\w\u4e00-\u9fff]+", (text or "").lower()))

        sec_items: List[Tuple[str, float, set]] = []
        seen = set()
        for c, s in scored:
            sid = c.section_id or c.node_id
            if sid in seen:
                continue
            seen.add(sid)
            sec_items.append((sid, float(s), _tok(c.text)))

        if not sec_items:
            return []

        lambda_raw = 0.75
        selected: List[Tuple[str, float, set]] = []
        while len(selected) < m and sec_items:
            best_idx = 0
            best_score = -1e9
            for i, cand in enumerate(sec_items):
                _, rel, toks = cand
                if not selected:
                    mmr = rel
                else:
                    max_sim = 0.0
                    for _, _, stoks in selected:
                        if not toks or not stoks:
                            continue
                        inter = len(toks & stoks)
                        uni = len(toks | stoks)
                        if uni > 0:
                            max_sim = max(max_sim, inter / uni)
                    mmr = lambda_raw * rel - (1.0 - lambda_raw) * max_sim
                if mmr > best_score:
                    best_score = mmr
                    best_idx = i
            selected.append(sec_items.pop(best_idx))

        return [sid for sid, _, _ in selected]

    def retrieve_facts(
        self,
        section_ids: Sequence[str],
        query: str,
        k_per_section: int,
        *,
        doc_id: Optional[str] = None,
    ) -> List[ToolHit]:
        hits: List[ToolHit] = []
        for sid in section_ids:
            pool = self.index.fact_by_section.get(sid, [])
            if not pool:
                continue
            scored = self.index.search(query, list(pool), k_per_section, doc_id_filter=doc_id)
            for c, s in scored:
                hits.append(ToolHit(chunk=c, score=s))
        hits.sort(key=lambda h: -h.score)
        return hits

    def search_flat(
        self,
        query: str,
        k: int,
        *,
        doc_id: Optional[str] = None,
    ) -> List[ToolHit]:
        pool = self.index.flat_chunks if self.index.flat_chunks else self.index.small_chunks
        scored = self.index.search(query, pool, k, doc_id_filter=doc_id)
        return [ToolHit(chunk=c, score=s) for c, s in scored]
