import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile

import yaml

from community_ops.faq_search import EXCLUSIONS, lexical_encoder, lexical_vector, search
from community_ops.rag import DEFAULT_INDEX, content_sha256, parse_index

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/faq/source.md"
REGISTRY = ROOT / "assets/faq/sources.json"
EXPECTED_IDS = {f"aal-faq-{number:03}" for number in range(1, 9)}
OPENAI_MODEL = "text-embedding-3-small"


def unique_by_id(entries: list[dict]) -> dict[str, dict]:
    result = {entry["id"]: entry for entry in entries}
    if len(result) != len(entries):
        raise ValueError("Duplicate registry ID")
    return result


def read_records(source_path: Path, registry_path: Path) -> tuple[list[dict], dict]:
    source_bytes = source_path.read_bytes()
    registry_bytes = registry_path.read_bytes()
    registry = json.loads(registry_bytes)
    corpus_hash = hashlib.sha256(source_bytes).hexdigest()
    if corpus_hash != registry["corpus_sha256"]:
        raise ValueError("Corpus bytes disagree with registry corpus_sha256")
    source = source_bytes.decode("utf-8")
    if not source.startswith("---\n"):
        raise ValueError("Missing FAQ frontmatter")
    header, body = source[4:].split("\n---\n", 1)
    frontmatter = yaml.safe_load(header)
    if (registry["schema_version"] != 1 or registry["runtime_enabled"] is not False
            or frontmatter.get("runtime_enabled") is not False
            or registry["status"] != "source-verified-draft" or frontmatter.get("status") != registry["status"]
            or registry["corpus_path"] != "assets/faq/source.md"
            or registry["planned_index_path"] != "src/assets/faq/index.json"):
        raise ValueError("Unexpected corpus policy, path or version")
    sources = unique_by_id(registry["sources"])
    items = unique_by_id(registry["faq_items"])
    if set(items) != EXPECTED_IDS or {item["source_id"] for item in items.values()} != set(sources):
        raise ValueError("Expected eight registered study FAQs and their cited sources")
    for entry in sources.values():
        pinned = f"https://github.com/{entry['repository']}/blob/{entry['commit']}/{entry['path']}"
        if (not re.fullmatch(r"[0-9a-f]{40}", entry["commit"]) or entry["url"] != pinned
                or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
            raise ValueError("Invalid pinned source URL, commit or SHA256")
    records = []
    for block in re.split(r"(?m)^## ", body)[1:]:
        match = re.fullmatch(
            r"(aal-faq-[0-9]{3})\n+질문: ([^\n]+)\n+답변: (.+?)\n+출처: \[[^\]\n]+\]\(([^)\n]+)\)",
            block.strip(), flags=re.DOTALL,
        )
        if not match:
            raise ValueError("FAQ section must contain an ID, question, answer and source link")
        item_id, question, answer, url = match.groups()
        if item_id not in items:
            raise ValueError(f"Unregistered FAQ ID: {item_id}")
        item = items[item_id]
        origin = sources[item["source_id"]]
        first, last = item["lines"]
        if type(first) is not int or type(last) is not int or not (1 <= first <= last):
            raise ValueError(f"Invalid source line range: {item_id}")
        if url != f"{origin['url']}#L{first}-L{last}":
            raise ValueError(f"FAQ citation differs from registry: {item_id}")
        records.append({"id": item_id, "question": question, "text": answer,
                        "source_id": origin["id"], "source_commit": origin["commit"],
                        "source_sha256": origin["sha256"], "source_url": url,
                        "content_sha256": content_sha256(question, answer)})
    if set(unique_by_id(records)) != EXPECTED_IDS:
        raise ValueError("Corpus must contain all eight registered FAQ IDs")
    if set(registry["excluded_topics"]) != set(EXCLUSIONS):
        raise ValueError("Unsupported or missing excluded topic")
    metadata = {"schema_version": 1, "status": registry["status"], "runtime_enabled": False,
                "corpus_sha256": corpus_hash, "registry_sha256": hashlib.sha256(registry_bytes).hexdigest(),
                "excluded_topics": registry["excluded_topics"]}
    return records, metadata


def compile_index(source_path: Path, registry_path: Path, encoder_name: str) -> dict:
    records, metadata = read_records(source_path, registry_path)
    documents = [f"{record['question']}\n{record['text']}" for record in records]
    if encoder_name == "lexical":
        encoder = lexical_encoder(documents)
        vectors = [lexical_vector(text, encoder) for text in documents]
    elif encoder_name == "openai":
        from openai import OpenAI

        response = OpenAI().embeddings.create(model=OPENAI_MODEL, input=documents)
        ordered = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in ordered] != list(range(len(documents))):
            raise ValueError("Incomplete embedding response")
        vectors = [item.embedding for item in ordered]
        encoder = {"name": OPENAI_MODEL, "provider": "openai"}
    else:
        raise ValueError(f"Unknown encoder: {encoder_name}")
    for record, vector in zip(records, vectors, strict=True):
        record["embedding"] = vector
    result = {**metadata, "encoder": encoder, "records": records}
    parse_index(result, allow_draft=True)
    return result


def build(output: Path, encoder: str, check: bool, source: Path = SOURCE, registry: Path = REGISTRY) -> None:
    target = output.resolve()
    if target in (source.resolve(), registry.resolve()) or target.suffix != ".json":
        raise ValueError("Output must be a separate JSON index")
    if encoder == "openai" and (check or target == DEFAULT_INDEX.resolve()):
        raise ValueError("Use a separate output for an explicit OpenAI build; check is offline only")
    payload = compile_index(source, registry, encoder)
    data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if check:
        if not target.is_file() or target.read_bytes() != data:
            raise ValueError("Study FAQ index is stale or missing; rebuild with --encoder lexical")
        if target.stat().st_mode & 0o444 != 0o444:
            raise ValueError("Study FAQ index must be readable by the Lambda runtime user")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temp:
        temporary = Path(temp.name)
    try:
        temporary.write_bytes(data)
        temporary.chmod(0o644)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or search the local study FAQ index")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("build")
    generate.add_argument("--encoder", choices=("lexical", "openai"), default="lexical")
    generate.add_argument("--output", type=Path, default=DEFAULT_INDEX)
    generate.add_argument("--check", action="store_true", help="Check deterministic lexical output without writing")
    lookup = commands.add_parser("search")
    lookup.add_argument("question")
    lookup.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    lookup.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    try:
        if args.command == "build":
            build(args.output, args.encoder, args.check)
            print(f"{args.encoder} study FAQ index {'verified' if args.check else 'created'}: {args.output}")
        else:
            print(json.dumps(search(args.question, args.index, args.top_k, allow_draft=True), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
