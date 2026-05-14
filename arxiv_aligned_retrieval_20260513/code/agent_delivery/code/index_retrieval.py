"""
小块 / 大块 / 扁平索引 + 检索后端：`dense`（sentence-transformers）。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .embedding_backend import DEFAULT_DENSE_EMBEDDING_MODEL, mmr_select_indices
from .load_data import DocBundle, LineRecord, build_parent_pointers, line_node_id


@dataclass
class Chunk:
    node_id: str
    doc_id: str
    text: str
    line_ids: Tuple[int, ...]  # 包含的行 id
    section_id: Optional[str] = None  # 命题 B：所属节（level-1 锚点行 id）


class CorpusIndex:
    """全局池：跨文档小块、大块、节摘要、扁平块。"""

    def __init__(self) -> None:
        self.small_chunks: List[Chunk] = []
        self.large_chunks: List[Chunk] = []
        self.flat_chunks: List[Chunk] = []
        self.section_summaries: List[Chunk] = []  # 摘要层：节标题 + 首段摘要
        self.fact_by_section: Dict[str, List[Chunk]] = {}  # section_id -> 小块
        # 小块 node_id -> 文档内行下标（在 bundle.lines 中的 index）
        self._node_to_doc_line: Dict[str, Tuple[str, int]] = {}
        self._doc_parents: Dict[str, List[Optional[int]]] = {}
        self._bundles: Dict[str, DocBundle] = {}
        # dense only
        self.retrieval_backend: str = "dense"
        self.embedding_model_name: str = DEFAULT_DENSE_EMBEDDING_MODEL
        self._dense_model = None
        # 稳定键（chunk node_id 元组）-> 与 pool 等长的归一化向量矩阵。
        # 禁止用 id(list)：list(pool) 等短命列表的 id 会被 CPython 复用，导致错维缓存命中。
        self._pool_emb_cache: Dict[Tuple[str, ...], object] = {}

    def _ensure_dense_model(self):
        if self._dense_model is None:
            from .embedding_backend import get_dense_encoder

            self._dense_model = get_dense_encoder(self.embedding_model_name)

    def _embeddings_for_pool(self, pool: List[Chunk]):
        key = tuple(c.node_id for c in pool)
        if key not in self._pool_emb_cache:
            self._ensure_dense_model()
            from .embedding_backend import encode_chunks_normalized

            self._pool_emb_cache[key] = encode_chunks_normalized(
                self._dense_model, pool, batch_size=64
            )
        return self._pool_emb_cache[key]

    @classmethod
    def from_bundles(
        cls,
        bundles: Sequence[DocBundle],
        *,
        tree_mode: str,
        large_merge_lines: int = 12,
        flat_window: int = 8,
        retrieval_backend: str = "dense",
        embedding_model: str = DEFAULT_DENSE_EMBEDDING_MODEL,
    ) -> "CorpusIndex":
        """
        tree_mode: "hierarchical" | "flat"
        - hierarchical: 用 levels_for_tree 建树、大块按节、摘要层
        - flat: 仅填充 flat_chunks + small_chunks（每行一小块），无 parent
        """
        idx = cls()
        for b in bundles:
            idx._bundles[b.doc_id] = b
            lines = b.lines
            levels = b.levels_for_tree
            n = len(lines)

            if tree_mode == "hierarchical" and n > 0:
                parents = build_parent_pointers(levels)
                idx._doc_parents[b.doc_id] = parents

                # 小块：每行
                for j, rec in enumerate(lines):
                    nid = line_node_id(b.doc_id, rec.line_id)
                    ch = Chunk(
                        node_id=nid,
                        doc_id=b.doc_id,
                        text=rec.content,
                        line_ids=(rec.line_id,),
                        section_id=_section_anchor_for_line(lines, levels, j),
                    )
                    idx.small_chunks.append(ch)
                    idx._node_to_doc_line[nid] = (b.doc_id, j)

                # 大块：滑动窗口若干行
                for start in range(0, n, large_merge_lines):
                    part = lines[start : start + large_merge_lines]
                    if not part:
                        continue
                    lids = tuple(r.line_id for r in part)
                    text = "\n".join(r.content for r in part)
                    nid = f"{b.doc_id}:WIN{start}"
                    idx.large_chunks.append(
                        Chunk(node_id=nid, doc_id=b.doc_id, text=text, line_ids=lids)
                    )

                # 节（level==1 的锚点）与摘要层 + 事实按节
                anchors = [j for j in range(n) if levels[j] == 1]
                if not anchors and n > 0:
                    anchors = [0]
                for ai, start_j in enumerate(anchors):
                    end_j = anchors[ai + 1] if ai + 1 < len(anchors) else n
                    sec_lines = lines[start_j:end_j]
                    sec_id = line_node_id(b.doc_id, lines[start_j].line_id)
                    title = lines[start_j].content[:200]
                    body_preview = "\n".join(r.content for r in sec_lines[:3])[:500]
                    summary_text = f"{title}\n{body_preview}"
                    idx.section_summaries.append(
                        Chunk(
                            node_id=f"{sec_id}__summary",
                            doc_id=b.doc_id,
                            text=summary_text,
                            line_ids=tuple(r.line_id for r in sec_lines),
                            section_id=sec_id,
                        )
                    )
                    sec_small: List[Chunk] = []
                    for j in range(start_j, end_j):
                        rec = lines[j]
                        nid = line_node_id(b.doc_id, rec.line_id)
                        c = Chunk(
                            node_id=nid,
                            doc_id=b.doc_id,
                            text=rec.content,
                            line_ids=(rec.line_id,),
                            section_id=sec_id,
                        )
                        sec_small.append(c)
                    idx.fact_by_section[sec_id] = sec_small
            else:
                # flat：无树
                idx._doc_parents[b.doc_id] = [None] * n
                for j, rec in enumerate(lines):
                    nid = line_node_id(b.doc_id, rec.line_id)
                    idx.small_chunks.append(
                        Chunk(
                            node_id=nid,
                            doc_id=b.doc_id,
                            text=rec.content,
                            line_ids=(rec.line_id,),
                        )
                    )
                    idx._node_to_doc_line[nid] = (b.doc_id, j)
                for start in range(0, n, large_merge_lines):
                    part = lines[start : start + large_merge_lines]
                    if not part:
                        continue
                    lids = tuple(r.line_id for r in part)
                    text = "\n".join(r.content for r in part)
                    idx.large_chunks.append(
                        Chunk(
                            node_id=f"{b.doc_id}:WIN{start}",
                            doc_id=b.doc_id,
                            text=text,
                            line_ids=lids,
                        )
                    )
                for start in range(0, n, flat_window):
                    part = lines[start : start + flat_window]
                    if not part:
                        continue
                    text = "\n".join(r.content for r in part)
                    idx.flat_chunks.append(
                        Chunk(
                            node_id=f"{b.doc_id}:FLAT{start}",
                            doc_id=b.doc_id,
                            text=text,
                            line_ids=tuple(r.line_id for r in part),
                        )
                    )

        if retrieval_backend != "dense":
            raise ValueError(f"unsupported retrieval_backend={retrieval_backend!r}; only 'dense' is supported")
        idx.retrieval_backend = retrieval_backend
        idx.embedding_model_name = embedding_model
        return idx

    def search(
        self,
        query: str,
        pool: List[Chunk],
        k: int,
        doc_id_filter: Optional[str] = None,
    ) -> List[Tuple[Chunk, float]]:
        if self.retrieval_backend != "dense":
            raise ValueError(f"unsupported retrieval_backend={self.retrieval_backend!r}; only 'dense' is supported")
        if not pool:
            return []
        import numpy as np

        from .embedding_backend import dense_scores_for_pool

        mat = self._embeddings_for_pool(pool)
        dense_scored = dense_scores_for_pool(
            query,
            pool,
            doc_id_filter,
            model=self._dense_model,
            emb_matrix=mat,
        )
        if k <= 0:
            return []
        if not dense_scored:
            return []

        # 仅当请求截断 top-k（k 小于候选规模）时做 MMR，避免同质高分挤占名额（toolspace / 工具侧检索）。
        # gather_flat / gather_hier 传入 k=len(pool) 时路径不变。BODYRICH_DENSE_MMR=0 可关闭。
        want_mmr = os.environ.get("BODYRICH_DENSE_MMR", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if not want_mmr or k >= len(dense_scored):
            return dense_scored[:k]

        fetch_mult = int(os.environ.get("BODYRICH_MMR_FETCH_MULT", "6").strip() or "6")
        fetch_mult = max(fetch_mult, 2)
        fetch_n = min(len(dense_scored), max(k * fetch_mult, k + 8))
        head = dense_scored[:fetch_n]

        node_to_row = {c.node_id: i for i, c in enumerate(pool)}
        rows: List[int] = []
        rel_list: List[float] = []
        for c, sc in head:
            ri = node_to_row.get(c.node_id)
            if ri is None:
                continue
            rows.append(ri)
            rel_list.append(float(sc))
        if len(rows) <= k:
            return [(pool[r], rel_list[i]) for i, r in enumerate(rows)]

        emb_sub = np.asarray(mat[rows], dtype=np.float64)
        rel = np.asarray(rel_list, dtype=np.float64)
        lam = float(os.environ.get("BODYRICH_MMR_LAMBDA", "0.68").strip() or "0.68")
        lam = max(0.0, min(1.0, lam))
        pick_local = mmr_select_indices(rel, emb_sub, k_out=k, lambda_mult=lam)
        out: List[Tuple[Chunk, float]] = []
        for li in pick_local:
            out.append((pool[rows[li]], rel_list[li]))
        return out

    def ancestor_line_node_ids(self, node_id: str) -> List[str]:
        """从当前行小块沿 parent 链上至根，返回 node_id 列表（含自身，叶→根顺序）。"""
        if node_id not in self._node_to_doc_line:
            return []
        doc_id, j = self._node_to_doc_line[node_id]
        parents = self._doc_parents.get(doc_id, [])
        b = self._bundles.get(doc_id)
        if not b or j >= len(b.lines):
            return []
        out: List[str] = []
        cur: Optional[int] = j
        visited = 0
        while cur is not None and visited < len(b.lines) + 1:
            rec = b.lines[cur]
            out.append(line_node_id(doc_id, rec.line_id))
            p = parents[cur] if cur < len(parents) else None
            cur = p
            visited += 1
        return out

    def expand_parent_text(
        self,
        node_id: str,
        *,
        max_chars: int = 2000,
        random_parent: bool = False,
    ) -> str:
        """小块命中后拉父链文本；random_parent 消融用。"""
        if node_id not in self._node_to_doc_line:
            return ""
        doc_id, j = self._node_to_doc_line[node_id]
        parents = self._doc_parents.get(doc_id, [])
        if j >= len(parents):
            return ""
        parts: List[str] = []
        cur: Optional[int] = j
        visited = 0
        while cur is not None and visited < 5:
            b = self._bundles.get(doc_id)
            if not b or cur >= len(b.lines):
                break
            parts.append(b.lines[cur].content)
            cur = parents[cur] if cur < len(parents) else None
            visited += 1
        text = "\n".join(reversed(parts))
        if random_parent and self.small_chunks:
            import random

            other = random.choice(self.small_chunks)
            if other.node_id != node_id:
                text = other.text[: max_chars // 2] + "\n" + text[: max_chars // 2]
        return text[:max_chars]


def _section_anchor_for_line(lines: List[LineRecord], levels: List[int], j: int) -> str:
    """当前行所属 level-1 节锚点的 node_id。"""
    if j >= len(levels):
        return line_node_id(lines[0].doc_id, lines[0].line_id)
    doc_id = lines[j].doc_id
    for t in range(j, -1, -1):
        if levels[t] == 1:
            return line_node_id(doc_id, lines[t].line_id)
    return line_node_id(doc_id, lines[0].line_id)


def merge_evidence(chunks: Sequence[Chunk], max_chars: int) -> str:
    out: List[str] = []
    used = 0
    for c in chunks:
        block = f"[{c.node_id}]\n{c.text}"
        if used + len(block) > max_chars:
            remain = max_chars - used
            if remain > 50:
                out.append(block[:remain])
            break
        out.append(block)
        used += len(block) + 1
    return "\n\n".join(out)
