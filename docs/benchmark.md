---
type: guide
subject: community operations agent benchmark records
created: 2026-10-03
updated: 2026-10-03
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
