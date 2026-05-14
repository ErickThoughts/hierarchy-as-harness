# Realdata Results Summary

Canonical results in this delivery package:

- `results/eval97_predcomplete_postfix_b300.json`
- `results/eval97_predcomplete_postfix_b500.json`
- `results/eval97_predcomplete_postfix_b1000.json`

Task set: `data/tasks_realdata_bodyrich_inspect_pred_complete_97_for_runner.jsonl` (`n=97`).

## Main Metrics

| Budget | Metric | Hier Gold | Hier Pred | Flat |
| ---: | --- | ---: | ---: | ---: |
| 300 | task_success_mean | 0.3265 | 0.3210 | 0.2914 |
| 300 | inspect_evidence_score_mean | 0.3531 | 0.3385 | 0.3397 |
| 300 | evidence_coverage_mean | 0.3531 | 0.3385 | 0.3397 |
| 300 | evidence_hit@1_mean | 0.4536 | 0.4639 | 0.4742 |
| 500 | task_success_mean | 0.4001 | 0.3627 | 0.3144 |
| 500 | inspect_evidence_score_mean | 0.4585 | 0.3861 | 0.4283 |
| 500 | evidence_coverage_mean | 0.4585 | 0.3861 | 0.4283 |
| 500 | evidence_hit@1_mean | 0.5155 | 0.4639 | 0.4845 |
| 1000 | task_success_mean | 0.4358 | 0.4202 | 0.3976 |
| 1000 | inspect_evidence_score_mean | 0.5572 | 0.5099 | 0.5674 |
| 1000 | evidence_coverage_mean | 0.5572 | 0.5099 | 0.5674 |
| 1000 | evidence_hit@1_mean | 0.4742 | 0.4227 | 0.4948 |

## Task Success Delta

| Budget | Gold - Flat | Pred - Flat |
| ---: | ---: | ---: |
| 300 | +0.0351 | +0.0296 |
| 500 | +0.0857 | +0.0483 |
| 1000 | +0.0382 | +0.0227 |

## Naming Contract

The runner summary naming is aligned to the existing result JSON files. Main keys include:

- `task_success_mean`
- `keyword_recall_mean`
- `inspect_evidence_score_mean`
- `truncated_last_mean`
- `evidence_coverage_mean`
- `evidence_hit@1_mean`
- `score_task_mean`
- `score_evidence_mean`
- `score_process_mean`

The JSON result files remain the source of truth; this Markdown file is the readable summary.
