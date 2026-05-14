"""从 tasks JSONL 加载 AgentTask（runner_bodyrich 专用，避免依赖旧 runner/agent_loop）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .types import AgentTask


def _load_tasks(path: Path) -> List[AgentTask]:
    rows: List[AgentTask] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            query = str(d.get("query") or d.get("question") or "").strip()
            if not query:
                continue
            gold = d.get("gold_nodes") or d.get("gold_node_ids") or []
            if isinstance(gold, str):
                gold = [gold]
            insp = d.get("inspect_id")
            inspect_id = str(insp).strip() if insp is not None and str(insp).strip() else None
            cfh = str(d.get("compose_format_hint") or "").strip()
            rows.append(
                AgentTask(
                    query=query,
                    doc_id=str(d["doc_id"]) if d.get("doc_id") is not None else None,
                    gold_nodes=[str(x) for x in gold],
                    gold_answer=str(d.get("gold_answer") or ""),
                    task_type=str(d.get("task_type") or "unknown"),
                    cross_section=d.get("cross_section"),
                    inspect_id=inspect_id,
                    compose_format_hint=cfh,
                )
            )
    return rows
