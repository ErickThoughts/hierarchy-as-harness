"""
交付包内精简版 `agent_delivery.code`：仅导出 Agent 实验所需子模块，不依赖 `policies` 等完整 RAG 实验代码。
"""

__version__ = "0.1.0-delivery"

from .load_data import (
    DocBundle,
    LineRecord,
    bundles_from_paths,
    build_parent_pointers,
    line_node_id,
    load_test_groups,
)
from .index_retrieval import CorpusIndex, merge_evidence
from .hierarchical_tools import HierarchicalTools
from .metrics import (
    answer_keyword_recall_in_evidence,
    retrieval_metrics,
    coverage,
    precision_at_k,
)

__all__ = [
    "__version__",
    "DocBundle",
    "LineRecord",
    "bundles_from_paths",
    "build_parent_pointers",
    "line_node_id",
    "load_test_groups",
    "CorpusIndex",
    "merge_evidence",
    "HierarchicalTools",
    "answer_keyword_recall_in_evidence",
    "retrieval_metrics",
    "coverage",
    "precision_at_k",
]
