---
type: guide
subject: community operations agent benchmark records
created: 2026-10-03
updated: 2026-10-09
author: jihyun
tags: [agents, evaluation]
related: [evaluations/cases.json]
---

# Benchmark records

Run the locked synthetic cases and write a JSONL result outside Git:

```bash
uv run python evaluations/run_benchmark.py --output /tmp/community-ops-benchmark.jsonl
```

Each record has `case_id`, `status`, `latency_ms`, `input_tokens`, `output_tokens`, and `estimated_cost_usd`. Never add source text, interaction tokens, or secrets to the record.

Promote a prompt, model, RAG, context, or Reflection default only after comparing a baseline and candidate record set with the same case IDs:

```bash
uv run python evaluations/compare_benchmarks.py \
  --baseline /tmp/baseline.jsonl \
  --candidate /tmp/candidate.jsonl \
  --improvement-metric estimated_cost_usd \
  --code-commit-sha COMMIT_SHA \
  --model-id MODEL_ID \
  --settings-digest SETTINGS_DIGEST \
  --output /tmp/benchmark-gate.json
```

The candidate is blocked when any run fails, success or citation rate falls, case IDs differ, or the declared improvement metric does not improve. Review the JSON evidence before changing a default.
