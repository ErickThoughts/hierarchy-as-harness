from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ..code.index_retrieval import Chunk


@dataclass
class AgentTask:
    query: str
    doc_id: Optional[str]
    gold_nodes: List[str]
    gold_answer: str = ""
    task_type: str = "unknown"
    # 可选：用于 stratified 子集过滤（与 tasks JSONL 字段对齐）
    cross_section: Optional[bool] = None
    # 可选：与 Inspect 任务 JSONL 的 id 对齐，供 --inspect-judge 阅卷
    inspect_id: Optional[str] = None
    # 可选：直接写入 compose LLM 的格式说明（优先于按 inspect_id 从库生成）
    compose_format_hint: str = ""


@dataclass
class AgentStep:
    step_idx: int
    action: str
    detail: Dict[str, object] = field(default_factory=dict)


@dataclass
class AgentTrace:
    query: str
    doc_id: Optional[str]
    representation: str
    steps: List[AgentStep]
    retrieved_nodes: List[str]
    evidence_text: str
    final_answer: str
    stop_reason: str


@dataclass
class EpisodeResult:
    """runner_bodyrich / react_agent 共用的单任务 episode 产物。"""

    representation: str
    steps: List[AgentStep]
    scored_chunks: List[Tuple["Chunk", float]]
    kept_chunks: List["Chunk"]
    evidence_text: str
    evidence_chars_actual: int
    retrieved_nodes: List[str]
    composed_answer: str = ""
    section_ids: List[str] = field(default_factory=list)
    trajectory_length: int = 0
    truncated_last: bool = False
    refusal_events: List[Dict[str, object]] = field(default_factory=list)
