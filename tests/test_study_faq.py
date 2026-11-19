import hashlib
import json
from types import SimpleNamespace

import pytest

from community_ops.faq_search import search
from community_ops.models import RunRequest
from community_ops.rag import DEFAULT_INDEX, content_sha256, load_index, parse_index
from handlers.stages import faq_handler
from scripts.build_faq_index import OPENAI_MODEL, REGISTRY, SOURCE, build


def test_offline_build_reproduces_packaged_bytes_and_citations(tmp_path):
    output = tmp_path / "index.json"
    build(output, "lexical", False)
    build(output, "lexical", True)
    assert output.read_bytes() == DEFAULT_INDEX.read_bytes()
    assert output.stat().st_mode & 0o777 == 0o644
    payload = json.loads(output.read_bytes())
    registry = json.loads(REGISTRY.read_bytes())
    assert payload["corpus_sha256"] == hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert payload["registry_sha256"] == hashlib.sha256(REGISTRY.read_bytes()).hexdigest()
    assert payload["runtime_enabled"] is False
    assert len(payload["records"]) == len(registry["faq_items"]) == 8
    records = load_index(output, allow_draft=True)
    for record, item in zip(records, registry["faq_items"], strict=True):
        origin = next(row for row in registry["sources"] if row["id"] == item["source_id"])
        assert record.id == item["id"]
        assert record.source_sha256 == origin["sha256"]
        assert record.source_commit == origin["commit"]
        assert record.source_url == f"{origin['url']}#L{item['lines'][0]}-L{item['lines'][1]}"
        assert record.content_sha256 == content_sha256(record.question, record.text)


def test_default_runtime_rejects_study_draft():
    with pytest.raises(ValueError, match="runtime use is disabled"):
        load_index(DEFAULT_INDEX)
    model_calls = []
    response = faq_handler(
        {
            "request": RunRequest(
                run_id="test", command="ask", payload={"question": "Where are tasks managed?"}
            ).model_dump(),
        },
        None,
        answerer=lambda *args: model_calls.append(args) or {"answer": "[aal-faq-004]"},
    )
    assert response["status"] == "failed"
    assert response["error"] == "FAQ source is not approved for runtime use"
    assert model_calls == []



def test_explicitly_enabled_sourced_index_loads_for_runtime(tmp_path):
    payload = json.loads(DEFAULT_INDEX.read_bytes())
    payload["runtime_enabled"] = True
    path = tmp_path / "approved-index.json"
    path.write_text(json.dumps(payload))

    records = load_index(path)

    assert len(records) == 8
    assert records[0].id == "aal-faq-001"


def test_ask_returns_cited_answer_and_safe_metadata(caplog):
    source = {
        "id": "aal-faq-004",
        "text": "Use GitHub Issues to manage tasks.",
        "source_url": "https://github.com/example/repo/blob/0123456789012345678901234567890123456789/README.md",
    }
    response = faq_handler(
        {
            "request": RunRequest(
                run_id="run-ask-1", command="ask", payload={"question": "Where are tasks managed?"}
            ).model_dump(),
        },
        None,
        searcher=lambda _: {"status": "matches", "hits": [source]},
        answerer=lambda *_: {
            "answer": "Manage tasks in GitHub Issues [aal-faq-004].",
            "model": "test-model",
            "request_id": "req-safe-1",
            "input_tokens": 30,
            "output_tokens": 12,
            "latency_ms": 24,
        },
    )

    assert response["status"] == "succeeded"
    assert response["data"]["source_ids"] == ["aal-faq-004"]
    assert response["data"]["sources"] == [{"id": "aal-faq-004", "url": source["source_url"]}]
    assert response["data"]["input_tokens"] == 30
    assert "Where are tasks managed?" not in caplog.text


def test_ask_does_not_call_model_for_low_evidence():
    model_calls = []
    result = faq_handler(
        {
            "request": RunRequest(
                run_id="run-ask-2", command="ask", payload={"question": "unknown"}
            ).model_dump(),
        },
        None,
        searcher=lambda _: {"status": "low_evidence", "hits": [{"id": "aal-faq-004"}]},
        answerer=lambda *args: model_calls.append(args) or {"answer": "[aal-faq-004]"},
    )

    assert result["status"] == "failed"
    assert result["error"] == "No supported FAQ answer was found"
    assert model_calls == []


def test_openai_faq_adapter_uses_injected_secret_and_records_usage(monkeypatch):
    from handlers.stages import _answer_with_openai

    monkeypatch.setenv("OPENAI_SECRET_ARN", "secret-arn")
    monkeypatch.setenv("FAQ_MODEL", "test-model")
    calls = []

    class Completions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Answer [faq-1]."))],
                usage=SimpleNamespace(prompt_tokens=15, completion_tokens=7),
                model="test-model",
                _request_id="req-1",
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    result = _answer_with_openai(
        "Where?", {"id": "faq-1", "text": "Some answer."},
        secret_loader=lambda arn: "test-secret" if arn == "secret-arn" else "",
        client_factory=lambda **kwargs: client,
    )

    assert calls[0]["model"] == "test-model"
    assert calls[0]["max_tokens"] == 350
    assert result["answer"] == "Answer [faq-1]."
    assert result["request_id"] == "req-1"
    assert result["input_tokens"] == 15
    assert result["output_tokens"] == 7


@pytest.mark.parametrize("variant", ["flattened", "reserved_id", "provenance"])
def test_study_records_cannot_enter_through_legacy_file_or_event(variant):
    item = json.loads(DEFAULT_INDEX.read_bytes())["records"][0]
    if variant == "reserved_id":
        item = {key: item[key] for key in ("id", "text", "embedding")}
    elif variant == "provenance":
        item = {**item, "id": "faq-001"}
    with pytest.raises(ValueError):
        parse_index([item], allow_draft=True)
    result = faq_handler({
        "request": RunRequest(
            run_id="test", command="ask", payload={"question": "sample"}
        ).model_dump(),
        "index": [item],
    }, None)
    assert result["status"] == "failed"
    assert result["error"] == "FAQ source is not approved for runtime use"


def test_empty_legacy_event_remains_a_no_sources_result():
    result = faq_handler(
        {
            "request": RunRequest(
                run_id="test", command="ask", payload={"question": "sample"}
            ).model_dump(),
        },
        None,
        searcher=lambda _: {"status": "no_match", "hits": []},
    )
    assert result["status"] == "failed"
    assert result["error"] == "No supported FAQ answer was found"


@pytest.mark.parametrize("mutation", ["corpus_hash", "missing", "duplicate", "source_url", "upstream_hash", "unexpected_heading"])
def test_invalid_input_preserves_previous_artifact(tmp_path, mutation):
    source = tmp_path / "source.md"
    registry_file = tmp_path / "sources.json"
    output = tmp_path / "index.json"
    corpus = SOURCE.read_text()
    registry = json.loads(REGISTRY.read_text())
    if mutation == "corpus_hash":
        registry["corpus_sha256"] = "0" * 64
    elif mutation == "missing":
        corpus = corpus.split("## aal-faq-008")[0]
    elif mutation == "duplicate":
        corpus = corpus.replace("## aal-faq-008", "## aal-faq-001")
    elif mutation == "unexpected_heading":
        corpus += "\n## extra\n\nIgnored would be unsafe\n"
    elif mutation == "source_url":
        registry["faq_items"][0]["lines"] = [1, 22]
    elif mutation == "upstream_hash":
        registry["sources"][0]["sha256"] = "invalid"
    source.write_text(corpus)
    if mutation != "corpus_hash":
        registry["corpus_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    registry_file.write_text(json.dumps(registry))
    output.write_bytes(b"previous")
    with pytest.raises(ValueError):
        build(output, "lexical", False, source, registry_file)
    assert output.read_bytes() == b"previous"


def test_stale_check_preserves_modified_file(tmp_path):
    output = tmp_path / "index.json"
    output.write_bytes(b"stale")
    with pytest.raises(ValueError, match="stale"):
        build(output, "lexical", True)
    assert output.read_bytes() == b"stale"


def test_corrupt_record_hash_rejected(tmp_path):
    payload = json.loads(DEFAULT_INDEX.read_bytes())
    payload["records"][0]["text"] += "unexpected"
    path = tmp_path / "index.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="content hash"):
        load_index(path, allow_draft=True)


def test_search_returns_cited_record_and_query_coverage():
    result = search("과제와 진행 상황은 어디에서 관리하는가?", top_k=1, allow_draft=True)
    assert result["use"] == "retrieval_candidates_only" and result["status"] == "matches"
    assert result["hits"][0]["id"] == "aal-faq-004"
    assert "#L254-L258" in result["hits"][0]["source_url"]
    assert len(result["hits"][0]["matched_query_words"]) > 1


def test_runtime_search_refuses_current_disabled_index_by_default():
    with pytest.raises(ValueError, match="runtime use is disabled"):
        search("과제와 진행 상황은 어디에서 관리하는가?")


@pytest.mark.parametrize(("question", "status"), [
    ("zzqxvk", "no_match"), ("zzqxvk 과제", "low_evidence"),
    ("현재 봇이 온라인인가요?", "excluded"), ("이번 주 모임은 몇 시인가요?", "excluded"),
])
def test_search_marks_out_of_scope_or_weak_evidence(question, status):
    result = search(question, allow_draft=True)
    assert result["status"] == status
    if status != "low_evidence":
        assert result["hits"] == []


@pytest.mark.parametrize("mutation", ["empty", "duplicate", "unknown"])
def test_search_rejects_modified_exclusion_policy(tmp_path, mutation):
    payload = json.loads(DEFAULT_INDEX.read_bytes())
    topics = payload["excluded_topics"]
    payload["excluded_topics"] = {"empty": [], "duplicate": topics + [topics[0]],
                                 "unknown": topics[:-1] + ["unknown"]}[mutation]
    path = tmp_path / "index.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="exclusion policy"):
        search("현재 봇이 온라인인가요?", path, allow_draft=True)


def test_openai_mode_is_explicit_and_preserves_model_contract(monkeypatch, tmp_path):
    def create(*, model, input):
        assert model == OPENAI_MODEL and len(input) == 8
        return SimpleNamespace(data=[SimpleNamespace(index=i, embedding=[1.0, float(i)]) for i in reversed(range(8))])
    monkeypatch.setattr("openai.OpenAI", lambda: SimpleNamespace(embeddings=SimpleNamespace(create=create)))
    output = tmp_path / "openai.json"
    build(output, "openai", False)
    payload = json.loads(output.read_bytes())
    assert payload["encoder"] == {"name": OPENAI_MODEL, "provider": "openai"}
    assert payload["records"][3]["embedding"] == [1, 3]
    with pytest.raises(ValueError, match="lexical"):
        search("과제 관리", output, allow_draft=True)
    with pytest.raises(ValueError, match="separate output"):
        build(DEFAULT_INDEX, "openai", False)
