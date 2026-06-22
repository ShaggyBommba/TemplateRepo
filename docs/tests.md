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
from application.usecases.things import CreateThingUseCase
```

`asyncio_mode = "auto"` runs `async def` tests without per-test markers.

Install test dependencies with:

```bash
task sync
```

## Test Layout

Tests live under `tests/`, one file per behavior area. Prefer names that expose
the boundary under test:

```text
tests/test_<area>_domain.py
tests/test_<area>_usecases.py
tests/test_<area>_services.py
tests/test_<area>_persistence.py
tests/test_<area>_routes.py
tests/test_<area>_worker.py
tests/test_config.py
tests/test_cli.py
```

There is no requirement to add shared fixtures early. Start with small fakes in
the test file that needs them. If shared setup grows, add fixtures in
`tests/conftest.py` and reusable port fakes in `tests/fakes.py`.

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
uv run python -m pytest tests/test_<area>_usecases.py -q
uv run python -m pytest tests/test_<area>_routes.py -q
uv run python -m pytest -k create_thing -q
uv run python -m pytest --collect-only -q
```

Lint and format the same paths the tasks target:

```bash
task lint
task format
```

## Unit Test Rules

Write unit tests around observable behavior. A unit is usually a class or
use-case behavior at a domain, application, infrastructure-adapter, or
presentation boundary:

- domain model behavior
- application use-case and handler behavior through ports
- service behavior such as queue claim and event dispatch
- infrastructure adapter behavior through public methods
- presentation behavior through request, route, command, or worker boundaries

Use the Arrange, Act, Assert shape:

```python
def test_create_thing_usecase_persists_entity() -> None:
    # Arrange
    uow = FakeUnitOfWork()
    usecase = CreateThingUseCase(lambda: uow)

    # Act
    thing = usecase("example")

    # Assert
    assert uow.things.get(thing.id) == thing
    assert uow.committed
```

Keep one behavior per test. Multiple asserts are fine when they describe the
same behavior, such as "entity was persisted and the unit of work committed".
Split the test when the asserts describe different behavior.

Prefer deterministic inputs:

- fixed dates and ids when identity matters
- `tmp_path` for filesystem work
- `monkeypatch` for environment variables or global functions
- injected settings instead of ambient `.env` state
- fake ports for application and service unit tests

Avoid external services in unit tests:

- no real databases unless the test is explicitly an integration test
- no network or live provider session
- no provider SDK calls
- no sleeps
- no shared mutable process state unless reset by a fixture

If real infrastructure matters, write an integration test and name it as such.

## Fakes, Mocks, And Ports

Prefer this order:

1. Real implementation, when it is fast, deterministic, and local.
2. Fake implementation, when the real dependency is slow, nondeterministic, or
   external.
3. Mock, when neither a real implementation nor a fake can express the case
   cleanly.

Application and service code should be easy to fake because dependencies are
the `Protocol` ports in `src/application/adapters/core.py`, such as:

```text
UnitOfWork
CrudRepo
OutboxRepo
Handler
Dispatcher
Runner
```

Use mocks mainly at hard process boundaries:

- web server launch functions
- process spawning
- time and sleep
- environment access
- provider SDK clients and other third-party clients

Do not mock a repository when the repository itself is the subject under test.
Use a real local storage implementation or test database in a repository test
instead.

## Layer Guidance

Domain and application tests:

- assert domain model, use-case, and handler behavior
- depend on ports, not concrete infrastructure
- use plain values and deterministic ids

Service tests:

- assert queue claim, event dispatch, retry, and idempotency behavior
- instantiate service classes with port fakes

Infrastructure tests:

- test rows, repositories, units of work, config, and adapter parsing
- use real local infrastructure only when it stays fast and deterministic
- keep network and provider clients behind fakes or local fixtures

Presentation tests:

- call route functions directly with a fake app/unit of work, or assert the
  framework app's public surface
- do not start long-running servers or process launchers

## Naming

Use behavior names:

```text
test_create_thing_usecase_persists_entity
test_create_thing_route_rejects_invalid_name
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

It also follows the broader testing guidance that healthy suites have many fast
unit tests, fewer integration tests, and very few end-to-end tests; and that
tests are more trustworthy when they use real implementations or fakes before
falling back to mocks.

References:

- pytest good integration practices: https://docs.pytest.org/en/stable/explanation/goodpractices.html
- pytest fixtures: https://docs.pytest.org/en/stable/explanation/fixtures.html
- pytest `monkeypatch`: https://docs.pytest.org/en/stable/how-to/monkeypatch.html
- pytest `tmp_path`: https://docs.pytest.org/en/stable/how-to/tmp_path.html
- Practical Test Pyramid: https://martinfowler.com/articles/practical-test-pyramid.html
- Google Testing Blog on mocks and fakes: https://testing.googleblog.com/2024/02/increase-test-fidelity-by-avoiding-mocks.html
