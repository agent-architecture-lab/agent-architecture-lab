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

## Discord /ask checks

Run `uv run --locked python evaluations/run_ask_retrieval.py` to check retrieval and abstention on the fixed sample. It inspects the draft index offline and exits nonzero if any expected decision or source ID differs. This does not make the index eligible for serving. The generic benchmark below uses a stub stage and does not measure answer quality.

For a live quality review, freeze the FAQ version, model, approved call limit and case IDs before running. Include an answerable paraphrase, insufficient evidence, an excluded request and a question with an instruction to override the FAQ. For each case, a human checks that every material claim follows from the approved source, the linked citation is correct, and the response abstains when support is insufficient. Record case ID, source ID, expected behavior, pass/hold and a fixed failure reason without saving message text. All required cases must pass and no material claim may lack support. A citation string in an answer alone is not a pass.

Run the locked synthetic cases and write a JSONL result outside Git:

```bash
uv run python evaluations/run_benchmark.py --output /tmp/community-ops-benchmark.jsonl
```

Each record has `case_id`, `status`, `latency_ms`, `input_tokens`, `output_tokens`, and `estimated_cost_usd`. Never add source text, interaction tokens, or secrets to the record.
