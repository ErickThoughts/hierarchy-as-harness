#!/usr/bin/env python3
"""Build consolidated Markdown reports for the arXiv retrieval package."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
BUDGETS = (300, 500, 1000)


@dataclass(frozen=True)
class Experiment:
    name: str
    pattern: str
    scoring: str
    pool: str
    purpose: str


SCORE_MODE_EXPERIMENTS = (
    Experiment(
        "full_text",
        "arxiv_predcomplete_aligned_dense_b{budget}.json",
        "PATH + 正文",
        "整篇文档 leaf/path pool",
        "realdata 对齐主设置",
    ),
    Experiment(
        "content_only",
        "arxiv_predcomplete_content_only_b{budget}.json",
        "仅正文",
        "整篇文档 leaf/path pool",
        "剥离 PATH 对 dense ranking 的影响",
    ),
    Experiment(
        "path_only",
        "arxiv_predcomplete_path_only_b{budget}.json",
        "仅 PATH",
        "整篇文档 leaf/path pool",
        "单独观察标题/路径文本信号",
    ),
)

IMPROVEMENT_EXPERIMENTS = (
    Experiment(
        "full_text_main",
        "arxiv_predcomplete_aligned_dense_b{budget}.json",
        "PATH + 正文",
        "整篇文档 leaf/path pool",
        "realdata 对齐主结果",
    ),
    Experiment(
        "content_only",
        "arxiv_predcomplete_content_only_b{budget}.json",
        "仅正文",
        "整篇文档 leaf/path pool",
        "去掉 PATH 参与 dense scoring",
    ),
    Experiment(
        "content_len220",
        "arxiv_predcomplete_content_len220_b{budget}.json",
        "仅正文",
        "leaf/path 正文按约 220 字符窗口切分",
        "降低 chunk 长度和 budget 边界偏置",
    ),
    Experiment(
        "content_routed_m3",
        "arxiv_predcomplete_content_routed_m3_b{budget}.json",
        "仅正文",
        "只检索 top-3 routed sections",
        "强 section routing 约束",
    ),
    Experiment(
        "content_routed_m8",
        "arxiv_predcomplete_content_routed_m8_b{budget}.json",
        "仅正文",
        "只检索 top-8 routed sections",
        "较宽松 section routing 约束",
    ),
)


def _budget_metric(arm: dict, key: str) -> float:
    return float(arm["budget"][key])


def _line_metric(arm: dict, key: str) -> float:
    return float(arm["line_retrieval"][key])


def _arm_metric(arm: dict, key: str) -> float:
    return float(arm[key])


METRICS: tuple[tuple[str, str, Callable[[dict], float]], ...] = (
    ("coverage_budget_lenient", "Coverage@budget_lenient", lambda arm: _budget_metric(arm, "coverage_budget_lenient")),
    ("mrr_chunks", "MRR@chunks", lambda arm: _budget_metric(arm, "mrr_chunks")),
    ("chunk_hit@1", "ChunkHit@1", lambda arm: _budget_metric(arm, "chunk_hit@1")),
    ("precision@1_line", "Precision@1 line", lambda arm: _line_metric(arm, "precision@1")),
    ("precision@3_line", "Precision@3 line", lambda arm: _line_metric(arm, "precision@3")),
    ("precision@5_line", "Precision@5 line", lambda arm: _line_metric(arm, "precision@5")),
    ("mrr_line", "MRR line", lambda arm: _line_metric(arm, "mrr")),
    ("hit@5_line", "Hit@5 line", lambda arm: _line_metric(arm, "hit@5")),
    ("ndcg@10_line", "NDCG@10 line", lambda arm: _line_metric(arm, "ndcg@10")),
    ("coverage_line", "Coverage line", lambda arm: _line_metric(arm, "coverage")),
    ("evidence_chars", "Evidence chars", lambda arm: _arm_metric(arm, "evidence_chars_actual")),
    ("chunks_kept", "Chunks kept", lambda arm: _arm_metric(arm, "n_chunks_kept")),
)

METRIC_BY_ID = {metric_id: (label, getter) for metric_id, label, getter in METRICS}
ARM_KEYS = (("Gold", "gold_hier"), ("Pred", "pred_hier"), ("Flat", "flat"))


def load_result(exp: Experiment, budget: int) -> dict:
    path = RESULTS / exp.pattern.format(budget=budget)
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_rows(exp: Experiment, budget: int) -> list[dict]:
    return load_result(exp, budget)["rows"]


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def summarize_rows(rows: list[dict], metric_id: str) -> dict[str, float]:
    _, getter = METRIC_BY_ID[metric_id]
    return {
        label: mean([getter(row[key]) for row in rows])
        for label, key in ARM_KEYS
    }


def task_type_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("task_type", "unknown"))] += 1
    return dict(sorted(counts.items()))


def rows_by_type(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("task_type", "unknown"))].append(row)
    return dict(sorted(grouped.items()))


def fmt(value: float) -> str:
    return f"{value:.3f}"


def signed(value: float) -> str:
    return f"{value:+.3f}"


def metric_cells(summary: dict[str, float]) -> list[str]:
    gold = summary["Gold"]
    pred = summary["Pred"]
    flat = summary["Flat"]
    return [
        fmt(gold),
        fmt(pred),
        fmt(flat),
        signed(pred - flat),
        signed(gold - flat),
        signed(pred - gold),
    ]


def append_main_metric_table(lines: list[str], experiments: tuple[Experiment, ...]) -> None:
    lines.extend(
        [
            "| Budget | Experiment | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for budget in BUDGETS:
        for exp in experiments:
            summary = summarize_rows(load_rows(exp, budget), "coverage_budget_lenient")
            lines.append(f"| {budget} | `{exp.name}` | " + " | ".join(metric_cells(summary)) + " |")


def best_label_for_budget(exp: Experiment, budget: int) -> tuple[str, float]:
    summary = summarize_rows(load_rows(exp, budget), "coverage_budget_lenient")
    label = max(summary, key=summary.get)
    return label, summary[label]


def type_advantage(exp: Experiment, budget: int) -> tuple[list[str], list[str], list[str]]:
    grouped = rows_by_type(load_rows(exp, budget))
    pred_better: list[str] = []
    tied: list[str] = []
    flat_better: list[str] = []
    for task_type, rows in grouped.items():
        summary = summarize_rows(rows, "coverage_budget_lenient")
        delta = summary["Pred"] - summary["Flat"]
        if delta > 1e-12:
            pred_better.append(task_type)
        elif delta < -1e-12:
            flat_better.append(task_type)
        else:
            tied.append(task_type)
    return pred_better, tied, flat_better


def append_overall_all_metrics(lines: list[str], experiments: tuple[Experiment, ...], name_header: str = "Experiment") -> None:
    lines.append("## Overall All Metrics")
    lines.append("")
    for budget in BUDGETS:
        lines.append(f"### budget={budget}")
        lines.append("")
        lines.append(
            f"| {name_header} | Metric | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |"
        )
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for exp in experiments:
            rows = load_rows(exp, budget)
            for metric_id, label, _ in METRICS:
                summary = summarize_rows(rows, metric_id)
                lines.append(f"| `{exp.name}` | {label} | " + " | ".join(metric_cells(summary)) + " |")
        lines.append("")


def append_per_type_coverage(lines: list[str], experiments: tuple[Experiment, ...], name_header: str = "Experiment") -> None:
    lines.append("## Per-Type Coverage@budget_lenient")
    lines.append("")
    for budget in BUDGETS:
        lines.append(f"### budget={budget}")
        lines.append("")
        lines.append(
            f"| task_type | {name_header} | n | Gold | Pred | Flat | d(Pred-Flat) | d(Gold-Flat) | d(Pred-Gold) |"
        )
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        first_rows = load_rows(experiments[0], budget)
        task_types = list(rows_by_type(first_rows).keys())
        for task_type in task_types:
            for exp in experiments:
                rows = rows_by_type(load_rows(exp, budget))[task_type]
                summary = summarize_rows(rows, "coverage_budget_lenient")
                lines.append(
                    f"| {task_type} | `{exp.name}` | {len(rows)} | "
                    + " | ".join(metric_cells(summary))
                    + " |"
                )
        lines.append("")


def write_score_modes() -> None:
    lines = [
        "# arXiv 层级 dense scoring 模式对比",
        "",
        "本报告只改变层级臂 dense scoring 的文本来源；Flat-react 对照保持不变。三套结果是分别输出，不做 PATH/正文加权混合。",
        "",
        "## 实验定义",
        "",
        "| Mode | 层级 scoring | 候选池 | 用途 |",
        "| --- | --- | --- | --- |",
    ]
    for exp in SCORE_MODE_EXPERIMENTS:
        lines.append(f"| `{exp.name}` | {exp.scoring} | {exp.pool} | {exp.purpose} |")
    lines.extend(
        [
            "",
            "## 核心结论",
            "",
        ]
    )
    for budget in BUDGETS:
        best = ("", "", -1.0)
        for exp in SCORE_MODE_EXPERIMENTS:
            summary = summarize_rows(load_rows(exp, budget), "coverage_budget_lenient")
            for arm in ("Gold", "Pred", "Flat"):
                if summary[arm] > best[2]:
                    best = (exp.name, arm, summary[arm])
        lines.append(f"- budget={budget}: Coverage@budget_lenient 最好的是 `{best[0]}:{best[1]}` = {fmt(best[2])}。")
    lines.extend(
        [
            "- `content_only` 是最干净的正文检索诊断：PATH 不参与 dense ranking，但最终 evidence 仍保留 PATH + 正文。",
            "- `path_only` 用来观察 section heading / path 文本本身能贡献多少信号，不建议替代主结果。",
            "",
            "## Overall Main Metric",
            "",
        ]
    )
    append_main_metric_table(lines, SCORE_MODE_EXPERIMENTS)
    lines.append("")
    append_overall_all_metrics(lines, SCORE_MODE_EXPERIMENTS, name_header="Mode")
    append_per_type_coverage(lines, SCORE_MODE_EXPERIMENTS, name_header="Mode")
    (RESULTS / "summary_score_modes.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_improvement_experiments() -> None:
    lines = [
        "# arXiv 检索改进实验汇总",
        "",
        "范围：arXiv pred-complete 包内的 retrieval-only 诊断。Flat-react 在所有行里不变；层级臂只改变 scoring 文本或候选池构造。",
        "",
        "## 实验定义",
        "",
        "| Experiment | 层级 scoring | 层级候选池 | 用途 |",
        "| --- | --- | --- | --- |",
    ]
    for exp in IMPROVEMENT_EXPERIMENTS:
        lines.append(f"| `{exp.name}` | {exp.scoring} | {exp.pool} | {exp.purpose} |")

    len_rows_1000 = summarize_rows(load_rows(IMPROVEMENT_EXPERIMENTS[2], 1000), "coverage_budget_lenient")
    flat_1000 = len_rows_1000["Flat"]
    pred_1000 = len_rows_1000["Pred"]
    routed_m8_1000 = summarize_rows(load_rows(IMPROVEMENT_EXPERIMENTS[4], 1000), "coverage_budget_lenient")["Pred"]
    main_1000 = summarize_rows(load_rows(IMPROVEMENT_EXPERIMENTS[0], 1000), "coverage_budget_lenient")
    lines.extend(
        [
            "",
            "## 核心结论",
            "",
            f"- `content_len220` 是当前唯一明确有效的改进诊断：budget=1000 时 Pred-hier={fmt(pred_1000)}，略高于 Flat-react={fmt(flat_1000)}。",
            f"- Routing 不适合作为主设置：`content_routed_m8` 在 budget=1000 的 Pred-hier={fmt(routed_m8_1000)}，低于 full-pool 和 Flat-react，说明当前 top-section router 召回损失较大。",
            f"- Gold-hier 仍没有稳定超过 Pred-hier；主结果 budget=1000 为 Gold={fmt(main_1000['Gold'])}, Pred={fmt(main_1000['Pred'])}。这更像 tree/chunk 边界对 dense retrieval 的影响，而不是 PATH 文本单独造成的偏置。",
            "- 正式汇报建议：`full_text_main` 作为 realdata 对齐主结果；`content_only` 和 `content_len220` 作为诊断/改进补充。",
            "",
            "## Main Metric: Coverage@budget_lenient",
            "",
        ]
    )
    append_main_metric_table(lines, IMPROVEMENT_EXPERIMENTS)
    lines.append("")
    append_overall_all_metrics(lines, IMPROVEMENT_EXPERIMENTS)
    append_per_type_coverage(lines, IMPROVEMENT_EXPERIMENTS)
    (RESULTS / "summary_improvement_experiments.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_final_summary() -> None:
    main_exp = IMPROVEMENT_EXPERIMENTS[0]
    len_exp = IMPROVEMENT_EXPERIMENTS[2]
    rows0 = load_rows(main_exp, 300)
    counts = task_type_counts(rows0)
    lines = [
        "# arXiv 检索实验最终总览",
        "",
        "本文件是 `arxiv_aligned_retrieval_20260513` 的入口总结。所有实验均为 retrieval-only：不跑 ReAct agent、不做 compose、不用 LLM judge。",
        "",
        "## 该看哪套结果",
        "",
        "| 用途 | 文件 | 结论口径 |",
        "| --- | --- | --- |",
        "| 正式主结果 | `summary_aligned.md` | realdata 对齐口径：层级 `PATH + 正文` dense scoring，Flat 为 flat_react-style 多 query 检索。 |",
        "| PATH/正文拆分诊断 | `summary_score_modes.md` | 分别输出 `full_text` / `content_only` / `path_only`，不做加权。 |",
        "| 改进实验 | `summary_improvement_experiments.md` | 比较主结果、正文-only、长度归一化、routing。 |",
        "| 单个设置详细表 | `summary_content_only.md` / `summary_path_only.md` / `summary_content_len220.md` / routed summaries | 每个 budget 下的总体指标和 per-type 全指标。 |",
        "",
        "## 数据与任务",
        "",
        f"- 任务数：{len(rows0)}。",
        "- 任务文件名保留历史 `150` 命名，但当前有效任务是 77 条。",
        "- 评估开始会校验每题 `gold_nodes` 都能在 arXiv 行节点中找到。",
        "",
        "| task_type | n |",
        "| --- | ---: |",
    ]
    for task_type, n in counts.items():
        lines.append(f"| {task_type} | {n} |")

    lines.extend(
        [
            "",
            "## 主结果：realdata 对齐口径",
            "",
            "| Budget | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Pred-Gold) | 最好 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for budget in BUDGETS:
        summary = summarize_rows(load_rows(main_exp, budget), "coverage_budget_lenient")
        best_arm = max(summary, key=summary.get)
        lines.append(
            f"| {budget} | {fmt(summary['Gold'])} | {fmt(summary['Pred'])} | {fmt(summary['Flat'])} | "
            f"{signed(summary['Pred'] - summary['Flat'])} | {signed(summary['Pred'] - summary['Gold'])} | {best_arm} |"
        )

    lines.extend(
        [
            "",
            "主结果说明：budget=300 时 Pred-hier 略高于 Flat；budget=500/1000 时 Flat-react 更强。Pred-hier 平均高于 Gold-hier，但题级差异集中在少数样本，不能解释成 gold tree 被系统性打败。",
            "",
            "## 最有效的改进诊断：content_len220",
            "",
            "| Budget | Gold-hier | Pred-hier | Flat-react | d(Pred-Flat) | d(Pred-Gold) | 最好 |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for budget in BUDGETS:
        summary = summarize_rows(load_rows(len_exp, budget), "coverage_budget_lenient")
        best_arm = max(summary, key=summary.get)
        lines.append(
            f"| {budget} | {fmt(summary['Gold'])} | {fmt(summary['Pred'])} | {fmt(summary['Flat'])} | "
            f"{signed(summary['Pred'] - summary['Flat'])} | {signed(summary['Pred'] - summary['Gold'])} | {best_arm} |"
        )

    lines.extend(
        [
            "",
            "这个设置保留 leaf/path 层级候选，但把正文切成约 220 字符窗口后再检索。它说明：控制 chunk 长度和边界后，arXiv 上的层级信号能被恢复一部分；budget=1000 时 Pred-hier 略高于 Flat-react。",
            "",
            "## 按题型主结论",
            "",
            "### 主结果 full_text_main：Pred-hier vs Flat-react",
            "",
            "| Budget | Pred-hier 优于 Flat-react | 打平 | Flat-react 优于 Pred-hier |",
            "| ---: | --- | --- | --- |",
        ]
    )
    for budget in BUDGETS:
        pred_better, tied, flat_better = type_advantage(main_exp, budget)
        lines.append(
            f"| {budget} | {', '.join(pred_better) or '-'} | {', '.join(tied) or '-'} | {', '.join(flat_better) or '-'} |"
        )

    lines.extend(
        [
            "",
            "### 改进结果 content_len220：Pred-hier vs Flat-react",
            "",
            "| Budget | Pred-hier 优于 Flat-react | 打平 | Flat-react 优于 Pred-hier |",
            "| ---: | --- | --- | --- |",
        ]
    )
    for budget in BUDGETS:
        pred_better, tied, flat_better = type_advantage(len_exp, budget)
        lines.append(
            f"| {budget} | {', '.join(pred_better) or '-'} | {', '.join(tied) or '-'} | {', '.join(flat_better) or '-'} |"
        )

    lines.extend(
        [
            "",
            "## 最终判断",
            "",
            "- arXiv 上层级结构有信号，但收益不稳定，强依赖检索单元的 chunk 长度和边界。",
            "- PATH 不是唯一原因：`content_only` 下 Pred 仍常高于 Gold，说明结构切分本身会影响 dense retrieval。",
            "- 目前不能声称 Gold tree 必然优于 Pred tree。更准确的表述是：gold 结构语义更可信，但未必天然产生最适合 dense retriever 的 chunk。",
            "- 不建议把 routing 作为主实验：它提前过滤 section，召回损失大。",
            "- 建议汇报主线：先给 `full_text_main` 对齐结果，再用 `content_only` 和 `content_len220` 解释 PATH/长度/边界的影响。",
            "",
            "## 文件索引",
            "",
            "- `summary_aligned.md`：正式主结果，含对齐审计、总体指标、per-type 全指标。",
            "- `summary_score_modes.md`：PATH/正文分开 dense scoring 的三套结果。",
            "- `summary_improvement_experiments.md`：主结果、正文-only、长度归一化、routing 的横向对比。",
            "- `summary_content_len220.md`：当前最好的改进诊断单表。",
            "- `arxiv_predcomplete_*_b{300,500,1000}.json`：逐题结果和 summary。",
        ]
    )
    (RESULTS / "summary_final.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_results_readme() -> None:
    lines = [
        "# results 目录说明",
        "",
        "## 推荐阅读顺序",
        "",
        "1. `summary_final.md`：最终总览和核心结论。",
        "2. `summary_aligned.md`：realdata 对齐主实验的完整表。",
        "3. `summary_score_modes.md`：PATH / 正文分开 dense scoring 的诊断。",
        "4. `summary_improvement_experiments.md`：长度归一化与 routing 改进诊断。",
        "",
        "## 正式结果 JSON",
        "",
        "| 文件模式 | 含义 |",
        "| --- | --- |",
        "| `arxiv_predcomplete_aligned_dense_b{300,500,1000}.json` | 主结果：`full_text_main`。 |",
        "| `arxiv_predcomplete_content_only_b{300,500,1000}.json` | 诊断：层级 dense scoring 只看正文。 |",
        "| `arxiv_predcomplete_path_only_b{300,500,1000}.json` | 诊断：层级 dense scoring 只看 PATH。 |",
        "| `arxiv_predcomplete_content_len220_b{300,500,1000}.json` | 改进诊断：正文-only + 约 220 字符窗口。 |",
        "| `arxiv_predcomplete_content_routed_m{3,8}_b{300,500,1000}.json` | routing 诊断：先选 section 再检索。 |",
        "",
        "## 非正式烟测文件",
        "",
        "`smoke_*` 文件只用于开发过程中的小样本检查，不作为论文/报告结果引用。",
    ]
    (RESULTS / "README.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_score_modes()
    write_improvement_experiments()
    write_final_summary()
    write_results_readme()
    print("Wrote summary_score_modes.md, summary_improvement_experiments.md, summary_final.md, results/README.md")


if __name__ == "__main__":
    main()
