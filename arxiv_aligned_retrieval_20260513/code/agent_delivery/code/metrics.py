"""
检索指标：Precision@k、Coverage；生成侧可选 ROUGE-L / METEOR。
"""
from __future__ import annotations

import math
import re
from typing import Iterable, List, Optional, Sequence, Set, Tuple

_ANSWER_STOP = frozenset(
    "the a an and or that this was were from with for not paper "
    "cannot determined according into about which their there "
    "these those they have been were being".split()
)


def answer_keyword_recall_in_evidence(
    evidence: str, gold_answer: str, min_words: int = 2
) -> Optional[float]:
    """
    参考答案中较长英文词在证据文本中出现的比例（0~1）。
    用于体现「父链/更长证据」是否更易覆盖可验证表述；跳过无解题与过短答案。
    """
    ga = (gold_answer or "").strip()
    if len(ga) < 12:
        return None
    if "cannot be determined" in ga.lower():
        return None
    words = re.findall(r"[A-Za-z]{4,}", ga.lower())
    words = [w for w in words if w not in _ANSWER_STOP]
    if len(words) < min_words:
        return None
    ev = evidence.lower()
    hit = sum(1 for w in words if w in ev)
    return hit / len(words)


def precision_at_k(retrieved_node_ids: Sequence[str], gold_node_ids: Set[str], k: int) -> float:
    """前 k 个检索结果中命中金标节点的比例。"""
    if k <= 0:
        return 0.0
    top = list(retrieved_node_ids)[:k]
    if not top:
        return 0.0
    hits = sum(1 for n in top if n in gold_node_ids)
    return hits / min(k, len(top))


def coverage(retrieved_node_ids: Iterable[str], gold_node_ids: Set[str]) -> float:
    """|R ∩ G| / |G|；G 为空时返回 1.0。"""
    g = set(gold_node_ids)
    if not g:
        return 1.0
    r = set(retrieved_node_ids)
    return len(r & g) / len(g)


def hit_at_k(retrieved_node_ids: Sequence[str], gold_node_ids: Set[str], k: int) -> float:
    """前 k 个是否至少命中 1 个金标节点（命中=1，否则=0）。"""
    if k <= 0 or not retrieved_node_ids:
        return 0.0
    top = list(retrieved_node_ids)[:k]
    return 1.0 if any(n in gold_node_ids for n in top) else 0.0


def mrr(retrieved_node_ids: Sequence[str], gold_node_ids: Set[str]) -> float:
    """Mean Reciprocal Rank 的单题值：第一个命中位置的倒数。"""
    if not retrieved_node_ids or not gold_node_ids:
        return 0.0
    for i, n in enumerate(retrieved_node_ids, start=1):
        if n in gold_node_ids:
            return 1.0 / float(i)
    return 0.0


def ndcg_at_k(
    retrieved_node_ids: Sequence[str], gold_node_ids: Set[str], k: int = 10
) -> float:
    """二值相关的 nDCG@k（命中为1，未命中为0）。"""
    if k <= 0:
        return 0.0
    top = list(retrieved_node_ids)[:k]
    if not top or not gold_node_ids:
        return 0.0
    dcg = 0.0
    for i, n in enumerate(top, start=1):
        if n in gold_node_ids:
            dcg += 1.0 / (1.0 if i == 1 else float(math.log2(i)))
    ideal_hits = min(k, len(gold_node_ids))
    if ideal_hits <= 0:
        return 0.0
    idcg = 0.0
    for i in range(1, ideal_hits + 1):
        idcg += 1.0 / (1.0 if i == 1 else float(math.log2(i)))
    return dcg / idcg if idcg > 0 else 0.0


def retrieval_metrics(
    retrieved_node_ids: Sequence[str],
    gold_node_ids: Sequence[str],
    k_list: Sequence[int] = (1, 3, 5, 8),
) -> dict:
    gold = set(gold_node_ids)
    out = {
        "coverage": coverage(retrieved_node_ids, gold),
        "mrr": mrr(retrieved_node_ids, gold),
        "ndcg@10": ndcg_at_k(retrieved_node_ids, gold, k=10),
        "hit@5": hit_at_k(retrieved_node_ids, gold, k=5),
    }
    for k in k_list:
        out[f"precision@{k}"] = precision_at_k(retrieved_node_ids, gold, k)
    return out


def rouge_l_f1(candidate: str, reference: str) -> Optional[float]:
    try:
        from rouge_score import rouge_scorer  # type: ignore
    except ImportError:
        return None
    scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
    return scorer.score(reference, candidate)["rougeL"].fmeasure


def meteor_score(candidate: str, reference: str) -> Optional[float]:
    try:
        import nltk  # type: ignore
        from nltk.translate.meteor_score import meteor_score as _meteor  # type: ignore

        try:
            nltk.data.find("corpora/wordnet")
        except LookupError:
            nltk.download("wordnet", quiet=True)
            nltk.download("omw-1.4", quiet=True)
    except ImportError:
        return None
    ref = reference.split()
    hyp = candidate.split()
    if not ref or not hyp:
        return 0.0
    return float(_meteor([ref], hyp))


def checklist_coverage(candidate: str, checklist: Sequence[str]) -> float:
    """要点是否出现在候选答案中（简单子串匹配，可换 embedding）。"""
    if not checklist:
        return 1.0
    c = candidate.lower()
    hit = sum(1 for p in checklist if p.strip() and p.strip().lower() in c)
    return hit / len(checklist)
