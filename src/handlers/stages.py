from typing import Any

from community_ops.matching import rank_matches
from community_ops.models import RunRequest
from community_ops.rag import IndexRecord, answer_faq
from community_ops.reflection import reflect_once
from community_ops.screening import screen_application


def request(event: dict[str, Any]) -> RunRequest:
    return RunRequest.model_validate(event["request"])


def screening_handler(event: dict[str, Any], _context: object) -> dict[str, Any]:
    return screen_application(request(event), event["labels"]).model_dump(mode="json")


def matching_handler(event: dict[str, Any], _context: object) -> dict[str, Any]:
    request(event)
    return rank_matches(event["candidates"], event["constraints"]).model_dump(mode="json")


def faq_handler(event: dict[str, Any], _context: object) -> dict[str, Any]:
    request(event)
    index = [IndexRecord.model_validate(item) for item in event["index"]]
    return answer_faq(
        event["question"], index, lambda _: event["query_embedding"], lambda *_: event["answer"]
    ).model_dump(mode="json")


def reflection_handler(event: dict[str, Any], _context: object) -> dict[str, Any]:
    request(event)
    return reflect_once(
        event["draft"], lambda _: event["review"], lambda *_: event["revision"]
    ).model_dump(mode="json")
