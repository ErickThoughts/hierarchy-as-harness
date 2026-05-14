"""
Plan §3.4：结构化 Compose。

- `compose_answer_llm`：OpenAI 兼容 Chat Completions，输出单行 JSON；须配置 `OPENAI_API_KEY`，
  可选 `OPENAI_BASE_URL`（如 DeepSeek / 转发网关）、`COMPOSE_MODEL`、`COMPOSE_TEMPERATURE`（默认 0）。
- `compose_structured_string`：仅用于离线调试/测试，主评测路径（runner_bodyrich / react_agent）不调用。

主路径由 `runner_bodyrich._configure_bodyrich_task_judge` 强制 `COMPOSE_USE_LLM=1`；LLM 失败或
无法解析 JSON 时直接抛错，不回退到启发式拼接。
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Optional, Sequence

from .index_retrieval import Chunk
from .llm_config import load_llm_env

load_llm_env()


def _task_type_compose_guidance(task_type: str) -> str:
    """按题型追加 compose 指令（不含金标答案，仅引导结构化输出以提高 Inspect 命中率）。"""
    tt = (task_type or "").lower()
    if tt == "multi_hop":
        return (
            "【题型 multi_hop】必须在 JSON 中给出三个独立短句字段："
            "\"fact_1\"（第一步事实）、\"fact_2\"（第二步事实）、\"final_answer\"（综合结论）；"
            "final_answer 必须综合回答问题中的所有子问，不得为空。"
            "若问题询问多个方面（如功能和设计要求、主体和期限、类型列表），final_answer 必须逐项覆盖；"
            "不要把 fact_2 或 final_answer 这些键名写进字段值。全部严格来自 Evidence，勿臆造。"
        )
    if tt in ("scope_collection", "regulatory_coverage"):
        return (
            "【题型 scope/regulatory】输出 `items` 为非空字符串数组：每一项对应证据中一条独立要点或条款，"
            "去重、简短；尽量覆盖问题所问的全部子项，顺序可与证据不一致。"
        )
    if tt == "niche_fact":
        return "【题型 niche_fact】`answer` 为一句可核验的简短结论，含必要数字与单位，严格来自 Evidence。"
    if tt == "self_correct":
        return "【题型 self_correct】`answer` 给出修正后的最终结论，与 Evidence 一致。"
    return ""


def _norm_ws(s: str) -> str:
    return " ".join((s or "").split())


def _extract_first_balanced_json(text: str) -> Optional[str]:
    s = (text or "").strip()
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escaped = False
    end = -1
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None
    return s[start : end + 1]


def _repair_multi_hop_glued_json(raw: str) -> Optional[str]:
    """修复 qwen 常见坏格式：fact_1 字符串里粘连 fact_2/final_answer 键。"""
    s = (raw or "").strip()
    if '"fact_1":"' not in s or 'fact_2":"' not in s or 'final_answer":"' not in s:
        return None
    try:
        f1_start = s.index('"fact_1":"') + len('"fact_1":"')
        f2_key = s.index('fact_2":"', f1_start)
        f2_start = f2_key + len('fact_2":"')
        fa_key = s.index('final_answer":"', f2_start)
        fa_start = fa_key + len('final_answer":"')
        fa_end = s.rfind('"')
        if fa_end <= fa_start:
            return None
        f1 = s[f1_start:f2_key]
        f2 = s[f2_start:fa_key]
        fa = s[fa_start:fa_end]
        # 去掉键粘连产生的分隔噪声
        f1 = re.sub(r'[;；,\s"\']+$', "", f1).strip()
        f2 = re.sub(r'^[;；,\s"\']+', "", f2).strip()
        f2 = re.sub(r'[;；,\s"\']+$', "", f2).strip()
        fa = re.sub(r'^[;；,\s"\']+', "", fa).strip()
        if not (f1 and f2 and fa):
            return None
        obj = {
            "task_type": "multi_hop",
            "fact_1": f1,
            "fact_2": f2,
            "final_answer": fa,
        }
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return None


def _split_embedded_multi_hop_fields(text: str) -> Optional[dict]:
    """修复合法 JSON 中 fact_1/answer 字符串粘入 `fact_2:` / `final_answer:` 的情况。"""
    s = str(text or "").strip()
    if not s:
        return None
    markers = [
        "fact_2：",
        "fact_2:",
        "final_answer：",
        "final_answer:",
        "final answer：",
        "final answer:",
    ]
    if not any(m in s for m in markers):
        return None

    f1 = s
    f2 = ""
    fa = ""
    m_f2 = re.search(r"(?:^|[;；，,\s])fact_2\s*[:：]", s)
    m_fa = re.search(r"(?:^|[;；，,\s])final(?:_answer| answer)\s*[:：]", s, re.I)
    if m_f2:
        f1 = s[: m_f2.start()].strip(" ;；，,")
        rest = s[m_f2.end() :].strip(" ;；，,")
        m_fa2 = re.search(r"(?:^|[;；，,\s])final(?:_answer| answer)\s*[:：]", rest, re.I)
        if m_fa2:
            f2 = rest[: m_fa2.start()].strip(" ;；，,")
            fa = rest[m_fa2.end() :].strip(" ;；，,")
        else:
            f2 = rest
    elif m_fa:
        f1 = s[: m_fa.start()].strip(" ;；，,")
        fa = s[m_fa.end() :].strip(" ;；，,")

    if not (f1 or f2 or fa):
        return None
    return {"fact_1": f1, "fact_2": f2, "final_answer": fa}


def _repair_multi_hop_obj_fields(obj: dict) -> dict:
    """Normalize valid-but-glued multi-hop JSON fields before scoring/mapping."""
    out = dict(obj)
    for key in ("fact_1", "answer"):
        repaired = _split_embedded_multi_hop_fields(str(out.get(key) or ""))
        if not repaired:
            continue
        for rk, rv in repaired.items():
            if rv and (rk == key or not str(out.get(rk) or "").strip()):
                out[rk] = rv
        if key == "answer":
            out.pop("answer", None)
        break
    return out


def _normalize_composed_obj(tt: str, obj: dict, max_answer_chars: int) -> dict:
    cap = max(64, int(max_answer_chars))
    task_type = str(obj.get("task_type") or tt or "unknown").strip() or "unknown"
    if tt in ("scope_collection", "regulatory_coverage"):
        items = obj.get("items")
        out_items: List[str] = []
        if isinstance(items, list):
            for x in items:
                s = str(x or "").strip()
                if s:
                    out_items.append(s[:cap])
            if out_items:
                return {"task_type": task_type, "items": out_items[:32]}
        ans = str(obj.get("answer") or "").strip()
        if ans:
            return {"task_type": task_type, "items": [ans[:cap]]}
        return {"task_type": task_type, "items": []}
    if tt == "multi_hop":
        obj = _repair_multi_hop_obj_fields(obj)
        if str(obj.get("condition") or "").strip() or str(obj.get("outcome") or "").strip():
            return {
                "task_type": task_type,
                "condition": str(obj.get("condition") or "").strip()[:cap],
                "outcome": str(obj.get("outcome") or "").strip()[:cap],
                "final_answer": str(obj.get("final_answer") or obj.get("answer") or "").strip()[:cap],
            }
        for k in ("fact_1", "fact_2", "final_answer", "answer"):
            v = str(obj.get(k) or "").strip()
            if v:
                if k == "answer":
                    parts = [p.strip() for p in re.split(r"[；;]", v) if p.strip()]
                    if len(parts) >= 2:
                        return {
                            "task_type": task_type,
                            "fact_1": parts[0][:cap],
                            "fact_2": parts[1][:cap],
                            "final_answer": v[:cap],
                        }
                    return {"task_type": task_type, "answer": v[:cap]}
                out = {
                    "task_type": task_type,
                    "fact_1": str(obj.get("fact_1") or "").strip()[:cap],
                    "fact_2": str(obj.get("fact_2") or "").strip()[:cap],
                    "final_answer": str(obj.get("final_answer") or "").strip()[:cap],
                }
                return out
        return {"task_type": task_type, "answer": ""}
    if tt in ("cross_section_conflict", "cross_clause_conflict"):
        return {
            "task_type": task_type,
            "is_conflict": bool(obj.get("is_conflict", False)),
            "diff_items": [str(x)[:cap] for x in (obj.get("diff_items") or []) if str(x).strip()][:16],
            "evidence_a": str(obj.get("evidence_a") or "").strip()[:cap],
            "evidence_b": str(obj.get("evidence_b") or "").strip()[:cap],
        }
    return {"task_type": task_type, "answer": str(obj.get("answer") or "").strip()[:cap]}


def _extract_answer_field(text: str) -> Optional[str]:
    m = re.search(r'"answer"\s*:\s*"((?:\\.|[^"\\])*)"', text or "")
    if not m:
        return None
    raw = m.group(1)
    try:
        return json.loads(f'"{raw}"')
    except Exception:
        return raw


def _compose_max_tokens(max_answer_chars: int) -> int:
    # 过去按 max_answer_chars/2 容易在多字段 JSON 上截断；这里放宽上限，保证 JSON 闭合。
    return min(1024, max(256, int(max_answer_chars) * 2))


def _evidence_from_chunks(chunks: Sequence[Chunk], max_chars: int) -> str:
    parts: List[str] = []
    used = 0
    sep = "\n\n"
    for c in chunks:
        block = f"[{c.node_id}]\n{(c.text or '').strip()}"
        add = len(block) + (len(sep) if parts else 0)
        if used + add > max_chars:
            remain = max_chars - used - (len(sep) if parts else 0)
            if remain > 20:
                parts.append(block[:remain])
            break
        parts.append(block)
        used += add
    return sep.join(parts)


def compose_structured_string(
    query: str,
    task_type: str,
    evidence_text: str,
    *,
    max_answer_chars: int = 1024,
) -> str:
    """
    离线可复现：根据 task_type 把 evidence 压成 plan 约定的 JSON 行（无 LLM）。
    niche_fact / multi_hop / self_correct: {"answer": "..."}
    scope_collection / regulatory_coverage: {"items": [...]} 从 evidence 启发式切分
    cross_section_conflict / cross_clause_conflict:
      {"is_conflict": bool, "diff_items":[...], "evidence_a":"...", "evidence_b":"..."}
    """
    del query
    tt = (task_type or "unknown").lower()
    ev = (evidence_text or "").strip()
    cap = max(64, int(max_answer_chars))

    def _split_items(text: str) -> list[str]:
        parts = re.split(r"[，,、;；\n]+", text)
        out: list[str] = []
        for p in parts:
            p = p.strip()
            if len(p) >= 2:
                out.append(p)
        return out[:32]

    def _split_claims(text: str) -> list[str]:
        blocks = [b.strip() for b in re.split(r"\n\s*\n+", text) if b.strip()]
        if len(blocks) >= 2:
            return [blocks[0][: cap // 2], blocks[1][: cap // 2]]
        sents = [s.strip() for s in re.split(r"[。.;；]+", text) if len(s.strip()) > 12]
        if len(sents) >= 2:
            return [sents[0][: cap // 2], sents[1][: cap // 2]]
        half = min(len(text), cap // 2)
        return [text[:half], text[half : half * 2]] if text else ["", ""]

    def _infer_conflict_obj(text: str) -> dict:
        t = text or ""
        pos = ["冲突", "矛盾", "不一致", "差异", "反转", "相反", "额外要求"]
        neg = ["无冲突", "一致", "完全一致", "未改变", "非实质冲突"]
        is_conflict = any(k in t for k in pos) and not any(k in t for k in neg)
        # 提取若干“差异项”线索
        segs = [s.strip() for s in re.split(r"[。；;\n]+", t) if len(s.strip()) >= 6]
        diff_items = []
        for s in segs:
            if any(k in s for k in ("冲突", "矛盾", "不一致", "差异", "反转", "增加", "减少")):
                diff_items.append(s[:80])
            if len(diff_items) >= 5:
                break
        claims = _split_claims(t)
        return {
            "task_type": tt,
            "is_conflict": bool(is_conflict),
            "diff_items": diff_items,
            "evidence_a": claims[0] if claims else "",
            "evidence_b": claims[1] if len(claims) > 1 else "",
        }

    if tt in ("niche_fact", "multi_hop", "self_correct", "unknown"):
        ans = _norm_ws(ev)[:cap]
        return json.dumps({"task_type": tt, "answer": ans}, ensure_ascii=False)

    if tt in ("scope_collection", "regulatory_coverage"):
        items = _split_items(ev) or [_norm_ws(ev)[:cap]]
        return json.dumps({"task_type": tt, "items": items}, ensure_ascii=False)

    if tt in ("cross_section_conflict", "cross_clause_conflict"):
        return json.dumps(_infer_conflict_obj(ev), ensure_ascii=False)

    return json.dumps({"task_type": tt, "answer": _norm_ws(ev)[:cap]}, ensure_ascii=False)


def compose_answer_string(query: str, chunks: Sequence[Chunk], max_chars: int = 700) -> str:
    """兼容旧接口：与主路径一致，仅走 LLM compose（niche_fact）。"""
    bc = max(200, max_chars * 8)
    ev = _evidence_from_chunks(chunks, max_chars=bc)
    return compose_answer_llm(
        query,
        chunks=None,
        task_type="niche_fact",
        evidence_text=ev,
        max_answer_chars=max_chars,
        budget_chars=bc,
        format_constraints="",
    )


def compose_answer_llm(
    query: str,
    chunks: Optional[Sequence[Chunk]] = None,
    *,
    task_type: str = "niche_fact",
    evidence_text: Optional[str] = None,
    max_answer_chars: int = 1024,
    budget_chars: int = 4000,
    format_constraints: str = "",
) -> str:
    """
    调用 OpenAI 兼容 Chat Completions，输出 **仅一行 JSON**（与 compose_structured_string 同 schema）。
    evidence_text 缺省时由 chunks 按 budget_chars 拼接。
    """
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "compose_answer_llm 需要 OPENAI_API_KEY（及可选 OPENAI_BASE_URL）；请配置 llm_api.env 或环境变量。"
        )
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise RuntimeError("compose_answer_llm 需要安装 openai 包") from e

    ev = evidence_text
    if ev is None:
        ev = _evidence_from_chunks(chunks or [], max_chars=max(200, budget_chars))
    else:
        ev = ev[: max(1, budget_chars)]

    base = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    model = os.environ.get("COMPOSE_MODEL", "gpt-4o-mini").strip()
    client = OpenAI(api_key=key, base_url=base)
    tt = (task_type or "niche_fact").lower()
    schema_hint = {
        "niche_fact": '{"task_type":"niche_fact","answer":"<简短事实>"}',
        "multi_hop": (
            '{"task_type":"multi_hop","fact_1":"<第1步事实>","fact_2":"<第2步事实>",'
            '"final_answer":"<综合结论，必须覆盖所有子问>"}'
        ),
        "self_correct": '{"task_type":"self_correct","answer":"<修正后答案>"}',
        "scope_collection": '{"task_type":"scope_collection","items":["...","..."]}',
        "regulatory_coverage": '{"task_type":"regulatory_coverage","items":["..."]}',
        "cross_section_conflict": '{"task_type":"cross_section_conflict","is_conflict":true,"diff_items":["<差异点1>"],"evidence_a":"<A证据>","evidence_b":"<B证据>"}',
        "cross_clause_conflict": '{"task_type":"cross_clause_conflict","is_conflict":true,"diff_items":["<差异点1>"],"evidence_a":"<A证据>","evidence_b":"<B证据>"}',
    }.get(tt, '{"task_type":"...","answer":"..."}')

    user = f"Task type: {tt}\nQuery:\n{query}\n\nEvidence:\n{ev}\n\n"
    fc = (format_constraints or "").strip()
    if fc:
        user += f"Output format constraints:\n{fc}\n\n"
    guide = _task_type_compose_guidance(tt)
    if guide:
        user += guide + "\n\n"
    user += (
        "Output exactly one JSON object on a single line, no markdown, schema like: "
        f"{schema_hint}"
    )
    user += (
        "\n禁止输出无关键（如 evidence_line_ids、analysis、reasoning）；"
        "只输出 schema 所需最小字段；不要把 JSON 键名写进字符串值。"
    )
    try:
        rsp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You output only one line of valid JSON. No code fences. Answer strictly from evidence.",
                },
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=float(os.environ.get("COMPOSE_TEMPERATURE", "0").strip() or "0"),
            max_tokens=_compose_max_tokens(max_answer_chars),
        )
    except Exception:
        rsp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You output only one line of valid JSON. No code fences. Answer strictly from evidence.",
                },
                {"role": "user", "content": user},
            ],
            temperature=float(os.environ.get("COMPOSE_TEMPERATURE", "0").strip() or "0"),
            max_tokens=_compose_max_tokens(max_answer_chars),
        )
    text = (rsp.choices[0].message.content or "").strip()
    text = text.replace("```json", "").replace("```", "").strip()
    # 取第一行 JSON
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    return json.dumps(
                        _normalize_composed_obj(tt, obj, max_answer_chars),
                        ensure_ascii=False,
                    )
            except json.JSONDecodeError:
                continue
    balanced = _extract_first_balanced_json(text)
    if balanced:
        try:
            obj = json.loads(balanced)
            if isinstance(obj, dict):
                return json.dumps(
                    _normalize_composed_obj(tt, obj, max_answer_chars),
                    ensure_ascii=False,
                )
        except json.JSONDecodeError:
            if tt == "multi_hop":
                fixed = _repair_multi_hop_glued_json(balanced)
                if fixed:
                    obj = json.loads(fixed)
                    return json.dumps(
                        _normalize_composed_obj(tt, obj, max_answer_chars),
                        ensure_ascii=False,
                    )
    ans = _extract_answer_field(text)
    if ans is not None:
        obj = {"task_type": tt, "answer": ans}
        return json.dumps(_normalize_composed_obj(tt, obj, max_answer_chars), ensure_ascii=False)
    preview = (text or "")[:400].replace("\n", "\\n")
    raise RuntimeError(
        "compose_answer_llm：模型返回中未找到可解析的单行 JSON，已禁止回退到离线 compose。"
        f" model={model!r} preview={preview!r}"
    )
