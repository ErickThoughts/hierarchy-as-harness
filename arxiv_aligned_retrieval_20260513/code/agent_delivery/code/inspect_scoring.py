"""
与 delivery_bundle_inspect_tasks/code/evaluate_inspect_tasks.py 对齐的 Inspect 阅卷逻辑。

用于 runner_bodyrich：将 compose 单行 JSON + 检索轨迹映射为 Inspect 预测结构，再算
content_score 与 evidence_score（evidence_line_ids 对 gold_line_ids 覆盖率）。

content_score：`content_score_for_inspect` — 金标能抽出数字则数值完全匹配（仅 0/1）；否则仅用语义 LLM
（无 API 或解析失败记 0，不再用 token-F1）。`scope_collection` / `regulatory_coverage`：
使用 gold 条目 multiset recall 作为单一分数，不再与语义分或 exact 加权混合。
`multi_hop`：`build_inspect_pred_output` 在仅有单行 `answer` 时按 hop_template 拆子段供 M1/M2 阅卷。
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .judge_llm import _parse_composed_json

NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
WS_RE = re.compile(r"\s+")
_NODE_LINE_RE = re.compile(r":L(\d+)\s*$", re.I)


def norm_text(s: Any) -> str:
    t = str(s or "").strip().lower()
    t = WS_RE.sub(" ", t)
    return t


def has_number(s: Any) -> bool:
    return bool(NUM_RE.search(str(s or "")))


def extract_numbers(s: Any) -> List[str]:
    return NUM_RE.findall(str(s or ""))


def token_f1(pred: str, gold: str) -> float:
    p = [x for x in re.split(r"[，,。；;、\s]+", norm_text(pred)) if x]
    g = [x for x in re.split(r"[，,。；;、\s]+", norm_text(gold)) if x]
    if not p and not g:
        return 1.0
    if not p or not g:
        return 0.0
    pset: Dict[str, int] = {}
    gset: Dict[str, int] = {}
    for x in p:
        pset[x] = pset.get(x, 0) + 1
    for x in g:
        gset[x] = gset.get(x, 0) + 1
    inter = 0
    for k, v in pset.items():
        inter += min(v, gset.get(k, 0))
    precision = inter / max(len(p), 1)
    recall = inter / max(len(g), 1)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def exact_numeric_score(pred: str, gold: str) -> float:
    pn = extract_numbers(pred)
    gn = extract_numbers(gold)
    if not gn:
        return token_f1(pred, gold)
    if pn == gn:
        unit_markers = ["米", "m", "mm", "㎡", "%", "天", "日", "万元", "元"]
        markers_in_gold = [u for u in unit_markers if u in gold]
        if markers_in_gold and not any(u in pred for u in markers_in_gold):
            return 0.5
        return 1.0
    return 0.0


def exact_numeric_score_strict(pred: str, gold: str) -> float:
    """数值完全匹配：数字序列须与金标 extract_numbers 一致；金标含常见单位时预测须带单位。仅 0/1。"""
    pn = extract_numbers(pred)
    gn = extract_numbers(gold)
    if not gn:
        return 0.0
    if pn != gn:
        return 0.0
    unit_markers = ["米", "m", "mm", "㎡", "%", "天", "日", "万元", "元"]
    markers_in_gold = [u for u in unit_markers if u in gold]
    if markers_in_gold and not any(u in pred for u in markers_in_gold):
        return 0.0
    return 1.0


def content_score_for_inspect(pred: str, gold: str) -> float:
    """
    金标含可抽取数字 → exact_numeric_score_strict（仅 0/1）；
    否则 → 仅用语义 LLM（需 OPENAI_API_KEY）；调用失败或无法解析 → 0.0（不回退 token_f1）。
    """
    p = str(pred or "").strip()
    g = str(gold or "").strip()
    if not g:
        return 1.0 if not p else 0.0
    if not p:
        return 0.0
    gn = extract_numbers(g)
    if gn:
        return float(exact_numeric_score_strict(p, g))
    from .judge_llm import _semantic_similarity_answer_llm

    sem = _semantic_similarity_answer_llm(p, g, task_type="inspect_content", hard=False)
    if sem is None:
        return 0.0
    return float(max(0.0, min(1.0, sem)))


_SCOPE_SEP = re.compile(r"[，,、;；\n]+")


def _scope_multiset_recall(pred: str, gold: str) -> float:
    """
    金标条目 multiset 上的召回：sum_k min(pred_cnt, gold_cnt) / sum(gold_cnt)，∈[0,1]。
    分隔与 `scope_regulatory_content_exact` 一致。
    """
    g = str(gold or "").strip()
    p = str(pred or "").strip()
    if not g:
        return 1.0 if not p else 0.0
    if not p:
        return 0.0
    gc = Counter(x.strip() for x in _SCOPE_SEP.split(norm_text(g)) if x.strip())
    if not gc:
        return 0.0
    pc = Counter(x.strip() for x in _SCOPE_SEP.split(norm_text(p)) if x.strip())
    denom = sum(gc.values())
    if denom <= 0:
        return 0.0
    hit = sum(min(int(pc.get(k, 0)), int(v)) for k, v in gc.items())
    return float(hit) / float(denom)


def scope_collection_content_score(pred: str, gold: str) -> float:
    """
    scope / regulatory 单一分数：gold 条目 multiset recall。

    即命中的 gold 条目数 / gold 条目总数。完全匹配自然为 1；
    漏项按比例扣分；多答不额外加分，也不与语义 LLM 或 exact 分数混合。
    """
    return float(max(0.0, min(1.0, _scope_multiset_recall(pred, gold))))


def scope_regulatory_content_exact(pred: str, gold: str) -> float:
    """
    scope / regulatory：完全匹配。
    1) 规范化后去空白，整段相等 → 1；
    2) 否则按常见分隔符切成 multiset（Counter），与金标 multiset 一致 → 1；否则 0。
    """
    p = str(pred or "").strip()
    g = str(gold or "").strip()
    if not g:
        return 1.0 if not p else 0.0
    if not p:
        return 0.0
    if re.sub(r"\s+", "", norm_text(p)) == re.sub(r"\s+", "", norm_text(g)):
        return 1.0
    pc = Counter(x.strip() for x in _SCOPE_SEP.split(norm_text(p)) if x.strip())
    gc = Counter(x.strip() for x in _SCOPE_SEP.split(norm_text(g)) if x.strip())
    if gc and pc == gc:
        return 1.0
    return 0.0


def content_score_for_simple(pred: str, gold: str) -> float:
    """保留旧名：供外部脚本与纯启发式对照；主路径请用 content_score_for_inspect。"""
    if has_number(gold):
        return exact_numeric_score(pred, gold)
    return token_f1(pred, gold)


def to_int_list(v: Any) -> List[int]:
    out: List[int] = []
    if not isinstance(v, list):
        return out
    for x in v:
        if isinstance(x, int):
            out.append(x)
        elif isinstance(x, str) and x.strip().isdigit():
            out.append(int(x.strip()))
    return out


def evidence_coverage(pred_evidence: List[int], gold_evidence: List[int]) -> float:
    if not gold_evidence:
        return 0.0
    p = set(pred_evidence)
    g = set(gold_evidence)
    hit = len(p & g)
    return hit / len(g)


def split_dual_answer(answer: str) -> Dict[str, str]:
    s = (answer or "").strip()
    for sep in ("；", ";"):
        if sep in s:
            parts = [p.strip(" 。；;") for p in s.split(sep) if p.strip(" 。；;")]
            if len(parts) >= 2:
                return {"fact_1": parts[0], "fact_2": parts[1]}
    return {"fact_1": s, "fact_2": ""}


def inspect_compose_format_block(inspect_task: Dict[str, Any], *, max_chars: int = 2400) -> str:
    """
    从 Inspect 任务行摘要「仅与输出形状/字段相关」的文案，供 compose LLM 的 user prompt 注入。
    不包含 judge_config 等判分细则，避免把阅卷规则泄露给模型。
    """
    md = inspect_task.get("metadata") if isinstance(inspect_task.get("metadata"), dict) else {}
    lines: List[str] = []
    lines.append("【输出格式约定（摘自 Inspect 元数据，便于下游解析）】")

    oreq = md.get("output_requirements")
    if isinstance(oreq, list) and oreq:
        lines.append("输出要求：")
        for x in oreq[:16]:
            xs = str(x).strip()
            if xs:
                lines.append(f"- {xs}")

    apol = md.get("answer_policy")
    if isinstance(apol, dict) and apol:
        lines.append("answer_policy（表述形态）：")
        for k, v in list(apol.items())[:12]:
            lines.append(f"- {k}: {v}")

    oc = md.get("output_contract") if isinstance(md.get("output_contract"), dict) else {}
    if not oc and isinstance(inspect_task.get("output_contract"), dict):
        oc = inspect_task["output_contract"]  # type: ignore[index]
    if isinstance(oc, dict) and oc:
        # 不把 Inspect 落库的顶层键（如 final_answer / evidence_line_ids）原样塞进 compose：
        # 与下方 runner schema（answer / items）并存时模型会混淆；evidence_line_ids 也由评测从检索轨迹写入。
        lines.append("output_contract（仅作背景，勿改本条消息末尾的 runner JSON schema）：")
        mode = str(oc.get("mode", "") or "").strip()
        if mode:
            lines.append(f"- mode: {mode}")
        ap = oc.get("additional_properties")
        if ap is not None:
            lines.append(f"- additional_properties: {ap}")

    hop = str(md.get("hop_template", "") or "").strip().upper()
    if hop:
        lines.append(f"multi_hop hop_template: {hop}")
        if hop == "M2":
            lines.append(
                "M2 输出要求：优先输出 condition/outcome/final_answer 三个字段；"
                "condition 写适用条件，outcome 写对应结论或后果，final_answer 汇总二者。"
            )
        elif hop == "M1":
            lines.append(
                "M1 输出要求：优先输出 fact_1/fact_2/final_answer 三个字段；"
                "fact_1 与 fact_2 分别对应两个证据事实，final_answer 汇总回答所有子问。"
            )
        elif hop == "M3":
            lines.append(
                "M3 输出要求：final_answer 必须完整列举问题所问的所有要点；"
                "若输出 fact_1/fact_2，也要在 final_answer 中合并为完整答案。"
            )
    lines.append(
        "与 runner 对齐：请仍只输出本条末尾 schema 要求的一行 JSON。"
        "niche/self_correct 用 answer；multi_hop 用 fact_1/fact_2/final_answer"
        "（M2 可用 condition/outcome/final_answer）；scope/regulatory 用 items。"
        "Inspect 侧的 evidence_line_ids 由评测脚本从检索轨迹自动映射，compose 中不要输出。"
        "勿使用 markdown 代码块。"
    )
    s = "\n".join(lines).strip()
    if len(s) > int(max_chars):
        s = s[: max(0, int(max_chars) - 1)] + "…"
    return s


def load_inspect_registry(paths: Sequence[Path]) -> Dict[str, Dict[str, Any]]:
    """后读入的文件在同 id 上覆盖先读入的。"""
    out: Dict[str, Dict[str, Any]] = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                o = json.loads(line)
                sid = str(o.get("id", "")).strip()
                if sid:
                    out[sid] = o
    return out


def default_inspect_task_paths(kit_root: Path) -> List[Path]:
    rels_primary = (
        "datasets/realdata/tasks_realdata_bodyrich_200_manual_niche_fact_inspect.jsonl",
        "datasets/realdata/tasks_realdata_bodyrich_200_manual_multi_hop_inspect.jsonl",
        "datasets/realdata/tasks_realdata_bodyrich_200_manual_scope_only_mapped_strict_agent_inspect.jsonl",
    )
    rels_fallback = (
        "delivery_bundle_inspect_tasks/data/tasks_realdata_bodyrich_200_manual_niche_fact_inspect.jsonl",
        "delivery_bundle_inspect_tasks/data/tasks_realdata_bodyrich_200_manual_multi_hop_inspect.jsonl",
        "delivery_bundle_inspect_tasks/data/tasks_realdata_bodyrich_200_manual_scope_only_mapped_strict_agent_inspect.jsonl",
    )
    out: List[Path] = []
    for p, fb in zip(rels_primary, rels_fallback):
        p1 = kit_root / p
        out.append(p1 if p1.exists() else (kit_root / fb))
    return out


def evidence_line_ids_from_runner(
    *,
    retrieved_nodes: Sequence[str],
    kept_chunks: Sequence[Any],
    doc_id: Optional[str],
) -> List[int]:
    """从 doc_id:Lk 节点与 Chunk.line_ids 收集整数行号，供 Inspect evidence 覆盖率。"""
    lids: set[int] = set()
    did = (doc_id or "").strip()
    for n in retrieved_nodes or []:
        ns = str(n).strip()
        if did and not ns.startswith(did):
            continue
        m = _NODE_LINE_RE.search(ns)
        if m:
            lids.add(int(m.group(1)))
    for ch in kept_chunks or []:
        cdid = str(getattr(ch, "doc_id", "") or "").strip()
        if did and cdid and cdid != did:
            continue
        for lid in getattr(ch, "line_ids", ()) or ():
            try:
                lids.add(int(lid))
            except (TypeError, ValueError):
                continue
    return sorted(lids)


def _composed_answer_text(obj: Dict[str, Any], composed_fallback: str) -> str:
    return str(obj.get("answer", "") or "").strip() or (composed_fallback or "").strip()


def build_inspect_pred_output(
    composed_answer: str,
    *,
    evidence_line_ids: List[int],
    inspect_task: Dict[str, Any],
) -> Dict[str, Any]:
    """将 runner 的 compose JSON 映射为 evaluate_inspect_tasks.score_sample 期望的 output 结构。"""
    obj = _parse_composed_json(composed_answer) or {}
    if not isinstance(obj, dict):
        obj = {}
    md = inspect_task.get("metadata") if isinstance(inspect_task.get("metadata"), dict) else {}
    ttype = str(md.get("task_type", "") or "").strip()
    eids = list(evidence_line_ids)

    if ttype == "niche_fact":
        tpl = str(md.get("fact_template", "A") or "A").upper()
        if tpl == "C":
            ans = _composed_answer_text(obj, composed_answer)
            inner = ans.strip()
            if inner.startswith("{") and "fact_1" in inner:
                try:
                    d = json.loads(inner)
                    if isinstance(d, dict) and ("fact_1" in d or "fact_2" in d):
                        return {
                            "fact_1": str(d.get("fact_1", "")),
                            "fact_2": str(d.get("fact_2", "")),
                            "evidence_line_ids": eids,
                        }
                except json.JSONDecodeError:
                    pass
            parts = split_dual_answer(ans)
            return {
                "fact_1": parts["fact_1"],
                "fact_2": parts["fact_2"],
                "evidence_line_ids": eids,
            }
        return {"final_answer": _composed_answer_text(obj, composed_answer), "evidence_line_ids": eids}

    if ttype == "multi_hop":
        if isinstance(obj, dict):
            keys_m = ("fact_1", "fact_2", "condition", "outcome", "final_answer")
            picked = {k: str(obj.get(k, "") or "").strip() for k in keys_m if str(obj.get(k, "") or "").strip()}
            if picked:
                picked["evidence_line_ids"] = eids
                return picked
        ans = _composed_answer_text(obj, composed_answer)
        inner = ans.strip()
        if inner.startswith("{") and inner.endswith("}"):
            try:
                d = json.loads(inner)
                if isinstance(d, dict):
                    out = {k: str(d.get(k, "")) for k in ("fact_1", "fact_2", "condition", "outcome", "final_answer") if k in d}
                    if out:
                        out["evidence_line_ids"] = eids
                        return out
            except json.JSONDecodeError:
                pass
        md_hop = str(md.get("hop_template", "M1") or "M1").upper()
        if md_hop == "M1":
            parts = split_dual_answer(ans)
            if parts.get("fact_2"):
                return {
                    "fact_1": parts["fact_1"],
                    "fact_2": parts["fact_2"],
                    "final_answer": ans.strip(),
                    "evidence_line_ids": eids,
                }
        elif md_hop == "M2":
            parts = split_dual_answer(ans)
            if parts.get("fact_2"):
                return {
                    "condition": parts["fact_1"],
                    "outcome": parts["fact_2"],
                    "final_answer": ans.strip(),
                    "evidence_line_ids": eids,
                }
        return {"final_answer": ans, "evidence_line_ids": eids}

    # scope_collection / regulatory_coverage / 其它：用 items 拼接或 answer
    items = obj.get("items")
    if isinstance(items, list) and items:
        joined = "、".join(str(x).strip() for x in items if str(x).strip())
        return {"final_answer": joined, "evidence_line_ids": eids}
    return {"final_answer": _composed_answer_text(obj, composed_answer), "evidence_line_ids": eids}


def score_sample(task: Dict[str, Any], pred_output: Any) -> Tuple[float, float, Dict[str, Any]]:
    """返回 (content_score, evidence_score, extra)。"""
    md = task.get("metadata", {}) if isinstance(task.get("metadata"), dict) else {}
    ttype = md.get("task_type", "")
    target = task.get("target")

    pred_obj = pred_output if isinstance(pred_output, dict) else {"final_answer": str(pred_output or "")}
    pred_evidence = to_int_list(pred_obj.get("evidence_line_ids", []))
    gold_evidence = to_int_list(md.get("gold_line_ids", []))
    ev = evidence_coverage(pred_evidence, gold_evidence)

    extra: Dict[str, Any] = {}

    if ttype == "niche_fact":
        tpl = md.get("fact_template", "A")
        if tpl == "C" and isinstance(target, dict):
            g1 = str(target.get("fact_1", ""))
            g2 = str(target.get("fact_2", ""))
            p1 = str(pred_obj.get("fact_1", ""))
            p2 = str(pred_obj.get("fact_2", ""))
            s1 = content_score_for_inspect(p1, g1)
            s2 = content_score_for_inspect(p2, g2)
            c = (s1 + s2) / 2
            extra["fact_1_score"] = round(s1, 4)
            extra["fact_2_score"] = round(s2, 4)
        else:
            g = str(target if not isinstance(target, dict) else target.get("final_answer", ""))
            p = str(pred_obj.get("final_answer", pred_output if isinstance(pred_output, str) else ""))
            c = content_score_for_inspect(p, g)
    elif ttype == "multi_hop":
        tpl = md.get("hop_template", "M1")
        if isinstance(target, dict):
            if tpl == "M1":
                p1 = str(pred_obj.get("fact_1", "")).strip()
                p2 = str(pred_obj.get("fact_2", "")).strip()
                pf = str(pred_obj.get("final_answer", "")).strip()
                if (not p1 and not p2) and pf:
                    parts = split_dual_answer(pf)
                    p1, p2 = parts["fact_1"].strip(), parts["fact_2"].strip()
                s1 = content_score_for_inspect(p1, str(target.get("fact_1", "")))
                s2 = content_score_for_inspect(p2, str(target.get("fact_2", "")))
                sf = content_score_for_inspect(pf or (p1 + "；" + p2), str(target.get("final_answer", "")))
                c = (s1 + s2 + sf) / 3
                extra["fact_1_score"] = round(s1, 4)
                extra["fact_2_score"] = round(s2, 4)
            elif tpl == "M2":
                c1 = str(pred_obj.get("condition", "")).strip()
                c2 = str(pred_obj.get("outcome", "")).strip()
                pf = str(pred_obj.get("final_answer", "")).strip()
                if (not c1 and not c2) and pf:
                    parts = split_dual_answer(pf)
                    c1, c2 = parts["fact_1"].strip(), parts["fact_2"].strip()
                s1 = content_score_for_inspect(c1, str(target.get("condition", "")))
                s2 = content_score_for_inspect(c2, str(target.get("outcome", "")))
                sf = content_score_for_inspect(pf or (c1 + "；" + c2), str(target.get("final_answer", "")))
                c = (s1 + s2 + sf) / 3
                extra["condition_score"] = round(s1, 4)
                extra["outcome_score"] = round(s2, 4)
            else:
                sf = content_score_for_inspect(str(pred_obj.get("final_answer", "")), str(target.get("final_answer", "")))
                gp = target.get("evidence_points", [])
                if isinstance(gp, list) and gp:
                    pp = pred_obj.get("evidence_points", [])
                    if not isinstance(pp, list):
                        pp = []
                    hit = 0
                    for g in gp:
                        gtxt = str(g)
                        if any(content_score_for_inspect(str(p), gtxt) >= 0.8 for p in pp):
                            hit += 1
                    sp = hit / len(gp)
                    c = (sf + sp) / 2
                    extra["points_score"] = round(sp, 4)
                else:
                    c = sf
        else:
            c = content_score_for_inspect(str(pred_obj.get("final_answer", "")), str(target))
    elif ttype in ("scope_collection", "regulatory_coverage"):
        p = str(pred_obj.get("final_answer", pred_output if isinstance(pred_output, str) else ""))
        g = str(target)
        c = scope_collection_content_score(p, g)
    else:
        p = str(pred_obj.get("final_answer", pred_output if isinstance(pred_output, str) else ""))
        g = str(target)
        c = content_score_for_inspect(p, g)

    return round(float(c), 4), round(float(ev), 4), extra
