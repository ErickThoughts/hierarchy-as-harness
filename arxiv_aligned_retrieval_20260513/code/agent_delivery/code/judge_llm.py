"""
Plan §4.3：按 task_type 的 task_success 标量 + 可选 LLM 语义兜底。

结构化 compose 输出为单行 JSON（由 compose_llm.compose_answer_llm 生成，与 compose_structured_string 同 schema）；
本模块优先 `json.loads`，再按类型计算：

- scope_collection / regulatory_coverage：预测 `items` 集合 vs **gold_answer 切分 ∪ gold_nodes 规范化键** 的 F1（对齐 plan「项 vs 证据行」）
- cross_section_conflict / cross_clause_conflict：claims 对与 gold 两段话 + **evidence 中 gold_nodes 覆盖率** 混合分
- niche_fact / multi_hop：默认 answer vs gold_answer 的 token-F1；见下「语义主评测」
- self_correct：token-F1 ≥ 阈值 → 1.0 否则 0.0（final_success）
- 其它：keyword 风格回退

`JUDGE_USE_LLM=1` 且 token_F1<semantic_threshold 时，对 niche/multi/self 可调用语义兜底。

**语义主评测（不比字符串重叠）**：设置 `JUDGE_SEMANTIC_PRIMARY=1` 时，须配置 `OPENAI_API_KEY`（及可选
`OPENAI_BASE_URL`、`JUDGE_MODEL`）。对 niche_fact / multi_hop / scope_collection / regulatory_coverage /
self_correct 以及 JSON 形式的 cross_section_conflict，**仅**用 LLM 输出 0–1 语义分；**无 API、未安装
openai、或 LLM 返回无法解析时直接 `RuntimeError` 退出**，不回退到 token-F1 / 集合 F1。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Set

from .llm_config import load_llm_env


def _token_f1(pred: str, gold: str) -> float:
    def toks(s: str) -> Set[str]:
        s = re.sub(r"\s+", " ", (s or "").lower()).strip()
        if not s:
            return set()
        out: Set[str] = set()
        for w in re.findall(r"[\w\u4e00-\u9fff]+", s):
            if len(w) >= 2:
                out.add(w)
        for i in range(len(s) - 1):
            out.add(s[i : i + 2])
        return out

    p, g = toks(pred), toks(gold)
    if not p and not g:
        return 1.0
    if not p or not g:
        return 0.0
    inter = len(p & g)
    prec = inter / len(p)
    rec = inter / len(g)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def _semantic_primary_enabled() -> bool:
    return os.environ.get("JUDGE_SEMANTIC_PRIMARY", "").strip().lower() in ("1", "true", "yes", "on")


def _require_semantic_api() -> None:
    """语义主评测开启时必须有 OpenAI 兼容客户端，否则立即失败。"""
    load_llm_env()
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        raise RuntimeError(
            "JUDGE_SEMANTIC_PRIMARY 已开启但未配置 OPENAI_API_KEY，语义评测无法运行。"
        )
    try:
        import openai  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "JUDGE_SEMANTIC_PRIMARY 已开启但未安装 openai 包，无法调用语义评测。"
        ) from e


def _semantic_score_json_llm(
    *,
    system_prompt: str,
    user_body: str,
    max_tokens: int = 80,
    hard: bool = False,
) -> Optional[float]:
    """调用 OpenAI 兼容接口，要求模型只输出含 score 的 JSON。hard=True 时任何失败抛 RuntimeError。"""
    load_llm_env()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        if hard:
            raise RuntimeError("语义评测需要 OPENAI_API_KEY。")
        return None
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        if hard:
            raise RuntimeError("语义评测需要安装 openai 包。") from e
        return None
    base = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = os.environ.get("JUDGE_MODEL", "gpt-4o-mini").strip()
    client = OpenAI(api_key=key, base_url=base)
    try:
        rsp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_body},
            ],
            temperature=0.0,
            max_tokens=max_tokens,
        )
    except Exception as e:
        if hard:
            raise RuntimeError(f"语义评测 LLM 调用失败: {e}") from e
        return None
    txt = (rsp.choices[0].message.content or "").strip()
    if not txt:
        if hard:
            raise RuntimeError("语义评测：LLM 返回空内容。")
        return None
    m = re.search(r"\{[\s\S]*?\}", txt)
    if not m:
        if hard:
            raise RuntimeError(f"语义评测：无法从 LLM 输出中解析 JSON。原始输出: {txt[:500]!r}")
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        if hard:
            raise RuntimeError(f"语义评测：JSON 解析失败。片段: {m.group(0)!r}") from e
        return None
    if not isinstance(obj, dict):
        if hard:
            raise RuntimeError("语义评测：解析结果不是 JSON 对象。")
        return None
    raw = obj.get("score")
    if raw is None:
        if hard:
            raise RuntimeError(f"语义评测：JSON 中缺少 score 字段。内容: {obj!r}")
        return None
    try:
        s = float(raw)
    except (TypeError, ValueError) as e:
        if hard:
            raise RuntimeError(f"语义评测：score 不是数字: {raw!r}") from e
        return None
    if s != s:  # NaN
        if hard:
            raise RuntimeError("语义评测：score 为 NaN。")
        return None
    return max(0.0, min(1.0, s))


def _semantic_similarity_answer_llm(
    pred: str, gold: str, *, task_type: str, hard: bool = False
) -> Optional[float]:
    """判断模型答案与金标在事实与结论上是否一致；表述可不同。返回 [0,1]。hard 时 LLM 失败抛错。"""
    pred = (pred or "").strip()
    gold = (gold or "").strip()
    if not gold:
        return 1.0 if not pred else 0.0
    if not pred:
        return 0.0
    sys_p = (
        "你是阅卷助手。根据「金标参考」对「模型答案」在事实、数值、结论上是否一致打分。"
        "措辞不同但含义一致应给高分；部分正确给中间分；事实错误或遗漏要点给低分。"
        "只输出一行 JSON，格式严格为：{\"score\":0.75}，score 为 0 到 1 的小数，不要其它字段。"
    )
    body = f"任务类型: {task_type}\n\n金标参考:\n{gold}\n\n模型答案:\n{pred}"
    return _semantic_score_json_llm(system_prompt=sys_p, user_body=body, hard=hard)


def _semantic_similarity_scope_llm(
    pred_items: List[str],
    gold: str,
    *,
    gold_nodes: Optional[Sequence[str]],
    hard: bool = False,
) -> Optional[float]:
    """范围/条目类：从语义上判断模型列出的项是否覆盖金标要求的含义。"""
    gold = (gold or "").strip()
    if not gold:
        return 1.0 if not pred_items else 0.0
    nodes = ", ".join(str(x) for x in (gold_nodes or []) if str(x).strip())
    items_txt = "\n".join(f"- {x}" for x in pred_items[:64]) if pred_items else "(无条目)"
    sys_p = (
        "你是阅卷助手。金标给出应覆盖的要点或范围描述（可含证据节点说明）。"
        "判断「模型抽取的条目列表」在语义上是否覆盖这些要点；不要求字面相同。"
        "只输出一行 JSON：{\"score\":0.8}，score 为 0 到 1 的小数。"
    )
    body = f"金标参考:\n{gold}\n\n证据节点提示:\n{nodes or '(无)'}\n\n模型抽取条目:\n{items_txt}"
    return _semantic_score_json_llm(system_prompt=sys_p, user_body=body, max_tokens=100, hard=hard)


def _semantic_similarity_conflict_json_llm(obj: Dict[str, Any], gold: str, *, hard: bool = False) -> Optional[float]:
    """冲突类 JSON 输出与金标叙述的整体语义一致度。"""
    gold = (gold or "").strip()
    if not gold:
        return 1.0
    try:
        pred_txt = json.dumps(obj, ensure_ascii=False, indent=2)[:12000]
    except Exception:
        pred_txt = str(obj)[:12000]
    sys_p = (
        "你是阅卷助手。金标是一段关于文档冲突与否的结论性描述。"
        "模型输出为结构化 JSON（含 is_conflict、diff_items、证据等）。"
        "判断模型结论与论证方向是否与金标含义一致；不要求字符串重合。"
        "只输出一行 JSON：{\"score\":0.7}，score 为 0 到 1 的小数。"
    )
    body = f"金标参考:\n{gold}\n\n模型结构化输出:\n{pred_txt}"
    return _semantic_score_json_llm(system_prompt=sys_p, user_body=body, max_tokens=120, hard=hard)


def _norm_item(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").strip().lower())


def _items_from_gold_answer(gold: str) -> Set[str]:
    parts = re.split(r"[，,、;；\n]+", gold or "")
    return {_norm_item(p) for p in parts if len(_norm_item(p)) >= 2}


def _gold_node_keys(gold_nodes: Optional[Sequence[str]]) -> Set[str]:
    """把 doc_id:Lk 规范化为可与 compose items 对齐的键。"""
    out: Set[str] = set()
    if not gold_nodes:
        return out
    for n in gold_nodes:
        ns = str(n).strip()
        if not ns:
            continue
        out.add(_norm_item(ns))
        m = re.search(r"L(\d+)\s*$", ns) or re.search(r":L(\d+)", ns)
        if m:
            out.add(_norm_item(f"L{m.group(1)}"))
            out.add(_norm_item(m.group(1)))
    return out


def _gold_set_scope_reg(gold_answer: str, gold_nodes: Optional[Sequence[str]]) -> Set[str]:
    s = _items_from_gold_answer(gold_answer) | _gold_node_keys(gold_nodes)
    if not s and gold_answer:
        s.add(_norm_item(gold_answer))
    return s


def _set_f1(pred_set: Set[str], gold_set: Set[str]) -> float:
    if not pred_set and not gold_set:
        return 1.0
    if not pred_set or not gold_set:
        return 0.0
    inter = len(pred_set & gold_set)
    prec = inter / len(pred_set)
    rec = inter / len(gold_set)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def _parse_composed_json(composed: str) -> Optional[Dict[str, Any]]:
    s = (composed or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _cross_claim_score(claims: Sequence[str], gold_answer: str) -> float:
    """两段式 gold（以；或 ; 分）与两条 claims 的最佳无序对齐。"""
    g = (gold_answer or "").strip()
    parts = re.split(r"[；;]", g, maxsplit=1)
    if len(parts) < 2:
        return _token_f1(" ".join(claims), g)
    g0, g1 = parts[0].strip(), parts[1].strip()
    if len(claims) < 2:
        return 0.5 * (_token_f1(claims[0], g0) + _token_f1(claims[0], g1)) if claims else 0.0
    c0, c1 = str(claims[0]).strip(), str(claims[1]).strip()
    s1 = 0.5 * (_token_f1(c0, g0) + _token_f1(c1, g1))
    s2 = 0.5 * (_token_f1(c0, g1) + _token_f1(c1, g0))
    return max(s1, s2)


def _gold_conflict_label(gold: str) -> Optional[bool]:
    g = (gold or "").strip()
    if not g:
        return None
    neg = ("无冲突", "一致", "完全一致", "未改变", "非实质冲突")
    pos = ("冲突", "矛盾", "不一致", "差异", "反转")
    if any(k in g for k in neg):
        return False
    if any(k in g for k in pos):
        return True
    return None


def _semantic_conflict_label(text: str) -> Optional[bool]:
    """
    将自然语言结论归一为:
      True  -> 有实质冲突
      False -> 无实质冲突/仅引用差异
      None  -> 无法判断
    """
    t = (text or "").strip()
    if not t:
        return None
    neg_kw = (
        "无冲突",
        "一致",
        "完全一致",
        "未改变",
        "非实质冲突",
        "条款号对应",
        "正常引用差异",
        "仅编号差异",
    )
    pos_kw = (
        "冲突",
        "矛盾",
        "不一致",
        "语义反转",
        "相反",
        "差异",
        "编辑错误",
        "额外加码",
    )
    if any(k in t for k in neg_kw):
        return False
    if any(k in t for k in pos_kw):
        return True
    return None


def _llm_conflict_label(pred_text: str, gold_text: str) -> Optional[bool]:
    """
    用 LLM 判断 pred 与 gold 的冲突标签语义是否一致，返回 gold 语义标签（True/False）或 None。
    仅在规则难以判断时启用。
    """
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return None
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        return None
    base = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = os.environ.get("JUDGE_MODEL", "gpt-4o-mini").strip()
    client = OpenAI(api_key=key, base_url=base)
    try:
        rsp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是冲突检测裁判。请判断 gold 结论的语义标签："
                        "1=有实质冲突，0=无实质冲突（含仅编号/引用差异）。"
                        "只输出一个字符：1 或 0。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"Gold:\n{gold_text}\n\nPred:\n{pred_text}\n",
                },
            ],
            temperature=0.0,
            max_tokens=2,
        )
        txt = (rsp.choices[0].message.content or "").strip()
        if txt.startswith("1"):
            return True
        if txt.startswith("0"):
            return False
        return None
    except Exception:
        return None


def _recall_nodes_in_text(text: str, gold_nodes: Optional[Sequence[str]]) -> float:
    if not gold_nodes:
        return 0.0
    t = text or ""
    hit = 0
    for n in gold_nodes:
        ns = str(n).strip()
        if not ns:
            continue
        if ns.split(":")[-1] in t.replace(" ", "") or ns in t:
            hit += 1
            continue
        lid_m = re.search(r"L(\d+)", ns)
        if lid_m and lid_m.group(1) in t:
            hit += 1
    return hit / len(list(gold_nodes))


def task_success_score(
    task_type: str,
    composed_answer: str,
    gold_answer: str,
    *,
    gold_nodes: Optional[Sequence[str]] = None,
    evidence_text: Optional[str] = None,
    semantic_threshold: float = 0.3,
) -> float:
    """返回 [0,1] 单标量 success。"""
    if _semantic_primary_enabled():
        _require_semantic_api()

    t = (task_type or "").lower()
    obj = _parse_composed_json(composed_answer)
    gold = gold_answer or ""

    # JSON 分支
    if isinstance(obj, dict):
        tt = str(obj.get("task_type", t)).lower()
        if tt in ("scope_collection", "regulatory_coverage") or t in (
            "scope_collection",
            "regulatory_coverage",
        ):
            raw_items = obj.get("items")
            pred_list: List[str] = [str(x) for x in raw_items] if isinstance(raw_items, list) else []
            if _semantic_primary_enabled():
                sem = _semantic_similarity_scope_llm(
                    pred_list, gold, gold_nodes=gold_nodes, hard=True
                )
                return float(sem)
            if isinstance(raw_items, list):
                pred_set = {_norm_item(str(x)) for x in raw_items if _norm_item(str(x))}
            else:
                pred_set = set()
            gold_set = _gold_set_scope_reg(gold, gold_nodes)
            return float(_set_f1(pred_set, gold_set))

        if tt in ("cross_section_conflict", "cross_clause_conflict") or t in (
            "cross_section_conflict",
            "cross_clause_conflict",
        ):
            if _semantic_primary_enabled():
                sem = _semantic_similarity_conflict_json_llm(obj, gold, hard=True)
                return float(sem)
            # 新协议优先：is_conflict + diff_items + evidence_a/b
            base = 0.0
            gl = _gold_conflict_label(gold)
            if gl is None:
                gl = _semantic_conflict_label(gold)
            pred_label = obj.get("is_conflict")
            if not isinstance(pred_label, bool):
                # 从预测文本里也尝试语义抽取
                pred_label = _semantic_conflict_label(
                    " ".join(
                        [
                            str(obj.get("answer", "")),
                            str(obj.get("evidence_a", "")),
                            str(obj.get("evidence_b", "")),
                            " ".join([str(x) for x in (obj.get("diff_items") or [])]),
                        ]
                    )
                )
            if gl is None and os.environ.get("JUDGE_USE_LLM", "").strip() in ("1", "true", "yes"):
                gl = _llm_conflict_label(str(obj), gold)
            if isinstance(pred_label, bool) and gl is not None:
                base += 0.35 if pred_label == gl else 0.0
            items = obj.get("diff_items")
            if isinstance(items, list):
                pred_set = {_norm_item(str(x)) for x in items if _norm_item(str(x))}
                gold_set = _items_from_gold_answer(gold)
                base += 0.35 * _set_f1(pred_set, gold_set) if gold_set else 0.0
            ea = str(obj.get("evidence_a", "")).strip()
            eb = str(obj.get("evidence_b", "")).strip()
            if ea or eb:
                base += 0.2 * _cross_claim_score([ea, eb], gold)
            else:
                cl = obj.get("claims")
                if isinstance(cl, list) and len(cl) >= 2:
                    base += 0.2 * _cross_claim_score([str(cl[0]), str(cl[1])], gold)
                else:
                    ans = str(obj.get("answer", ""))
                    base += 0.2 * _token_f1(ans, gold)
            ev = evidence_text or ""
            ev_cov = _recall_nodes_in_text(ev, gold_nodes) if ev else _recall_nodes_in_text(
                composed_answer, gold_nodes
            )
            return float(min(1.0, base + 0.10 * ev_cov))

        if tt in ("niche_fact", "multi_hop") or t in ("niche_fact", "multi_hop"):
            ans = str(obj.get("answer", composed_answer))
            if _semantic_primary_enabled():
                sem = _semantic_similarity_answer_llm(ans, gold, task_type=tt, hard=True)
                return float(sem)
            f1 = _token_f1(ans, gold)
            if f1 >= semantic_threshold:
                return float(f1)
            if os.environ.get("JUDGE_USE_LLM", "").strip() not in ("1", "true", "yes"):
                return float(f1)
            return float(max(f1, _semantic_match_llm(ans, gold)))

        if tt == "self_correct" or t == "self_correct":
            ans = str(obj.get("answer", composed_answer))
            if _semantic_primary_enabled():
                sem = _semantic_similarity_answer_llm(ans, gold, task_type="self_correct", hard=True)
                return float(sem)
            f1 = _token_f1(ans, gold)
            thr = float(os.environ.get("SELF_CORRECT_F1_THRESHOLD", "0.5"))
            if f1 >= thr:
                return 1.0
            if os.environ.get("JUDGE_USE_LLM", "").strip() in ("1", "true", "yes"):
                return 1.0 if max(f1, _semantic_match_llm(ans, gold)) >= 0.5 else 0.0
            return 0.0

        if _semantic_primary_enabled():
            raise RuntimeError(
                f"JUDGE_SEMANTIC_PRIMARY：composed JSON 未支持的 task_type={tt!r}（外层声明 {t!r}）。"
            )

    # 非 JSON 回退
    if t in ("niche_fact", "multi_hop"):
        if _semantic_primary_enabled():
            sem = _semantic_similarity_answer_llm(composed_answer, gold, task_type=t, hard=True)
            return float(sem)
        f1 = _token_f1(composed_answer, gold)
        if f1 >= semantic_threshold:
            return float(f1)
        if os.environ.get("JUDGE_USE_LLM", "").strip() not in ("1", "true", "yes"):
            return float(f1)
        return float(max(f1, _semantic_match_llm(composed_answer, gold)))

    if t == "self_correct":
        if _semantic_primary_enabled():
            sem = _semantic_similarity_answer_llm(composed_answer, gold, task_type=t, hard=True)
            return float(sem)
        f1 = _token_f1(composed_answer, gold)
        thr = float(os.environ.get("SELF_CORRECT_F1_THRESHOLD", "0.5"))
        return 1.0 if f1 >= thr else 0.0

    if t in ("scope_collection", "regulatory_coverage"):
        if _semantic_primary_enabled():
            parts = [p.strip() for p in re.split(r"[，,、;；\n]+", composed_answer or "") if len(p.strip()) >= 2]
            sem = _semantic_similarity_scope_llm(parts, gold, gold_nodes=gold_nodes, hard=True)
            return float(sem)
        pred_set = _items_from_gold_answer(composed_answer)
        gold_set = _gold_set_scope_reg(gold, gold_nodes)
        return float(_set_f1(pred_set, gold_set))

    if t in ("cross_section_conflict", "cross_clause_conflict"):
        if _semantic_primary_enabled():
            parsed = _parse_composed_json(composed_answer)
            if isinstance(parsed, dict):
                sem = _semantic_similarity_conflict_json_llm(parsed, gold, hard=True)
                return float(sem)
            sem = _semantic_similarity_answer_llm(composed_answer, gold, task_type=t, hard=True)
            return float(sem)
        base = _token_f1(composed_answer, gold)
        base = max(base, _cross_claim_score(re.split(r"[。.;；\n]+", composed_answer)[:2], gold))
        ev = evidence_text or ""
        ev_cov = _recall_nodes_in_text(ev, gold_nodes) if ev else _recall_nodes_in_text(
            composed_answer, gold_nodes
        )
        return float(min(1.0, 0.55 * base + 0.45 * ev_cov))

    # 未知类型：keyword 代理
    if _semantic_primary_enabled():
        raise RuntimeError(
            f"JUDGE_SEMANTIC_PRIMARY：不支持的 task_type={t!r}，无法用语义评测。"
        )
    return float(_keyword_overlap(composed_answer, gold))


def _keyword_overlap(pred: str, gold: str) -> float:
    gw = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", (gold or "").lower()))
    pw = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", (pred or "").lower()))
    if not gw:
        return 1.0 if not pw else 0.0
    if not pw:
        return 0.0
    return len(pw & gw) / len(gw)


def _semantic_match_llm(pred: str, gold: str) -> float:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key or not gold.strip():
        return 0.0
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        return 0.0
    base = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = os.environ.get("JUDGE_MODEL", "gpt-4o-mini").strip()
    client = OpenAI(api_key=key, base_url=base)
    rsp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": 'Reply exactly "1" if the prediction entails or matches the gold meaning, else "0".',
            },
            {
                "role": "user",
                "content": f"Gold:\n{gold}\n\nPred:\n{pred}\n",
            },
        ],
        temperature=0.0,
        max_tokens=2,
    )
    txt = (rsp.choices[0].message.content or "").strip()
    return 1.0 if txt.startswith("1") else 0.0
