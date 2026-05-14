"""
从 test_data_full 风格 JSONL 加载文档，构建黄金树 / 预测树 / 扁平切块。
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class LineRecord:
    doc_id: str
    line_id: int
    content: str
    gold_level: int
    pred_level: Optional[int] = None  # T2：若与 gold 不同则来自预测 JSONL


@dataclass
class DocBundle:
    doc_id: str
    lines: List[LineRecord]
    levels_for_tree: List[int]  # 用于建树：T1 用 gold，T2 用 pred


def load_test_groups(path: Path | str) -> Dict[str, List[dict]]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            groups[str(d["doc_id"])].append(d)
    for k in groups:
        groups[k] = sorted(groups[k], key=lambda x: int(x.get("line_id", 0)))
    return dict(groups)


def groups_to_bundles(
    groups: Dict[str, List[dict]],
    *,
    tree_source: str,
    pred_groups: Optional[Dict[str, List[dict]]] = None,
) -> List[DocBundle]:
    """
    tree_source: "gold" | "pred" | "flat"
    - gold: levels_for_tree = gold_level
    - pred: 需要 pred_groups（同 doc_id/line_id，字段 pred_level 或 predicted_level）；
      严格要求每一行都有预测层级，缺失则直接报错（fail-fast）。
    - flat: levels_for_tree 全 0（仅用于占位，建树时不应使用）
    """
    bundles: List[DocBundle] = []
    for doc_id in sorted(groups.keys()):
        rows = groups[doc_id]
        lines: List[LineRecord] = []
        levels: List[int] = []
        pred_map: Dict[int, int] = {}
        if pred_groups and doc_id in pred_groups:
            for r in pred_groups[doc_id]:
                lid = int(r["line_id"])
                pl = r.get("pred_level")
                if pl is None and r.get("predicted_level") is not None:
                    pl = int(r["predicted_level"])
                if pl is not None:
                    pred_map[lid] = int(pl)

        missing_pred_line_ids: List[int] = []
        for r in rows:
            lid = int(r["line_id"])
            gl = int(r.get("gold_level", 0))
            predicted_level = pred_map.get(lid)
            pr = LineRecord(
                doc_id=doc_id,
                line_id=lid,
                content=str(r.get("content", "")),
                gold_level=gl,
                pred_level=predicted_level,
            )
            lines.append(pr)
            if tree_source == "gold":
                levels.append(gl)
            elif tree_source == "pred":
                if predicted_level is not None:
                    levels.append(predicted_level)
                else:
                    missing_pred_line_ids.append(lid)
                    levels.append(0)
            else:
                levels.append(0)
        if tree_source == "pred" and missing_pred_line_ids:
            head = ",".join(f"L{x}" for x in missing_pred_line_ids[:10])
            tail = "..." if len(missing_pred_line_ids) > 10 else ""
            raise ValueError(
                f"pred tree requires complete pred levels; doc_id={doc_id} missing "
                f"{len(missing_pred_line_ids)} lines: {head}{tail}"
            )
        bundles.append(DocBundle(doc_id=doc_id, lines=lines, levels_for_tree=levels))
    return bundles


def build_parent_pointers(levels: List[int]) -> List[Optional[int]]:
    """栈式建树：返回每个行下标的父行下标（文档内 0..n-1），根行为 None。"""
    n = len(levels)
    parents: List[Optional[int]] = [None] * n
    stack: List[Tuple[int, int]] = [(-1, -1)]
    for i in range(n):
        lev = levels[i]
        while len(stack) > 1 and stack[-1][1] >= lev:
            stack.pop()
        p = stack[-1][0]
        parents[i] = p if p >= 0 else None
        stack.append((i, lev))
    return parents


def line_node_id(doc_id: str, line_id: int) -> str:
    return f"{doc_id}:L{line_id}"


def bundles_from_paths(
    test_path: Path,
    *,
    tree_source: str,
    pred_path: Optional[Path] = None,
    max_docs: int = 0,
) -> List[DocBundle]:
    groups = load_test_groups(test_path)
    doc_ids = sorted(groups.keys())
    if max_docs > 0:
        doc_ids = doc_ids[:max_docs]
        groups = {d: groups[d] for d in doc_ids}
    pred_groups = load_test_groups(pred_path) if pred_path and pred_path.exists() else None
    if tree_source == "pred" and pred_groups is None:
        raise ValueError("tree_source=pred 时需要提供有效的 pred_path JSONL（含 pred_level 或 predicted_level）")
    return groups_to_bundles(groups, tree_source=tree_source, pred_groups=pred_groups)
