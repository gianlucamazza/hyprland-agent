# Contributing

## Setup

```bash
git clone https://github.com/gianlucamazza/hyprland-agent
cd hyprland-agent
uv sync
uv run pytest -m "not slow"   # fast suite, no embedder download
uv run pytest                  # full suite (downloads ~1.3 GB multilingual-e5-large on first run)
```

Runtime prerequisites: `wtype`, `ydotool`, `grim`, `wl-clipboard`, `fuzzel` (optional), `mako` (optional).

## Pre-commit hooks

```bash
pip install pre-commit
pre-commit install
```

The hooks run `ruff` (lint + format), YAML/TOML validation, and large-file checks on every commit.
To run them manually: `pre-commit run --all-files`.

## Branch naming

```
feat/<short-description>
fix/<short-description>
docs/<short-description>
refactor/<short-description>
```

## Commit style

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(brain): add groq provider
fix(allowlist): handle empty YAML gracefully
refactor(cli): split monolithic cli.py into package
docs(readme): add quickstart section
```

Scope is the module area: `brain`, `daemon`, `cli`, `tools`, `safety`, `learning`, `memory`, `tui`, `integrations`, `ipc`.

## Tests

- Unit tests live under `tests/`. Mirror the `src/agent/` structure.
- Mark tests that require the real bge-m3 embedder with `@pytest.mark.slow`.
- Stub the embedder with `[[0.1] * 1024]` for unit tests.
- The CI job runs `pytest -m "not slow"` — all non-slow tests must pass without a desktop/Hyprland environment.

## Adding a provider

See `src/agent/brain/openai_brain.py` — add an entry to the `PROVIDERS` registry. No new class needed.

## Adding an integration

Implement `IntegrationBase` (see `src/agent/integrations/__init__.py`), declare a `CapabilitySpec`, and register it via the `hyprland_agent.integrations` entry-point group in `pyproject.toml`.

## Allowlist / rules proposals

To propose a new default allowlist entry or watch rule, open an issue with the label `allowlist` or `rules` and include the exact YAML snippet and the rationale.

## Pull requests

- Keep PRs focused: one logical change per PR.
- Reference any related issue in the PR description.
- Ensure `uv run ruff check .` and `uv run ruff format --check .` pass locally.
- Update `CHANGELOG.md` under `[Unreleased]` before submitting.
