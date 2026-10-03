# Community operations agent

A deterministic Discord community-operations workflow for synthetic and anonymized inputs only.

Run local checks with `uv sync --all-groups`, `uv run pytest -q`, and `sam validate --lint --template-file infra/template.yaml`.

See [the dev deployment runbook](docs/deploy-dev.md) and [benchmark records](docs/benchmark.md). Account owners perform AWS, secret, and Discord setup.
