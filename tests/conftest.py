from io import BytesIO

import pytest

from handlers.ask_payloads import AskPayloadStore


class MemoryS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, *, Bucket, Key, Body, ContentType, IfNoneMatch):
        assert ContentType == "application/json"
        assert IfNoneMatch == "*"
        if (Bucket, Key) in self.objects:
            error = RuntimeError("Object already exists")
            error.response = {"ResponseMetadata": {"HTTPStatusCode": 412}}
            raise error
        self.objects[Bucket, Key] = Body

    def get_object(self, *, Bucket, Key):
        return {"Body": BytesIO(self.objects[Bucket, Key])}

    def delete_objects(self, *, Bucket, Delete):
        for obj in Delete["Objects"]:
            self.objects.pop((Bucket, obj["Key"]), None)
        return {}


@pytest.fixture
def payload_store():
    return AskPayloadStore(MemoryS3(), "private-dev")
