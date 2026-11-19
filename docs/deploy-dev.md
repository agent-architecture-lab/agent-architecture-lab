---
type: runbook
subject: community operations agent dev deployment
created: 2026-10-03
updated: 2026-11-05
author: jihyun
tags: [aws, discord, deployment]
related: [docs/superpowers/specs/2026-10-03-001-agent-architecture-lab-design.md]
---

# Dev deployment runbook

## Local packaging gate (no AWS access)

Use a clean checkout of the reviewed candidate. `uv.lock` is the dependency source of truth;
`src/requirements.txt` is its generated, hash-pinned runtime export for SAM.
Run `uv run --locked python scripts/export_requirements.py --write` only when intentionally
updating the export, then review and commit the generated difference before building.
The default command below checks it without modifying the source or lock.

```bash
uv sync --locked --all-groups --python 3.12
uv run --locked python scripts/export_requirements.py
uv run --locked python scripts/build_faq_index.py build --encoder lexical --check
uv run --locked pytest -q
sam validate --lint --template-file infra/template.yaml
SAM_BUILD_IMAGE=public.ecr.aws/sam/build-python3.12@sha256:6b977f28341c892f743070ef945b600f1b257b668003720dc3bc9b1839fcd666
docker pull --platform linux/amd64 "$SAM_BUILD_IMAGE"
sam build --use-container --skip-pull-image --no-cached --build-image "$SAM_BUILD_IMAGE" --template-file infra/template.yaml
uv run --locked python scripts/verify_package.py --image "$SAM_BUILD_IMAGE" --synthetic-index tests/fixtures/faq-packaging-index.json --output evaluations/poc/release-manifest.json
```

The image is SAM 1.166.2 for Python 3.12 x86_64, pinned by digest. Docker must support
Linux amd64 execution (including emulation on Apple Silicon). Host verification dependencies
are in the locked dev group; they are excluded from Lambda packages. The import probe runs
with isolated Python, no site packages, no network, and read-only package mounts.

On macOS, if the shell cannot find the Docker credential helper or SAM cannot find
the Docker socket, set these for the current shell before running the commands.
They do not change Docker or system settings:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
export DOCKER_HOST="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
```

The gate checks all seven function packages against the 19 Linux Python 3.12 runtime
distributions, preserves the template resource set (including Dispatch and the operational alarms),
imports each handler and native dependency, and loads the FAQ using the packaged loader's
actual default path. It records source hashes, candidate commit and tracked dirty state,
original package content hashes, and fixture-copy content hashes in the manifest.
These content hashes are not an AWS deployment ZIP `CodeSha256`.
Python version markers use the actual patch version read from the pinned container,
recorded as `marker_python_full_version`; they do not assume Python 3.12.0.

The original `FaqFunction` package contains `assets/faq/index.json`. The verifier checks
its hash, verifies that the default runtime loader rejects the draft, and reads the eight
records with explicit inspection access. `original_study_faq_probe` records this result.
It separately checks synthetic fixtures in disposable copies of all seven packages.
`deploy_ready=false` remains the release status. Event-provided synthetic indexes still
work; a missing, damaged or disabled packaged index returns a safe stage error.
The `--synthetic-index` file must exist inside the repository after resolving symlinks;
outside paths are rejected before export, package copying, or Docker probes.

The package verifier removes the requested output manifest before starting, so a failed
run cannot leave an old success file at that output path. Choose a task-owned output path.
Model calls, Discord requests, IAM changes and deployments are not part of this gate.

## Study FAQ generation and local search

`assets/faq/source.md` contains the eight reviewed questions and answers. The registry
`assets/faq/sources.json` pins upstream commits, document hashes and cited line ranges.
The generator rejects corpus hash, ID, citation or policy changes that disagree with
the registry. Keep both source files and the generated artifact in the same change.

```bash
uv run --locked python scripts/build_faq_index.py build --encoder lexical
uv run --locked python scripts/build_faq_index.py build --encoder lexical --check
uv run --locked python scripts/build_faq_index.py search '실습 중 질문은 어디로 보내나요?' --top-k 3
```

The deterministic offline encoder uses a corpus vocabulary of words and character pairs
and triples. Document and query vectors use the same feature counts and inverse document
frequencies. Search returns ranked source records and pinned citation URLs. Zero overlap
returns `no_match`. Recognized excluded operational questions return `excluded`. A
multi-word query whose top record shares features with only one query word receives
`low_evidence`. Each hit lists those words; even a `matches` result is a retrieval
candidate requiring source review before using it in an answer. The metadata keeps
`runtime_enabled=false`. Local inspection uses `load_index(allow_draft=True)` explicitly.

For a separately authorized model experiment, `build --encoder openai --output <separate.json>`
uses `OPENAI_API_KEY` from the environment and calls `text-embedding-3-small`. CI and the
canonical lexical build use only the offline encoder. The study registry retains the last
verified upstream document hashes; change review must recheck those pinned originals.

References: [SAM build](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-cli-command-reference-sam-build.html),
[uv lockfile export](https://docs.astral.sh/uv/concepts/projects/export/).

## Account owner steps

1. Create a Discord application and copy its application ID and public key.
2. Create the OpenAI API key secret in AWS Secrets Manager. Do not put its value in a file or command history.
3. Choose the email address that receives the 5, 8, and 10 USD monthly AWS budget alerts.
4. Review the complete resource/IAM change list and rollback artifact. Confirm an existing
   SNS topic with an approved, confirmed dev recipient and supply `OperationsAlarmTopicArn`.
   Freeze dev Discord traffic and let active runs finish before changing Lambda and workflow
   event contracts. After the local
   packaging gate and the remaining U05/U08 release gates pass, deploy only the dev stack
   from the reviewed build output (never directly from the raw source template):

```bash
sam deploy --region ap-northeast-2 --template-file .aws-sam/build/template.yaml --stack-name community-ops-dev --capabilities CAPABILITY_IAM --parameter-overrides Environment=dev OpenAISecretArn=SECRET_ARN FaqModel=OWNER_APPROVED_MODEL DiscordApplicationId=APPLICATION_ID DiscordPublicKey=PUBLIC_KEY BudgetAlertEmail=ALERT_EMAIL OperationsAlarmTopicArn=APPROVED_TOPIC_ARN
```

5. Copy the current `DiscordInteractionEndpoint` output into the Discord application interaction endpoint setting. Confirm that it is the `community-ops-dev` output, not an earlier endpoint.
6. Run the no-model canary below before opening the command. After the canary and
   the approved FAQ and model checks pass, register only `/ask` and run one approved
   synthetic FAQ question.
7. Confirm Discord immediately shows a deferred response, then locate the same `run_id` in ingress and dispatch Lambda logs. Do not copy interaction tokens or request bodies into notes.
8. Confirm one Standard Step Functions execution starts for that `run_id` and the Discord result Lambda PATCHes the original deferred response.
9. Repeat the identical dispatch payload only in a controlled dev test. Confirm the duplicate converges on the existing execution rather than starting a second workflow.
10. Confirm the success run leaves the operational alarms clear. For the controlled failure run,
    record the metric, actual alarm state transition and receipt by the topic subscriber.
    Inspect `ExecutionsTimedOut` separately from `ExecutionsFailed` and Discord result errors.
    With two healthy test requests expected, confirm two terminal receipts by run ID; a quiet
    alarm by itself provides no evidence of traffic or delivery.
11. Inspect the benchmark JSONL record and benchmark-gate JSON evidence before changing a prompt, model, RAG, context, or Reflection default. Do not send real personal data.

Do not deploy prod, change IAM outside this stack, or delete resources as part of this runbook.

## Existing dispatch log group and payload boundary

The existing dev dispatch log group was created outside CloudFormation. Check old log
retention requirements with the account owner. The account owner then sets retention to
seven days on that exact group using its deployed function name and verifies all eight
group retentions. A regular stack update does not recreate or change that existing group.

Before a real Discord interaction, run a controlled synthetic interaction through the
deployed dev candidate with known markers for the token and question. Exercise
the answer marker in the local synthetic suite, and use a runtime-disabled FAQ for the
first deployed no-model canary. Confirm the input markers' absence from Step Functions
execution input/output, Standard event history and CloudWatch logs. Record booleans and
event counts only. An invalid synthetic token's delivery failure is expected and can
exercise result alarm delivery. Confirm request object expiry, and use a successful
approved dev request to confirm object cleanup and that the response body is absent
from the execution history and logs. The app denies reads after ten minutes; abandoned
objects, including those recreated by a late duplicate delivery, use the bucket's
one-day expiry policy. Keep the Discord command paused if
the deployment or rollback would restore raw payload handling.
