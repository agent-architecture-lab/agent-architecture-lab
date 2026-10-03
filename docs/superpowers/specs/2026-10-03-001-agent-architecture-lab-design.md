---
type: design
subject: agent-architecture-lab shared community operations agent
created: 2026-10-03
updated: 2026-10-03
author: jihyun
tags: [study, agents, aws, discord, openai]
related: []
---

# Agent Architecture Lab design

## Goal

Six participants build and operate one Discord-based community operations agent during an eight-week study. The system accepts only anonymized or synthetic inputs during the study and demonstrates screening, matching, FAQ answers, and retrospective feedback end to end.

Success means every participant has a personal GitHub fork, reviewed pull requests, and at least one deployed track. The final demo must reach at least 80% success on an anonymized evaluation set and report at least one measured value per module: accuracy, latency, or cost.

## Scope

Included:

- Four modules: screening, matching, FAQ, and retrospectives
- Reflection, RAG, and Multi-Agent patterns
- A Discord slash-command test interface on AWS
- Evaluation data, benchmark results, and an end-to-end demo

Excluded until a later, separately approved phase:

- Real community data or personally identifiable information
- A production stack
- A persistent database, vector database, containers, and a custom web UI

## Repository boundary

There is one public upstream repository and one deployable source of truth. Each participant forks it and opens pull requests from a feature branch in their own fork. Forks satisfy the personal portfolio goal without splitting the service into competing repositories.

The shared repository begins with this layout:

```text
agent-architecture-lab/
├── src/
│   ├── agents/                  # screening, matching, faq, reflection
│   ├── workflows/community_run.py
│   └── handlers/discord.py
├── assets/faq/                  # source documents and generated retrieval index
├── evaluations/                 # fixed inputs, expected results, benchmark outputs
├── notebooks/                   # weekly experiments, not deployed code
├── scripts/build_faq_index.py
├── infra/template.yaml
├── tests/
├── pyproject.toml
└── README.md
```

`src` is deployable code. `notebooks` is learning evidence only. An experiment moves into `src` only when it has a typed input and output contract, a fixed-sample test, and a measured result.

## Agent design

Every module receives and returns a Pydantic model. LLMs may create bounded categorical labels, a draft answer, or a critique. Python code makes all eligibility, score, routing, and final acceptance decisions.

| Pattern | Implementation | Guardrail |
|---|---|---|
| Deterministic picker | screening and matching rules consume structured LLM labels | LLM output never directly selects a person or team |
| RAG | build an embedding index from versioned FAQ documents; retrieve top three chunks with citations | no web search or unversioned source |
| Reflection | reviewer critiques one draft and permits at most one revision | one retry only; code decides whether the revision is accepted |
| Multi-Agent | role-specific modules exchange typed workflow state | no autonomous agent-to-agent loop |

AWS Step Functions represents the prescribed workflow and its retry and failure paths. It is not the decision maker. The agent workflow remains deterministic and inspectable in the shared Python contracts.

## AWS and Discord architecture

```text
Discord slash command
  -> API Gateway HTTP API
  -> Discord ingress Lambda
  -> Step Functions Standard
       -> screening Lambda
       -> matching Lambda
       -> FAQ RAG Lambda
       -> reflection Lambda
       -> Discord result Lambda
```

The ingress Lambda validates the Discord signature, acknowledges the interaction with a deferred response, and starts the workflow. Discord requires the initial response within three seconds; a follow-up token remains usable for fifteen minutes. The final Lambda posts the result using that token. See the [Discord interaction response rules](https://docs.discord.com/developers/interactions/receiving-and-responding).

The AWS SAM template creates only API Gateway, Lambda functions, a Step Functions state machine, least-privilege roles, Secrets Manager access for the OpenAI API key, CloudWatch logs, and a failure alarm. Logs retain for seven days. The first stack is `dev`; `prod` is not created during the study.

## Cost limit

The eight-week limit is USD 100.

| Allocation | Limit | Control |
|---|---:|---|
| OpenAI API | USD 70 | low-cost model by default, output-token limits, one reflection retry, higher-quality model only for named benchmarks |
| AWS | USD 10 | serverless services only, no VPC, no always-on compute, seven-day log retention |
| Reserve | USD 20 | approved quality comparison or unexpected rerun |

Step Functions Standard includes 4,000 free state transitions each month and charges by transition after that. Lambda includes 1 million requests and 400,000 GB-seconds each month. Those services are not expected to be the primary cost at this study scale. See [Step Functions pricing](https://aws.amazon.com/step-functions/pricing/) and [Lambda pricing](https://aws.amazon.com/lambda/pricing/).

The default model is the lowest-cost model that meets the weekly evaluation threshold. A higher-quality model is used only in a benchmark issue. Each execution logs model, input tokens, output tokens, estimated model cost, latency, and workflow result. AWS Budgets alerts at 50%, 80%, and 100% of the AWS allocation; the OpenAI project has matching usage alerts. Alerts do not guarantee a hard external API stop, so per-run token ceilings are mandatory.

## Quality, safety, and failure behavior

- Only anonymized or synthetic samples are committed or sent to an LLM.
- Secrets never enter Git, notebooks, logs, or Discord messages.
- Inputs are validated before an LLM call. Invalid inputs stop with an explicit status.
- A failed module produces a typed failure result and ends the workflow; later modules do not silently run on missing data.
- RAG outputs must include source identifiers. A missing source is a failed answer.
- Unit tests cover decision rules and data contracts. Dev integration tests invoke actual Discord commands. The final benchmark uses a locked evaluation sample.

## Collaboration and release flow

Each issue defines its deliverable, pass condition, and measurement. GitHub Project uses only week, track, status, owner, pull request, and deployment environment fields. Study work and deployment work use separate issues.

Participants use `feature/<issue-number>-<slug>` branches in their forks. A pull request needs one participant review before merge. `main` remains deployable and merges deploy to the `dev` Discord bot. A tagged release may be promoted only after the end-to-end evaluation passes, the measured cost is checked, and the account owner performs the deployment action.

## Suggested eight-week sequence

| Week | Shared result |
|---|---|
| 1 | repository, contracts, synthetic data, Discord acknowledgement |
| 2 | screening baseline and deterministic picker |
| 3 | matching rules and evaluation |
| 4 | FAQ RAG with cited answers |
| 5 | reflection with bounded revision |
| 6 | Step Functions Multi-Agent workflow |
| 7 | benchmarks, cost controls, and failure paths |
| 8 | end-to-end demo, release tag, and presentation materials |
