from unittest.mock import Mock

from community_ops.models import StageStatus
from community_ops.reflection import reflect_once


def test_reflection_calls_revise_once_when_review_requests_change():
    revise = Mock(return_value="revised")

    result = reflect_once("draft", lambda _: {"accept": False}, revise)

    assert result.status is StageStatus.SUCCEEDED
    assert result.data == {"text": "revised", "revised": True}
    revise.assert_called_once()


def test_reflection_keeps_accepted_draft_without_revision():
    revise = Mock()

    result = reflect_once("draft", lambda _: {"accept": True}, revise)

    assert result.data == {"text": "draft", "revised": False}
    revise.assert_not_called()


def test_reflection_fails_for_invalid_review_payload():
    revise = Mock()

    result = reflect_once("draft", lambda _: {"accept": "yes"}, revise)

    assert result.status is StageStatus.FAILED
    assert result.error == "invalid review"
    revise.assert_not_called()
