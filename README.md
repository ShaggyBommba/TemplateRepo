# Layered Service Template

This repository is a Python service template organized around clean architecture
boundaries:

- `presentation` handles entrypoints such as HTTP routes, workers, and CLIs.
- `application` holds use cases, services, ports, event handlers, and app
  wiring.
- `domain` holds entities, value objects, domain errors, and event contracts.
- `infrastructure` holds concrete adapters such as persistence, config, logging,
  and external clients.

See [docs/architecture.md](docs/architecture.md) for the full component
blueprints and extension checklist.

## Requirements

- Python `>=3.12,<3.14`
- [uv](https://docs.astral.sh/uv/) for dependency management
- `task` if you want to use the bundled task commands

## Setup

```bash
task sync
```

If this template is specialized for a concrete product, add project-specific
environment variables to `.env.example` and document them here.

## Running

Inspect `pyproject.toml` for available console scripts:

```toml
[project.scripts]
dev = "main:main"
```

For local development:

```bash
task dev      # or: uv run dev
```

When the template is adapted, replace this section with the concrete entrypoints
that developers should exercise.

## Testing

```bash
task test     # uv run python -m pytest
task check    # lint, then test
task lint     # uv run python -m ruff check src tests
task format   # uv run python -m ruff format src tests
```

See [docs/tests.md](docs/tests.md) for testing conventions.

## Project Layout

```text
  src/
  domain/          # entities, value objects, domain errors, events, value enums
  application/     # app facade, use cases, services, handlers, ports
  infrastructure/  # config, persistence, concrete adapters, logging
  presentation/    # HTTP, worker, CLI, or other process entrypoints
  main.py          # optional local process launcher
tests/             # pytest suite
  docs/              # architecture, rules, workflows, tests, and agent guidance
```

The documentation set is written for both engineers and AI coding agents:

- [AGENTS.md](AGENTS.md) defines bootstrap loading order and precedence.
- [docs/rules.md](docs/rules.md) defines reusable coding standards.
- [docs/workflows.md](docs/workflows.md) defines task execution procedure.
- [docs/architecture.md](docs/architecture.md) defines the template
  architecture and extension blueprints.
- [docs/tests.md](docs/tests.md) defines testing conventions.

## Job API Surface

Job endpoints are registered under `/jobs`:

- `GET /jobs/{job_id}`
  - Returns `JobStatusResponse` for a single job.
  - Response status codes:
    - `202` while the job is still `pending`/`running`
    - `200` for terminal states.
- `GET /jobs/ws/{job_id}` (WebSocket)
  - Opens a persistent stream of job-status updates for the same `job_id`.
  - Useful for UI or CLI clients that need live progress.
  - Each message mirrors `JobStatusResponse` fields.
  - The connection is typically closed by the server when status is terminal
    (`done` / `failed`).

Swagger/OpenAPI in FastAPI is HTTP-focused, so this websocket route is not shown in
`/docs` by default; keep this section as the canonical websocket contract for clients.
