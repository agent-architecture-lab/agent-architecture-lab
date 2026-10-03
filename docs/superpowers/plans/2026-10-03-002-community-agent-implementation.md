---
type: implementation-plan
subject: community operations agent implementation
created: 2026-10-03
updated: 2026-10-03
author: jihyun
tags: [plan, agents, aws, discord]
related: [docs/superpowers/specs/2026-10-03-001-agent-architecture-lab-design.md]
---

# Community Operations Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deployable Discord community-operations agent whose decisions are deterministic, whose LLM work is bounded, and whose end-to-end workflow is measurable.

**Architecture:** Python domain modules own typed contracts and can run locally. AWS SAM deploys a thin Discord ingress Lambda, a Step Functions Standard workflow, module Lambdas, and a Discord result Lambda; Step Functions executes a fixed route but never makes a business decision.

**Tech Stack:** Python 3.12, Pydantic, OpenAI Python SDK, PyNaCl, pytest, AWS SAM, Lambda, API Gateway HTTP API, Step Functions Standard, Secrets Manager, CloudWatch.

**Spec:** `docs/superpowers/specs/2026-10-03-001-agent-architecture-lab-design.md`

## 현재 상태

- [x] Task 1-6 구현 완료: typed contracts, 결정형 stages, fail-closed FAQ, 1회 reflection, 측정 workflow, SAM stage adapters.
- [x] 로컬 검증: `uv run --with pytest pytest -q` 21개 통과, `sam validate --lint --template-file infra/template.yaml` 통과, `sam build --template-file infra/template.yaml` 통과.
- [ ] Task 6 커밋 `6722161`을 `origin/codex/task-1-typed-contracts`에 push한다. 계획 작성 직전 실측에서 이 브랜치는 원격보다 1커밋 앞서고 작업 트리는 clean이었다.
- [ ] Task 7: Discord ingress와 안전한 결과 전송을 구현한다.
- [ ] Task 8: PR CI, 비용 알림, dev 배포 runbook을 추가한다.

`cfn-guard`는 현재 설치되어 있지 않아 정책 검증은 아직 실행하지 않았다. AWS 리소스와 배포는 0건이다.

## 이번 세션 실행 계획

1. Task 6를 push한 뒤 원격 SHA와 clean working tree를 확인한다.
2. Task 7 테스트부터 추가한다. 잘못된 서명은 `401`이고 Step Functions를 시작하지 않으며, 유효한 명령은 3초 안에 deferred response `{"type": 5}`를 반환하는지 검증한다.
3. Discord public key 검증, `StartExecution`, interaction token의 최소 workflow state 전달, `allowed_mentions: {"parse": []}`인 성공 또는 실패 follow-up을 구현한다.
4. SAM에 ingress API와 두 Lambda를 실제 리소스로 연결하고, ResultHandlerArn 임시 parameter를 제거한다. ingress에는 Step Functions 시작 권한만 부여한다.
5. focused tests, 전체 tests, SAM lint/build를 재실행한다. 배포, IAM 변경, secret 생성, Discord 설정은 Task 8 runbook과 account owner 작업으로 남긴다.

## Global Constraints

- Accept only anonymized or synthetic data; never commit, log, or send personal data to an LLM.
- An LLM may return bounded labels, drafts, or critiques; Python code makes all final eligibility, scoring, routing, and acceptance decisions.
- Use one public upstream repository, contributor forks, review before merge, and `main` as the deployable source of truth.
- Use AWS SAM and only API Gateway, Lambda, Step Functions, Secrets Manager, and CloudWatch in `dev`.
- Do not create `prod`, a database, vector database, VPC, container service, or custom web UI.
- Default to the lowest-cost model that meets the locked evaluation threshold; set output-token limits and permit one reflection revision at most.
- Retain CloudWatch logs for seven days and expose estimated model cost, latency, workflow result, and token counts per run.
- Initial Discord acknowledgement must be deferred before execution; never expose secrets in Discord, Git, notebooks, or logs.

## Review Focus

- A malformed Discord signature must return `401` and must not start a workflow; Task 7 owns this test.
- An LLM label outside the allowed enum must become a typed failed result, not a guessed decision; Task 2 owns this test.
- A FAQ answer without a selected source must fail closed and must not send an uncited claim; Task 3 owns this test.
- A reflection result must never cause a second revision; Task 4 owns this test.
- A workflow failure after the deferred response must post one clear failure follow-up and must not run later stages; Task 6 owns this test.

## File Structure

```text
src/community_ops/models.py              # all shared Pydantic contracts
src/community_ops/config.py              # validated environment settings
src/community_ops/screening.py           # label parsing and deterministic eligibility
src/community_ops/matching.py            # deterministic score and assignment
src/community_ops/rag.py                 # local index build, retrieval, cited answer checks
src/community_ops/reflection.py           # one-pass review and acceptance gate
src/community_ops/workflow.py             # fixed stage route and typed failures
src/handlers/discord_ingress.py           # signature validation and deferred callback
src/handlers/stages.py                    # Lambda adapters for domain stages
src/handlers/discord_result.py            # safe Discord follow-up sender
scripts/build_faq_index.py                # build versioned FAQ index
evaluations/cases.json                    # locked synthetic evaluation cases
evaluations/run_benchmark.py              # write JSONL measurements
infra/template.yaml                       # complete dev stack
tests/...                                 # unit, workflow, handler tests
```

### Task 1: Package, settings, and typed contracts

**Files:**
- Create: `pyproject.toml`, `src/community_ops/__init__.py`, `src/community_ops/models.py`, `src/community_ops/config.py`, `tests/test_models.py`, `.gitignore`, `.env.example`

**Interfaces:**
- Produces `RunRequest`, `StageResult`, `RunResult`, and `Settings` for every later task.

- [ ] **Step 1: Write failing contract tests**

```python
def test_stage_result_rejects_unknown_status():
    with pytest.raises(ValidationError):
        StageResult(stage="screening", status="maybe")
```

- [ ] **Step 2: Run the failing test**

Run: `pytest tests/test_models.py -v`

Expected: FAIL because `community_ops.models` does not exist.

- [ ] **Step 3: Add the minimal contracts and settings**

```python
class StageStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class StageResult(BaseModel):
    stage: str
    status: StageStatus
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
```

`Settings` must require `OPENAI_API_KEY` only when a live model call is requested; local rule and retrieval tests must run without it.

- [ ] **Step 4: Run the focused test and formatting checks**

Run: `pytest tests/test_models.py -v && python -m compileall src`

Expected: PASS with no real API call.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore .env.example src/community_ops tests/test_models.py
git commit -m "feat: add typed agent contracts"
```

### Task 2: Deterministic screening and matching

**Files:**
- Create: `src/community_ops/screening.py`, `src/community_ops/matching.py`, `tests/test_screening.py`, `tests/test_matching.py`

**Interfaces:**
- Consumes: `RunRequest` and `StageResult` from Task 1.
- Produces: `screen_application(request, labels)` and `rank_matches(candidates, constraints)` returning `StageResult`.

- [ ] **Step 1: Write failing decision-rule tests**

```python
def test_screening_uses_code_not_model_to_reject_ineligible_input():
    result = screen_application(sample_request(), {"attendance_commitment": "low"})
    assert result.status is StageStatus.SUCCEEDED
    assert result.data["eligible"] is False

def test_screening_rejects_unknown_model_label():
    result = screen_application(sample_request(), {"attendance_commitment": "unknown"})
    assert result.status is StageStatus.FAILED
```

- [ ] **Step 2: Run the focused tests**

Run: `pytest tests/test_screening.py tests/test_matching.py -v`

Expected: FAIL because the functions do not exist.

- [ ] **Step 3: Implement fixed enums, eligibility, and transparent scores**

```python
def screen_application(request: RunRequest, labels: dict[str, str]) -> StageResult:
    if labels.get("attendance_commitment") not in {"high", "medium", "low"}:
        return StageResult(stage="screening", status="failed", error="invalid label")
    return StageResult(stage="screening", status="succeeded", data={
        "eligible": labels["attendance_commitment"] != "low",
        "labels": labels,
    })
```

`rank_matches` must return the numeric component scores and use a stable secondary sort key so equal scores produce repeatable output.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_screening.py tests/test_matching.py -v`

Expected: PASS; equal-score results are stable and invalid labels fail closed.

- [ ] **Step 5: Commit**

```bash
git add src/community_ops/screening.py src/community_ops/matching.py tests/test_screening.py tests/test_matching.py
git commit -m "feat: add deterministic screening and matching"
```

### Task 3: Small, cited RAG without a vector service

**Files:**
- Create: `assets/faq/source.md`, `scripts/build_faq_index.py`, `src/community_ops/rag.py`, `tests/test_rag.py`

**Interfaces:**
- Consumes: a versioned JSON index of `{id, text, embedding}` records and a query embedding function.
- Produces: `answer_faq(question, index, embed, generate) -> StageResult` with `source_ids`.

- [ ] **Step 1: Write failing RAG tests**

```python
def test_faq_answer_carries_retrieved_source_ids():
    result = answer_faq("When do we meet?", index(), embed_stub, answer_stub)
    assert result.data["source_ids"] == ["faq-001"]

def test_faq_answer_fails_when_generator_omits_sources():
    result = answer_faq("When do we meet?", index(), embed_stub, lambda *_: "answer")
    assert result.status is StageStatus.FAILED
```

- [ ] **Step 2: Run the focused test**

Run: `pytest tests/test_rag.py -v`

Expected: FAIL because `answer_faq` does not exist.

- [ ] **Step 3: Implement index build and top-three cosine retrieval**

```python
def retrieve(query: list[float], index: list[IndexRecord], top_k: int = 3) -> list[IndexRecord]:
    return sorted(index, key=lambda item: cosine(query, item.embedding), reverse=True)[:top_k]
```

`build_faq_index.py` must chunk only `assets/faq/source.md`, use the configured embedding client, and write `assets/faq/index.json`. `answer_faq` must return `failed` if retrieval is empty or if the final answer does not include the selected source identifiers.

- [ ] **Step 4: Run focused tests and build an index only with an explicit key**

Run: `pytest tests/test_rag.py -v`

Expected: PASS without a network call.

- [ ] **Step 5: Commit**

```bash
git add assets/faq scripts/build_faq_index.py src/community_ops/rag.py tests/test_rag.py
git commit -m "feat: add cited FAQ retrieval"
```

### Task 4: Bounded reflection

**Files:**
- Create: `src/community_ops/reflection.py`, `tests/test_reflection.py`

**Interfaces:**
- Consumes: a draft string and injected `review` and `revise` callables.
- Produces: `reflect_once(draft, review, revise) -> StageResult`.

- [ ] **Step 1: Write failing reflection tests**

```python
def test_reflection_calls_revise_once_when_review_requests_change():
    revise = Mock(return_value="revised")
    result = reflect_once("draft", lambda _: {"accept": False}, revise)
    assert result.data["text"] == "revised"
    revise.assert_called_once()
```

- [ ] **Step 2: Run the focused test**

Run: `pytest tests/test_reflection.py -v`

Expected: FAIL because `reflect_once` does not exist.

- [ ] **Step 3: Implement the one-pass gate**

```python
def reflect_once(draft: str, review: ReviewFn, revise: ReviseFn) -> StageResult:
    verdict = review(draft)
    text = draft if verdict["accept"] else revise(draft, verdict)
    return StageResult(stage="reflection", status="succeeded", data={"text": text, "revised": not verdict["accept"]})
```

Invalid review payloads must return `failed`; no loop or recursive retry is permitted.

- [ ] **Step 4: Run the focused test**

Run: `pytest tests/test_reflection.py -v`

Expected: PASS; tests prove at most one revise call.

- [ ] **Step 5: Commit**

```bash
git add src/community_ops/reflection.py tests/test_reflection.py
git commit -m "feat: add bounded reflection"
```

### Task 5: Fixed workflow and measurement records

**Files:**
- Create: `src/community_ops/workflow.py`, `evaluations/cases.json`, `evaluations/run_benchmark.py`, `tests/test_workflow.py`

**Interfaces:**
- Consumes: stage functions from Tasks 2-4.
- Produces: `run_community_workflow(request, stages) -> RunResult` and one JSONL benchmark record per evaluation case.

- [ ] **Step 1: Write failing workflow tests**

```python
def test_workflow_stops_after_a_failed_stage():
    later = Mock()
    result = run_community_workflow(sample_request(), [failed_stage, later])
    assert result.status is StageStatus.FAILED
    later.assert_not_called()
```

- [ ] **Step 2: Run the focused test**

Run: `pytest tests/test_workflow.py -v`

Expected: FAIL because `run_community_workflow` does not exist.

- [ ] **Step 3: Implement sequential typed execution and metrics**

```python
def run_community_workflow(request: RunRequest, stages: list[StageFn]) -> RunResult:
    results = []
    for stage in stages:
        result = stage(request)
        results.append(result)
        if result.status is StageStatus.FAILED:
            return RunResult(status=StageStatus.FAILED, stages=results)
    return RunResult(status=StageStatus.SUCCEEDED, stages=results)
```

`run_benchmark.py` must emit `case_id`, `status`, `latency_ms`, `input_tokens`, `output_tokens`, and `estimated_cost_usd`; it must not write source text or secrets.

- [ ] **Step 4: Run the test and a local benchmark with fake stages**

Run: `pytest tests/test_workflow.py -v`

Expected: PASS and one non-sensitive JSONL record per case.

- [ ] **Step 5: Commit**

```bash
git add src/community_ops/workflow.py evaluations tests/test_workflow.py
git commit -m "feat: add measurable agent workflow"
```

### Task 6: AWS SAM workflow and stage adapters

**Files:**
- Create: `infra/template.yaml`, `src/handlers/stages.py`, `tests/test_stage_handlers.py`

**Interfaces:**
- Consumes: serializable `RunRequest` and stage functions from Task 5.
- Produces: Lambda handlers named `screening_handler`, `matching_handler`, `faq_handler`, `reflection_handler`, and a Standard state machine that catches stage errors before result delivery.

- [ ] **Step 1: Write failing adapter and template tests**

```python
def test_screening_handler_returns_serializable_stage_result():
    response = screening_handler(sample_event(), None)
    assert response["status"] == "succeeded"
```

- [ ] **Step 2: Run the focused test**

Run: `pytest tests/test_stage_handlers.py -v`

Expected: FAIL because the handler does not exist.

- [ ] **Step 3: Implement thin adapters and the SAM template**

```python
def screening_handler(event: dict, _context: object) -> dict:
    return screen_application(RunRequest.model_validate(event["request"]), event["labels"]).model_dump(mode="json")
```

`infra/template.yaml` must define `dev` parameters, seven-day log retention, a Standard Step Functions state machine, explicit `Catch` paths to the result handler, and only the least permissions needed to invoke the next Lambda and read the OpenAI secret.

- [ ] **Step 4: Validate template and handler tests**

Run: `pytest tests/test_stage_handlers.py -v && sam validate --template-file infra/template.yaml`

Expected: PASS with no deployment.

- [ ] **Step 5: Commit**

```bash
git add infra/template.yaml src/handlers/stages.py tests/test_stage_handlers.py
git commit -m "feat: add serverless agent workflow"
```

### Task 7: Discord ingress and result delivery

**Files:**
- Create: `src/handlers/discord_ingress.py`, `src/handlers/discord_result.py`, `tests/test_discord_ingress.py`, `tests/test_discord_result.py`
- Modify: `infra/template.yaml`

**Interfaces:**
- Consumes: Discord request headers and body plus `DISCORD_PUBLIC_KEY`, `DISCORD_APPLICATION_ID`, and interaction token.
- Produces: a deferred response `{\"type\": 5}` and a Step Functions execution; result delivery posts only safe text with `allowed_mentions: {\"parse\": []}`.

- [ ] **Step 1: Write failing ingress and result tests**

```python
def test_invalid_signature_does_not_start_workflow():
    starter = Mock()
    response = lambda_handler(event_with_bad_signature(), None, starter=starter)
    assert response["statusCode"] == 401
    starter.assert_not_called()

def test_valid_command_defers_before_starting_workflow():
    response = lambda_handler(valid_command_event(), None, starter=Mock())
    assert json.loads(response["body"])["type"] == 5
```

- [ ] **Step 2: Run the focused tests**

Run: `pytest tests/test_discord_ingress.py tests/test_discord_result.py -v`

Expected: FAIL because handlers do not exist.

- [ ] **Step 3: Implement signature-first ingress and safe follow-up**

```python
if not verify_key.verify(signature, timestamp.encode() + body.encode()):
    return {"statusCode": 401, "body": "unauthorized"}
start_execution(serialized_request)
return {"statusCode": 200, "body": json.dumps({"type": 5})}
```

The result handler must post one concise success or failure message, filter all mentions, and never include a raw exception, request body, or API response in Discord.

- [ ] **Step 4: Run focused tests and validate SAM**

Run: `pytest tests/test_discord_ingress.py tests/test_discord_result.py -v && sam validate --template-file infra/template.yaml`

Expected: PASS; invalid signatures have no side effect.

- [ ] **Step 5: Commit**

```bash
git add src/handlers/discord_ingress.py src/handlers/discord_result.py tests/test_discord_ingress.py tests/test_discord_result.py infra/template.yaml
git commit -m "feat: add Discord interaction handlers"
```

### Task 8: CI, cost alerts, and dev deployment runbook

**Files:**
- Create: `.github/workflows/test.yml`, `docs/deploy-dev.md`, `docs/benchmark.md`
- Modify: `README.md`, `infra/template.yaml`

**Interfaces:**
- Consumes: test suite, SAM template, benchmark JSONL records, and `dev` stack parameters.
- Produces: pull-request test checks, documented owner-only setup steps, and AWS budget alarm resources at USD 5, USD 8, and USD 10.

- [ ] **Step 1: Write the documentation acceptance checks**

```bash
rg -q 'sam deploy' docs/deploy-dev.md
rg -q 'estimated_cost_usd' docs/benchmark.md
rg -q 'anonymized' README.md
```

- [ ] **Step 2: Run the checks and CI-equivalent tests**

Run: `rg -q 'sam deploy' docs/deploy-dev.md`

Expected: FAIL because the runbook does not exist.

- [ ] **Step 3: Add the smallest CI and runbook**

The workflow runs `pytest` and `sam validate` on pull requests. The runbook must list: create Discord application, set the interaction endpoint, create the OpenAI secret, deploy `dev`, register a test slash command, run one synthetic command, inspect the benchmark record, and delete no resources. It must label IAM, secret creation, and deployment as account-owner actions.

- [ ] **Step 4: Run all local checks**

Run: `pytest -v && sam validate --template-file infra/template.yaml && rg -q 'estimated_cost_usd' docs/benchmark.md`

Expected: PASS before any cloud change.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/test.yml docs/deploy-dev.md docs/benchmark.md README.md infra/template.yaml
git commit -m "docs: add dev deployment and cost controls"
```

## Self-Review

Spec coverage: Tasks 1-5 cover typed modules, deterministic decisions, RAG, reflection, evaluation, and failure behavior. Tasks 6-7 cover AWS, Step Functions, Discord timing, and secret boundaries. Task 8 covers contributor checks, cost monitoring, and owner-only deployment. Personal forks, reviews, and `main` release rules are documented in the spec and README/runbook task.

Placeholder scan: no deferred tasks, generic test instructions, or undefined interfaces remain. `RunRequest`, `StageResult`, `RunResult`, and all named functions are introduced before later tasks consume them.

Type consistency: every domain stage returns `StageResult`; the workflow returns `RunResult`; Lambda adapters serialize models with `model_dump(mode="json")`.

Review focus coverage: malformed signatures are tested in Task 7; invalid labels in Task 2; uncited FAQ output in Task 3; reflection limit in Task 4; and early workflow termination in Task 5. Task 7 then translates the typed workflow failure to a safe Discord response.
