import json
from pathlib import Path
from screening.backends import MockBackend
from screening.validation import validate_evaluation, quote_accuracy, summarize_evaluation

DATA = Path(__file__).resolve().parents[1] / "data"
study = json.loads((DATA / "study.json").read_text(encoding="utf-8"))
applications = json.loads((DATA / "applications.json").read_text(encoding="utf-8"))


def test_malformed_quote_is_caught():
    ev = MockBackend().generate(applications[0], study)
    issues = validate_evaluation(ev, applications[0], study)
    assert any(x.code == "unmatched_quote" for x in issues)
    assert quote_accuracy(ev, applications[0])["ratio"] < 1


def test_missing_info_does_not_become_zero():
    app = applications[2]
    backend = MockBackend()
    initial = backend.generate(app, study)
    corrected = backend.refine(initial, backend.critique(initial, app, study), app, study)
    summary = summarize_evaluation(corrected, study, [])
    assert summary["score"] is None
    attendance = next(x for x in corrected.criteria if x.criterion_id == "attendance")
    assert attendance.status == "unknown" and attendance.grade is None


def test_mock_refine_fixes_the_quote():
    app = applications[0]
    backend = MockBackend()
    first = backend.generate(app, study)
    revised = backend.refine(first, backend.critique(first, app, study), app, study)
    assert not validate_evaluation(revised, app, study)
