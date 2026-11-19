"""Verify SAM packages locally without invoking AWS, Discord or a model."""

import argparse
import copy
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_hash(directory: Path) -> str:
    """Hash relative names and file contents, excluding interpreter-created bytecode."""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            digest.update(path.relative_to(directory).as_posix().encode() + b"\0")
            digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def runtime_requirements(text: str, python_full_version: str = "3.12.0") -> dict[str, str]:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    environment = default_environment()
    environment.update(
        sys_platform="linux", platform_system="Linux", os_name="posix",
        platform_machine="x86_64", python_version="3.12", python_full_version=python_full_version,
        implementation_name="cpython", platform_python_implementation="CPython",
        implementation_version=python_full_version, extra="",
    )
    expected = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "--hash=")):
            continue
        requirement = Requirement(line.rstrip("\\").strip())
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        pins = list(requirement.specifier)
        if len(pins) != 1 or pins[0].operator != "==" or "*" in pins[0].version:
            raise ValueError(f"Requirement is not exactly pinned: {requirement.name}")
        name = canonicalize_name(requirement.name)
        if name in expected:
            raise ValueError(f"Duplicate runtime requirement: {name}")
        expected[name] = pins[0].version
    if not expected:
        raise ValueError("Runtime requirements are empty")
    return expected


def package_distributions(package: Path) -> dict[str, str]:
    from packaging.utils import canonicalize_name

    actual = {}
    for distribution in metadata.distributions(path=[str(package)]):
        name = canonicalize_name(distribution.metadata["Name"])
        if name in actual:
            raise ValueError(f"Duplicate installed distribution: {name}")
        actual[name] = distribution.version
    return actual


def check_distributions(actual: dict[str, str], expected: dict[str, str]) -> None:
    if actual != expected:
        missing = sorted(expected.keys() - actual.keys())
        extra = sorted(actual.keys() - expected.keys())
        wrong = {name: {"expected": expected[name], "actual": actual[name]}
                 for name in actual.keys() & expected.keys() if actual[name] != expected[name]}
        raise ValueError(f"Dependency mismatch: missing={missing}, extra={extra}, versions={wrong}")


def load_template(path: Path) -> dict:
    import yaml

    class TemplateLoader(yaml.SafeLoader):
        pass

    def intrinsic(loader, tag, node):
        if isinstance(node, yaml.ScalarNode):
            value = loader.construct_scalar(node)
        elif isinstance(node, yaml.SequenceNode):
            value = loader.construct_sequence(node)
        else:
            value = loader.construct_mapping(node)
        if tag == "GetAtt" and isinstance(value, str):
            value = value.split(".", 1)
        return {"Ref" if tag == "Ref" else "Fn::" + tag: value}

    TemplateLoader.add_multi_constructor("!", intrinsic)
    return yaml.load(path.read_text(encoding="utf-8"), Loader=TemplateLoader)


def check_source_files(package: Path, source_dir: Path) -> None:
    expected = {path.relative_to(source_dir): path for path in source_dir.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}
    for relative, path in expected.items():
        target = package / relative
        if not target.is_file() or target.read_bytes() != path.read_bytes():
            raise ValueError(f"Source/package mismatch: {relative}")
    own_roots = {relative.parts[0] for relative in expected if len(relative.parts) > 1}
    for own_root in own_roots:
        for path in (package / own_root).rglob("*.py"):
            if path.relative_to(package) not in expected:
                raise ValueError(f"Unexpected application module: {path.relative_to(package)}")


def normalized_template(template: dict) -> dict:
    normalized = copy.deepcopy(template)
    for resource in normalized["Resources"].values():
        if resource["Type"] == "AWS::Serverless::Function":
            resource["Properties"]["CodeUri"] = "<build-output>"
        if "Metadata" in resource:
            resource["Metadata"].pop("SamResourceId", None)
            if not resource["Metadata"]:
                resource.pop("Metadata")
    return normalized


def function_packages(source: dict, built: dict, build_dir: Path) -> list[tuple[str, Path, str]]:
    if set(source["Resources"]) != set(built["Resources"]):
        raise ValueError("SAM resource set changed during build")
    if normalized_template(source) != normalized_template(built):
        raise ValueError("SAM template changed beyond CodeUri/generated SamResourceId")
    functions = []
    for name, resource in source["Resources"].items():
        candidate = built["Resources"][name]
        if resource["Type"] != candidate["Type"]:
            raise ValueError(f"Resource type changed: {name}")
        if resource["Type"] != "AWS::Serverless::Function":
            continue
        original = resource["Properties"]
        properties = candidate["Properties"]
        for field, default in [("Handler", None), ("Runtime", None), ("Architectures", ["x86_64"])]:
            if original.get(field, default) != properties.get(field, default):
                raise ValueError(f"Function configuration changed: {name}.{field}")
        if properties["Runtime"] != "python3.12" or properties.get("Architectures", ["x86_64"]) != ["x86_64"]:
            raise ValueError(f"Unsupported runtime/architecture: {name}")
        package = (build_dir / properties["CodeUri"]).resolve()
        if not package.is_relative_to(build_dir.resolve()) or not package.is_dir():
            raise ValueError(f"Package is missing or outside build directory: {name}")
        if name == "FaqFunction" and not (package / "assets/faq/index.json").is_file():
            raise ValueError("FaqFunction package is missing its study FAQ index")
        functions.append((name, package, properties["Handler"]))
    if len(functions) != 7:
        raise ValueError(f"Expected 7 function packages, found {len(functions)}")
    if not any(name == "FaqFunction" for name, _, _ in functions):
        raise ValueError("Required FaqFunction package is missing")
    return functions


def probe(package: Path, handler: str, index_hash: str, *, study_draft: bool = False) -> dict:
    """Executed by an isolated interpreter inside the Linux build image."""
    import importlib

    if sys.version_info[:2] != (3, 12) or platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("Probe requires Linux x86_64 Python 3.12")
    sys.path.insert(0, str(package))
    module_name, attribute = handler.rsplit(".", 1)
    module = importlib.import_module(module_name)
    if not Path(module.__file__).resolve().is_relative_to(package.resolve()):
        raise ValueError("Handler was imported outside its package")
    if not callable(getattr(module, attribute)):
        raise ValueError("Handler is not callable")
    # Explicit imports load all native runtime dependencies, not just handler imports.
    for name in ["openai", "pydantic", "pydantic_core", "nacl.bindings", "cffi", "jiter"]:
        importlib.import_module(name)
    from community_ops.rag import DEFAULT_INDEX, load_index

    if sha256(DEFAULT_INDEX) != index_hash:
        raise ValueError("Packaged FAQ content hash differs from expected source")
    if study_draft:
        if DEFAULT_INDEX.stat().st_mode & 0o444 != 0o444:
            raise ValueError("Packaged study FAQ is not readable by the runtime user")
        try:
            load_index()
        except ValueError as exc:
            if str(exc) != "Study FAQ runtime use is disabled":
                raise
        else:
            raise ValueError("Default runtime path accepted a disabled study FAQ")
    records = load_index(allow_draft=study_draft)
    if study_draft and {r.id for r in records} != {f"aal-faq-{n:03}" for n in range(1, 9)}:
        raise ValueError("Expected the eight registered study FAQ records")
    return {"handler": handler, "imported": True, "faq_records": len(records),
            "faq_scope": "study_draft" if study_draft else "synthetic_fixture",
            "default_runtime_rejected": study_draft,
            "faq_sha256": index_hash, "python": platform.python_version(),
            "system": platform.system(), "machine": platform.machine()}


def run_probe(package: Path, handler: str, index_hash: str, image: str, *, study_draft: bool = False) -> dict:
    command = [
        "docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
        "--entrypoint", "python3", "-v", f"{package.resolve()}:/package:ro",
        "-v", f"{Path(__file__).resolve()}:/verification/scripts/verify_package.py:ro", image,
        "-I", "-S", "/verification/scripts/verify_package.py", "--probe", "/package", handler, index_hash,
    ]
    if study_draft:
        command.append("--study-draft")
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"Isolated package probe failed for {handler}:\n{result.stderr[-4000:]}")
    return json.loads(result.stdout)


def image_python_version(image: str) -> str:
    command = [
        "docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
        "--entrypoint", "python3", image, "-I", "-S", "-c",
        "import json, platform; print(json.dumps({'python': platform.python_version(), "
        "'system': platform.system(), 'machine': platform.machine()}))",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=True)
    actual = json.loads(result.stdout)
    if actual["system"] != "Linux" or actual["machine"] != "x86_64" or not actual["python"].startswith("3.12."):
        raise ValueError("Verification image requires Linux x86_64 Python 3.12")
    return actual["python"]


def verify(build_dir: Path, fixture: Path, image: str) -> dict:
    from scripts.export_requirements import exported_requirements

    fixture = fixture.resolve()
    if not fixture.is_relative_to(ROOT.resolve()) or not fixture.is_file():
        raise ValueError("Synthetic index must be an existing file inside the repository")
    if "@sha256:" not in image:
        raise ValueError("Verification image must be pinned by digest")
    study_index = ROOT / "src/assets/faq/index.json"
    if not study_index.is_file():
        raise ValueError("Required study FAQ index is missing from the source")
    requirements = (ROOT / "src/requirements.txt").read_text(encoding="utf-8")
    if requirements != exported_requirements(ROOT):
        raise ValueError("SAM requirements export is stale")
    source = load_template(ROOT / "infra/template.yaml")
    built = load_template(build_dir / "template.yaml")
    functions = function_packages(source, built, build_dir)
    python_full_version = image_python_version(image)
    expected = runtime_requirements(requirements, python_full_version)
    fixture_hash = sha256(fixture)
    results = {}
    original_study_faq_probe = None
    # Synthetic files only enter disposable verification copies, never deployable build output.
    with tempfile.TemporaryDirectory(prefix="aal-package-check-") as temporary:
        for name, package, handler in functions:
            check_distributions(package_distributions(package), expected)
            check_source_files(package, ROOT / "src")
            before = content_hash(package)
            if name == "FaqFunction":
                original_study_faq_probe = run_probe(
                    package, handler, sha256(study_index), image, study_draft=True,
                )
            staged = Path(temporary) / name
            shutil.copytree(package, staged)
            index = staged / "assets/faq/index.json"
            index.parent.mkdir(parents=True, exist_ok=True)
            index.write_bytes(fixture.read_bytes())
            results[name] = {
                "original_content_sha256": before,
                "validation_content_sha256": content_hash(staged),
                "distributions": package_distributions(package),
                "probe": run_probe(staged, handler, fixture_hash, image),
            }
    if original_study_faq_probe is None:
        raise ValueError("Required FaqFunction original study FAQ probe is missing")
    paths = [ROOT / "uv.lock", ROOT / "pyproject.toml", ROOT / "infra/template.yaml"]
    paths += sorted((ROOT / "src").rglob("*.py")) + [ROOT / "src/requirements.txt", fixture]
    paths += sorted((ROOT / "scripts").glob("*.py")) + [ROOT / ".github/workflows/test.yml"]
    paths += sorted((ROOT / "tests").rglob("*.py"))
    paths += [p for p in (ROOT / "assets/faq/source.md", ROOT / "assets/faq/sources.json",
                           ROOT / "src/assets/faq/index.json") if p.is_file()]
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "--",
         "src", "scripts", "tests", "infra", ".github", "pyproject.toml", "uv.lock"],
        cwd=ROOT, text=True,
    ).splitlines()
    tracked_dirty = bool(subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
    ))
    return {
        "schema_version": 2, "synthetic_validation_only": False,
        "original_study_faq_probe": original_study_faq_probe, "deploy_ready": False,
        "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "tracked_source_dirty": tracked_dirty,
        "untracked_source_files": untracked, "source_dirty": tracked_dirty or bool(untracked),
        "source_hashes": {str(p.relative_to(ROOT)): sha256(p) for p in paths},
        "built_template_sha256": sha256(build_dir / "template.yaml"),
        "image": image, "marker_python_full_version": python_full_version,
        "runtime_distribution_count": len(expected),
        "preserved_resources": sorted(source["Resources"]), "functions": results,
        "limitations": ["No AWS invocation or deployment", "Synthetic index staged only in disposable verification copies",
                        "Content hashes are not AWS deployment ZIP CodeSha256", "Study FAQ serving disabled; no live model evaluation"],
    }


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--probe":
        print(json.dumps(probe(Path(sys.argv[2]), sys.argv[3], sys.argv[4],
                               study_draft=sys.argv[5:] == ["--study-draft"])))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / ".aws-sam/build")
    parser.add_argument("--synthetic-index", type=Path, required=True,
                        help="Existing synthetic fixture file inside this repository (symlinks resolved)")
    parser.add_argument("--image", required=True, help="SAM Python 3.12 x86_64 image pinned by digest")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Never leave an earlier success manifest after a failed verification.
    args.output.unlink(missing_ok=True)
    sys.path.insert(0, str(ROOT))
    result = verify(args.build_dir.resolve(), args.synthetic_index.resolve(), args.image)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Verified {len(result['functions'])} packages and recorded FAQ scopes; deploy_ready=false")


if __name__ == "__main__":
    main()
