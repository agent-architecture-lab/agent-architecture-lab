"""Short-lived private objects for the Discord FAQ workflow."""

import json
import os
import re
import time
from typing import Any, Literal

PayloadKind = Literal["question", "token", "answer"]
MAX_PAYLOAD_BYTES = 32_768
PAYLOAD_TTL_SECONDS = 600


class PayloadStoreError(RuntimeError):
    pass


class AskPayloadStore:
    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def put(self, kind: PayloadKind, reference: str, value: Any) -> None:
        key = _key(kind, reference)
        body = json.dumps({"expires_at": int(time.time()) + PAYLOAD_TTL_SECONDS, "value": value}).encode()
        if len(body) > MAX_PAYLOAD_BYTES:
            raise PayloadStoreError("Temporary payload is too large")
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=key, Body=body, ContentType="application/json",
                IfNoneMatch="*",
            )
        except Exception as error:
            # A duplicate delivery must not overwrite the original payload or extend its expiry.
            response = getattr(error, "response", {})
            if response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 412:
                raise PayloadStoreError("Temporary payload write failed") from None

    def get(self, kind: PayloadKind, reference: str) -> Any:
        key = _key(kind, reference)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            with response["Body"] as body:
                data = body.read(MAX_PAYLOAD_BYTES + 1)
            if len(data) > MAX_PAYLOAD_BYTES:
                raise ValueError("Oversized temporary payload")
            payload = json.loads(data)
            expires_at = payload["expires_at"]
            value = payload["value"]
        except Exception:
            raise PayloadStoreError("Temporary payload read failed") from None
        if type(expires_at) is not int or expires_at <= time.time():
            raise PayloadStoreError("Temporary payload expired")
        return value

    def cleanup(self, reference: str) -> None:
        keys = [{"Key": _key(kind, reference)} for kind in ("token", "question", "answer")]
        try:
            response = self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys, "Quiet": True})
        except Exception:
            raise PayloadStoreError("Temporary payload cleanup failed") from None
        if response.get("Errors"):
            raise PayloadStoreError("Temporary payload cleanup was incomplete")


def ask_payload_store() -> AskPayloadStore:
    import boto3
    from botocore.config import Config

    config = Config(connect_timeout=1, read_timeout=2, retries={"total_max_attempts": 2})
    return AskPayloadStore(boto3.client("s3", config=config), os.environ["ASK_PAYLOAD_BUCKET"])


def _key(kind: PayloadKind, reference: str) -> str:
    if not isinstance(reference, str) or not re.fullmatch(r"[0-9a-f]{64}", reference):
        raise PayloadStoreError("Invalid temporary payload reference")
    return f"{kind}/{reference}"
