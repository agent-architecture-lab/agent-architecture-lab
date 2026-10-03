import argparse
import json
from pathlib import Path

from openai import OpenAI

from community_ops.rag import IndexRecord

SOURCE = Path("assets/faq/source.md")
INDEX = Path("assets/faq/index.json")


def chunks(source: str) -> list[tuple[str, str]]:
    return [
        (heading, text.strip())
        for section in source.split("\n## ")[1:]
        for heading, _, text in [section.partition("\n")]
        if heading.startswith("faq-") and text.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", required=True)
    args = parser.parse_args()

    client = OpenAI(api_key=args.api_key)
    records = []
    for source_id, text in chunks(SOURCE.read_text()):
        embedding = client.embeddings.create(model="text-embedding-3-small", input=text).data[0].embedding
        records.append(IndexRecord(id=source_id, text=text, embedding=embedding).model_dump())
    INDEX.write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
