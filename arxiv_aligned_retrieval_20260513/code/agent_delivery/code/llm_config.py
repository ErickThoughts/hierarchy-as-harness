from __future__ import annotations

import os
from pathlib import Path


def _parse_env_line(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    k, v = s.split("=", 1)
    key = k.strip()
    val = v.strip()
    if not key:
        return None
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    return key, val


def _apply_env_file(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    for line in lines:
        parsed = _parse_env_line(line)
        if not parsed:
            continue
        k, v = parsed
        if k and v and k not in os.environ:
            os.environ[k] = v


def load_llm_env() -> None:
    """
    从若干固定位置读取 LLM API 配置（若系统环境变量已存在则不覆盖）：
      1) 与本包同目录的 agent_delivery/llm_api.env（delivery/core 交付布局）
      2) bodyrich_delivery_kit/core/agent_delivery/llm_api.env（实验包根下常见放置处）
    按顺序加载；后读到的键仍遵守「不覆盖已在 os.environ 中的值」。
    """
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "llm_api.env",
        here.parents[4] / "core" / "agent_delivery" / "llm_api.env",
    ]
    for cfg in candidates:
        if cfg.exists():
            _apply_env_file(cfg)

