# Tests

This repository uses pytest. Treat tests as behavior contracts at architecture
boundaries, not as snapshots of private implementation details.

## Setup

The pytest configuration lives in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"
addopts = "-ra"
```

`pythonpath = ["src"]` lets tests import the flat packages directly, for
example:

```python
from application.app import App
```

`asyncio_mode = "auto"` runs `async def` tests without per-test markers.

Install test dependencies with:

```bash
task sync
```

The default suite is infrastructure-backed. `tests/conftest.py` loads `.env`,
starts local infrastructure with `task infra:up`, creates a fresh Postgres test
database named `test`, applies asyncpg migrations, and exposes a `settings`
fixture whose database points at that test database. Tests should construct real
application wiring with:

```python
app = App.create(settings)
```

Use that app, its asyncpg unit of work, and the framework test clients to exercise
behavior through the same boundaries the service uses locally. Do not construct
mock repositories or mock use cases when the configured local infrastructure can
provide the dependency.

Use `async with app.uow() as uow:` when a test needs direct repository or
transaction access for setup, cleanup, or infrastructure-level assertions.

The local `.env` file is required for infrastructure-backed tests. Copy
`.env.example` to `.env` and keep the configured Postgres port aligned with
`infrastructure/docker-compose.yml`.

GitHub Actions writes a CI-specific `.env` from workflow environment variables,
starts the Compose `db` service, validates migrations against the `app`
database, and then runs pytest. The pytest fixture creates and migrates its own
`test` database on that same Postgres instance.

## Test Layout

Tests live under `tests/`, one file per behavior area. Prefer names that expose
the boundary under test:

```text
tests/test_<area>_domain.py
tests/test_<area>_application.py
tests/test_<area>_services.py
tests/test_<area>_persistence.py
tests/test_<area>_routes.py
tests/test_<area>_worker.py
tests/test_<area>_integration.py
tests/test_config.py
tests/test_cli.py
```

Keep shared infrastructure setup in `tests/conftest.py`. Prefer local helpers in
the test file for behavior-specific cleanup, such as truncating an affected
table before and after a test. Add reusable fixtures only when at least two test
files need the same real setup.

## Running Tests

For quick local iteration:

```bash
uv run python -m pytest
```

For evaluation, run the same checks the repository task flow expects:

```bash
task test
task check
```

Useful focused commands:

```bash
uv run python -m pytest tests/test_<area>_application.py -q
uv run python -m pytest tests/test_<area>_routes.py -q
uv run python -m pytest -k heartbeat -q
uv run python -m pytest --collect-only -q
```

Lint and format the same paths the tasks target:

```bash
task lint    # src tests migrations
task format  # src tests migrations
```

## Test Rules

Write tests around observable behavior. The preferred subject is an architecture
boundary wired with real local infrastructure:

- domain model behavior
- application behavior through `App.create(settings)`
- service behavior such as queue claim and event dispatch through real storage
- infrastructure adapter behavior through public methods and migrated tables
- presentation behavior through request, route, command, or worker boundaries

Use the Arrange, Act, Assert shape:

```python
async def test_request_heartbeat_persists_pending_job(settings: Settings) -> None:
    # Arrange
    app = App.create(settings)

    # Act
    job = await app.request_heartbeat(beats=2, interval=0.01)

    # Assert
    loaded = await app.get_job_status(job.id)
    assert loaded.payload == {"beats": 2, "interval": 0.01}
    assert loaded.status == JobStatus.PENDING
```

Keep one behavior per test. Multiple asserts are fine when they describe the
same behavior, such as "entity was persisted and the unit of work committed".
Split the test when the asserts describe different behavior.

Prefer deterministic inputs:

- fixed dates and ids when identity matters
- `tmp_path` for filesystem work
- `monkeypatch` for environment variables or global functions
- injected settings instead of ambient `.env` state
- short intervals such as `0.001` for jobs that wait

Avoid hidden external state:

- do not use developer or production databases
- do not depend on data left by a previous test
- no provider SDK calls
- no real sleeps longer than needed to prove behavior
- no shared mutable process state unless reset by a fixture

When a test writes to shared infrastructure, reset only the tables or provider
state it owns. Prefer cleanup before and after the test so reruns are stable
after an interrupted session.

## Infrastructure And Doubles

Prefer this order:

1. Real implementation, when it is fast, deterministic, and local.
2. Local provider fixture, when the dependency is external but the compose stack
   supplies it, such as Postgres or Keycloak.
3. Fake implementation, when the real dependency is slow, nondeterministic, or
   external.
4. Mock, when neither a real implementation nor a fake can express the case
   cleanly.

Application and service code still depend on `Protocol` ports in
`src/application/adapters/core.py`, such as:

```text
UnitOfWork
CrudRepo
OutboxRepo
Handler
Dispatcher
Runner
```

Use those ports to keep infrastructure swappable in production code, not as a
reason to replace local infrastructure in behavior tests.

Use mocks mainly at hard process boundaries that are not the behavior under
test:

- web server launch functions
- process spawning
- time and sleep
- environment access
- unavailable provider SDK clients and other third-party clients

Do not mock a repository when the repository itself is the subject under test.
Use the migrated test database instead.

## Layer Guidance

Domain and application tests:

- assert domain model, use-case, and handler behavior
- construct real application wiring when behavior crosses persistence,
  queue/outbox, auth, or configuration boundaries
- use plain values and deterministic ids

Service tests:

- assert queue claim, event dispatch, retry, and idempotency behavior
- prefer the asyncpg unit of work and migrated outbox table

Infrastructure tests:

- test rows, repositories, units of work, config, and adapter parsing
- test migration configuration in unit tests, and validate real migration
  application against a fresh Postgres database in CI or an explicit
  infrastructure-backed check
- use real local infrastructure through `tests/conftest.py`
- keep live external provider clients behind local fixtures unless the test is
  explicitly provider-backed

Presentation tests:

- use framework test clients and override `get_app` only to inject a real
  `App.create(settings)` instance configured for the test database
- do not start long-running servers or process launchers

## Naming

Use behavior names:

```text
test_request_heartbeat_persists_pending_job
test_heartbeat_route_rejects_invalid_body
test_runner_requeues_failed_event
```

Avoid names that only repeat a method:

```text
test_add
test_create
test_list
```

Short names are good when they stay clear, but test names should explain the
expected behavior that failed.

## Research Basis

This guide follows the current pytest recommendations for a separate `tests/`
directory with a `src/` layout and configured `pythonpath`, pytest fixtures as
explicit arrange state, `tmp_path` for isolated filesystem tests, and
`monkeypatch` for temporary environment or global patches.

It also follows the broader testing guidance that tests are more trustworthy
when they use real implementations before falling back to fakes or mocks. In
this template, the local compose stack makes real Postgres-backed behavior the
default for application workflow tests.

References:

- pytest good integration practices: https://docs.pytest.org/en/stable/explanation/goodpractices.html
- pytest fixtures: https://docs.pytest.org/en/stable/explanation/fixtures.html
- pytest `monkeypatch`: https://docs.pytest.org/en/stable/how-to/monkeypatch.html
- pytest `tmp_path`: https://docs.pytest.org/en/stable/how-to/tmp_path.html
- Practical Test Pyramid: https://martinfowler.com/articles/practical-test-pyramid.html
- Google Testing Blog on mocks and fakes: https://testing.googleblog.com/2024/02/increase-test-fidelity-by-avoiding-mocks.html
