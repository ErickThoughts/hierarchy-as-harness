# arXiv 对齐检索交付包（2026-05-13）

本目录为 **arXiv pred-complete 语料** 上的 **仅检索** 评估包。当前版本把层级臂改为 **多层 ToolSpace leaf/path chunk**：每个层级候选块显式包含 `PATH:` 父链路径 + 子树证据文本；Flat 臂为 realdata 对齐的 flat_react 风格多 query 融合。

## 目录说明

| 路径 | 说明 |
|------|------|
| `code/eval_arxiv_predcomplete_retrieval.py` | 主评估脚本（默认数据与输出均相对本包根目录解析）。 |
| `code/summarize_arxiv_experiments.py` | 从现有 JSON 重新生成横向对比和最终总览 Markdown。 |
| `code/agent_delivery/` | 评估所依赖的代码快照（与主仓库可能不同步，以本目录为准）。 |
| `data_refs/test_data_full_merged_pred_complete.jsonl` | 合并后的 arXiv 行流语料（含 `predicted_level` 等）。 |
| `data_refs/tasks_arxiv_bodyrich_150_pred_complete_for_runner.jsonl` | 与本语料对齐后的任务集。 |
| `results/summary_final.md` | **最终总览入口**：该看哪套结果、核心结论、按题型摘要。 |
| `results/README.md` | `results/` 目录内正式结果、诊断结果、烟测文件的说明。 |
| `results/arxiv_predcomplete_aligned_dense_b{300,500,1000}.json` | 各字符预算下的完整逐题结果 + `summary`。 |
| `results/summary_aligned.md` | 总体表 + **按 `task_type` 分层（per-type）** 表。 |
| `results/arxiv_predcomplete_content_only_b{300,500,1000}.json` | 诊断实验：层级臂 dense scoring 仅使用正文，evidence 仍输出 `PATH + 正文`。 |
| `results/arxiv_predcomplete_path_only_b{300,500,1000}.json` | 诊断实验：层级臂 dense scoring 仅使用 `PATH:` 行，evidence 仍输出 `PATH + 正文`。 |
| `results/summary_score_modes.md` | `full_text` / `content_only` / `path_only` 三种层级打分模式的横向对比。 |
| `results/arxiv_predcomplete_content_len220_b{300,500,1000}.json` | 改进诊断：正文打分 + leaf/path body 按约 220 字符窗口切分。 |
| `results/arxiv_predcomplete_content_routed_m{3,8}_b{300,500,1000}.json` | 改进诊断：正文打分 + top section routing 后只搜被选 subtree。 |
| `results/summary_improvement_experiments.md` | 主结果、content-only、length-normalized、routed 的横向对比和结论。 |

## 推荐阅读顺序

1. `results/summary_final.md`：最终总览，包含该用哪套结果和核心结论。
2. `results/summary_aligned.md`：realdata 对齐主实验，含总体指标和各题型全指标。
3. `results/summary_score_modes.md`：`PATH + 正文` / `content_only` / `path_only` 三套 dense scoring 诊断。
4. `results/summary_improvement_experiments.md`：长度归一化和 routing 的改进诊断。

`results/smoke_*` 文件只用于开发过程的小样本检查，不作为正式实验结果引用。

## 任务条数说明（文件名里的 150）

任务文件名仍沿用 `...150...` 历史命名；**当前 `data_refs/tasks_*.jsonl` 内为 77 条**（每行一题），故各结果中 **n=77**。若之后任务文件扩充，重新跑评估即可，`summary` 中的 `n_tasks` 会随之更新。

评估开始时会校验每条任务的 `gold_nodes` 均出现在所选语料的行节点上，不对齐则报错退出。

## 运行命令

在本包根目录（即包含 `code/`、`data_refs/` 的目录）执行（语料参数为 `--test-jsonl`）：

```bash
cd delivery/arxiv_aligned_retrieval_20260513

python3 code/eval_arxiv_predcomplete_retrieval.py \
  --test-jsonl data_refs/test_data_full_merged_pred_complete.jsonl \
  --tasks data_refs/tasks_arxiv_bodyrich_150_pred_complete_for_runner.jsonl \
  --budgets 300,500,1000 \
  --out-template results/arxiv_predcomplete_aligned_dense_b{budget}.json \
  --summary-md results/summary_aligned.md
```

不传参时，默认值已指向上述 `data_refs/` 路径与 `results/` 下输出模板。

### PATH / 正文分开打分的诊断实验

主结果 `summary_aligned.md` 使用 `--hier-score-mode full_text`，即 `PATH + 正文` 一起参与 dense scoring，这与 realdata-aligned 口径一致。为诊断 PATH 文本和正文文本各自的影响，可分别运行：

```bash
python3 code/eval_arxiv_predcomplete_retrieval.py \
  --hier-score-mode content_only \
  --budgets 300,500,1000 \
  --out-template results/arxiv_predcomplete_content_only_b{budget}.json \
  --summary-md results/summary_content_only.md

python3 code/eval_arxiv_predcomplete_retrieval.py \
  --hier-score-mode path_only \
  --budgets 300,500,1000 \
  --out-template results/arxiv_predcomplete_path_only_b{budget}.json \
  --summary-md results/summary_path_only.md
```

这两套诊断实验不做 PATH/正文加权混合；dense scoring 分别只看正文或只看 PATH。最终 budget evidence 仍使用原始 `PATH + 正文` chunk，因此展示与指标计算口径不变。

### Length-normalized / routed 诊断实验

用于进一步区分 chunk 边界和路由约束的影响：

```bash
python3 code/eval_arxiv_predcomplete_retrieval.py \
  --hier-score-mode content_only \
  --hier-retrieval-mode length_normalized \
  --hier-window-chars 220 \
  --budgets 300,500,1000 \
  --out-template results/arxiv_predcomplete_content_len220_b{budget}.json \
  --summary-md results/summary_content_len220.md

python3 code/eval_arxiv_predcomplete_retrieval.py \
  --hier-score-mode content_only \
  --hier-retrieval-mode routed_leaf_path \
  --hier-route-m 8 \
  --budgets 300,500,1000 \
  --out-template results/arxiv_predcomplete_content_routed_m8_b{budget}.json \
  --summary-md results/summary_content_routed_m8.md
```

`length_normalized` 保留 leaf/path 层级格式，但把正文按固定长度窗口拆小；`routed_leaf_path` 先 dense route top-level sections，再只在被选 subtree 中检索。

### 仅根据已有 JSON 重写汇总 Markdown

不重新建索引、不打分时：

```bash
cd delivery/arxiv_aligned_retrieval_20260513

python3 code/eval_arxiv_predcomplete_retrieval.py \
  --regenerate-summary-md-only \
  --from-result-json \
    results/arxiv_predcomplete_aligned_dense_b300.json \
    results/arxiv_predcomplete_aligned_dense_b500.json \
    results/arxiv_predcomplete_aligned_dense_b1000.json \
  --summary-md results/summary_aligned.md
```

重新生成横向对比和最终总览：

```bash
python3 code/summarize_arxiv_experiments.py
```

## 实现与元数据约定

- **`sys.path`**：向 `code/` 注入路径以加载 `agent_delivery`，不依赖不存在的 `delivery/core`。
- **结果 JSON 的 `summary.config`**：`test_jsonl` / `tasks` 写入**调用时解析后的绝对路径**，便于审计与复现。
- **`summary_aligned.md`**：每个 budget 下除总表外，附带各指标的 **per-type** 表（`cross_section_conflict` / `multi_hop` / `niche_fact` / `scope_collection` / `self_correct`）。
- **与 `runner_bodyrich` 对齐范围**：Flat 臂同 **`run_flat_react_episode`**（`_query_variants_for_flat_react` 每轮 + **`gather_flat_candidates`**，内含 `_build_retrieval_queries` 的 raw/rewrite/HyDE 开关）。层级臂不跑 ReAct/LLM agent，但使用 `ToolSpace` 的多层 `leaf/path` evidence pool，并用 `budget_eval._build_retrieval_queries` 的多 query 融合做 retrieval-only 打分。**不包含** compose / LLM judge。
- **层级 dense scoring 模式**：默认 `full_text` 使用完整 `PATH + 正文` chunk 打分，是主结果；`content_only` / `path_only` 是诊断结果，不替代主表。
- **层级 retrieval 模式**：默认 `global_leaf_path` 是主结果；`length_normalized` / `routed_leaf_path` / `routed_length_normalized` 是诊断或改进实验。
- **多层级检查**：`results/summary_aligned.md` 每个 budget 下记录 Gold/Pred 的 `path_depth_mean` 与 `max`；当前正式结果 max depth=5，说明不是单层 section→fact。

## 环境变量（可选）

Flat 多轮检索：`FLAT_REACT_SEARCH_ROUNDS`（默认 3）、`FLAT_REACT_K_PER_ROUND`（默认 64）。嵌入模型：`EMBEDDING_MODEL` 或 `--embedding-model`。
