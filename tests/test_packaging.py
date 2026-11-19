import json
from pathlib import Path

import pytest

from community_ops.models import RunRequest
from community_ops.rag import load_index
from handlers.stages import faq_handler
from scripts.verify_package import (
    check_distributions, check_source_files, content_hash, function_packages, load_template,
    package_distributions, probe, runtime_requirements, verify,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/faq-packaging-index.json"


def test_lock_export_selects_linux_python312_runtime_only():
    expected = runtime_requirements((ROOT / "src/requirements.txt").read_text())
    assert len(expected) == 19
    assert expected["pydantic"] == "2.13.5"
    assert expected["pydantic-core"] == "2.46.5"
    assert expected["pycparser"] == "3.0"
    assert "pytest" not in expected and "colorama" not in expected


@pytest.mark.parametrize("actual", [{}, {"demo": "2.0"}, {"demo": "1.0", "extra": "1.0"}])
def test_dependency_gate_rejects_missing_wrong_and_extra(actual):
    with pytest.raises(ValueError, match="Dependency mismatch"):
        check_distributions(actual, {"demo": "1.0"})


def test_dependency_gate_accepts_exact_match():
    check_distributions({"demo": "1.0"}, {"demo": "1.0"})


def test_distribution_reader_detects_duplicate_metadata(tmp_path):
    for version in ["1.0", "2.0"]:
        directory = tmp_path / f"demo-{version}.dist-info"
        directory.mkdir()
        (directory / "METADATA").write_text(f"Name: demo\nVersion: {version}\n")
    with pytest.raises(ValueError, match="Duplicate installed"):
        package_distributions(tmp_path)


@pytest.mark.parametrize("requirement", ["demo>=1", "demo==1.*", ""])
def test_export_reader_rejects_unpinned_or_empty(requirement):
    with pytest.raises(ValueError):
        runtime_requirements(requirement)


def test_faq_loader_reads_synthetic_fixture():
    records = load_index(FIXTURE)
    assert len(records) == 2
    assert all(record.id.startswith("synthetic-packaging-") for record in records)


def test_faq_loader_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_index(tmp_path / "missing.json")


@pytest.mark.parametrize("payload", [
    "not json", "[]", "{}", '[{"id":"x"}]',
    '[{"id":"x","text":"x","embedding":[]}]',
    '[{"id":"x","text":"x","embedding":[0,0]}]',
    '[{"id":"x","text":"x","embedding":[NaN]}]',
    '[{"id":"x","text":"x","embedding":[1]},{"id":"x","text":"y","embedding":[1]}]',
    '[{"id":"x","text":"x","embedding":[1]},{"id":"y","text":"y","embedding":[1,0]}]',
])
def test_faq_loader_rejects_corrupt_records(tmp_path, payload):
    path = tmp_path / "index.json"
    path.write_text(payload)
    with pytest.raises(ValueError):
        load_index(path)


def test_faq_handler_ignores_event_supplied_index():
    model_calls = []
    result = faq_handler(
        {
            "request": RunRequest(
                run_id="test", command="ask", payload={"question": "Synthetic test?"}
            ).model_dump(mode="json"),
            "index": [],
        },
        None,
        answerer=lambda *args: model_calls.append(args) or {"answer": "[faq-001]"},
    )
    assert result["status"] == "failed"
    assert result["error"] == "FAQ source is not approved for runtime use"
    assert model_calls == []


def test_faq_handler_returns_safe_failure_for_missing_packaged_index():
    def missing(_question):
        raise FileNotFoundError("private/path/index.json")

    result = faq_handler(
        {
            "request": RunRequest(
                run_id="test", command="ask", payload={"question": "Synthetic test?"}
            ).model_dump(mode="json"),
        },
        None,
        searcher=missing,
    )
    assert result["status"] == "failed"
    assert "private" not in json.dumps(result)


def test_resource_gate_rejects_removed_dispatch():
    source = load_template(ROOT / "infra/template.yaml")
    built = load_template(ROOT / "infra/template.yaml")
    del built["Resources"]["DiscordDispatchFunction"]
    with pytest.raises(ValueError, match="resource set changed"):
        function_packages(source, built, ROOT)


def test_resource_gate_rejects_iam_change():
    source = load_template(ROOT / "infra/template.yaml")
    built = load_template(ROOT / "infra/template.yaml")
    built["Resources"]["DiscordDispatchFunction"]["Properties"]["Policies"] = []
    with pytest.raises(ValueError, match="template changed"):
        function_packages(source, built, ROOT)


@pytest.mark.parametrize("mutation", ["missing", "modified", "extra"])
def test_source_gate_rejects_stale_or_extra_application_code(tmp_path, mutation):
    source = tmp_path / "src"
    package = tmp_path / "package"
    for base in [source, package]:
        (base / "handlers").mkdir(parents=True)
        (base / "handlers/main.py").write_text("value = 1\n")
    if mutation == "missing":
        (package / "handlers/main.py").unlink()
    elif mutation == "modified":
        (package / "handlers/main.py").write_text("value = 2\n")
    else:
        (package / "handlers/unexpected.py").write_text("value = 3\n")
    with pytest.raises(ValueError):
        check_source_files(package, source)


def test_content_hash_detects_modified_file_and_ignores_bytecode(tmp_path):
    (tmp_path / "module.py").write_text("value = 1\n")
    before = content_hash(tmp_path)
    (tmp_path / "module.pyc").write_bytes(b"temporary")
    assert content_hash(tmp_path) == before
    (tmp_path / "module.py").write_text("value = 2\n")
    assert content_hash(tmp_path) != before


def test_probe_fails_on_wrong_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.verify_package.platform.system", lambda: "Darwin")
    with pytest.raises(ValueError, match="Linux x86_64 Python 3.12"):
        probe(tmp_path, "missing.handler", "unused")


def test_probe_fails_for_missing_handler_module(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.verify_package.platform.system", lambda: "Linux")
    monkeypatch.setattr("scripts.verify_package.platform.machine", lambda: "x86_64")
    monkeypatch.setattr("scripts.verify_package.sys.version_info", (3, 12))
    with pytest.raises(ModuleNotFoundError):
        probe(tmp_path, "missing_test_only_handler.handler", "unused")


def test_external_fixture_rejected_before_export_or_docker(monkeypatch, tmp_path):
    fixture = tmp_path / "external.json"
    fixture.write_text("[]")
    def unexpected_export(*_):
        pytest.fail("External fixture must be rejected before exporting")
    monkeypatch.setattr("scripts.export_requirements.exported_requirements", unexpected_export)
    with pytest.raises(ValueError, match="inside the repository"):
        verify(tmp_path, fixture, "unused")


def test_fixture_symlink_outside_repository_is_rejected(monkeypatch, tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    external = tmp_path / "external.json"
    external.write_text("[]")
    link = root / "fixture.json"
    link.symlink_to(external)
    monkeypatch.setattr("scripts.verify_package.ROOT", root)
    with pytest.raises(ValueError, match="inside the repository"):
        verify(root, link, "unused")


def test_package_verifier_requires_original_study_index(monkeypatch, tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_bytes(FIXTURE.read_bytes())
    monkeypatch.setattr("scripts.verify_package.ROOT", tmp_path)
    with pytest.raises(ValueError, match="Required study FAQ index is missing"):
        verify(tmp_path, fixture, "test@sha256:test")


def test_package_gate_rejects_missing_study_faq_in_built_function(tmp_path):
    source = load_template(ROOT / "infra/template.yaml")
    built = load_template(ROOT / "infra/template.yaml")
    for name, resource in built["Resources"].items():
        if resource["Type"] == "AWS::Serverless::Function":
            (tmp_path / name).mkdir()
            resource["Properties"]["CodeUri"] = name
    with pytest.raises(ValueError, match="FaqFunction package is missing"):
        function_packages(source, built, tmp_path)


def test_runtime_requirement_marker_uses_actual_image_patch_version():
    requirements = "base==1.0\npatch-only==1.0 ; python_full_version >= '3.12.14'\n"
    assert runtime_requirements(requirements, "3.12.13") == {"base": "1.0"}
    assert runtime_requirements(requirements, "3.12.14") == {"base": "1.0", "patch-only": "1.0"}
