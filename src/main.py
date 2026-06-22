from __future__ import annotations
import sys
from collections.abc import Callable
from multiprocessing import Process

import click

from presentation.api.app import main as api_main
from presentation.htmx.app import main as htmx_main
from presentation.worker.app import main as worker_main

SERVICES = [
    ("api", api_main, "cyan"),
    ("htmx", htmx_main, "magenta"),
    ("worker", worker_main, "green"),
]


class PrefixedStream:
    """Prepend a colored service tag to each new output line."""

    def __init__(self, stream, prefix: str) -> None:
        self.stream, self.prefix, self.bol = stream, prefix, True

    def write(self, text: str) -> None:
        for line in text.splitlines(keepends=True):
            if self.bol and line != "\n":
                self.stream.write(f"{self.prefix} ")
            self.stream.write(line)
            self.bol = line.endswith("\n")

    def flush(self) -> None:
        self.stream.flush()

    def __getattr__(self, name: str):
        return getattr(self.stream, name)


def run(name: str, func: Callable[[], None], color: str) -> None:
    prefix = click.style(f"[{name.upper()}]", fg=color, bold=True)
    sys.stdout = PrefixedStream(sys.stdout, prefix)
    sys.stderr = PrefixedStream(sys.stderr, prefix)
    func()


def stop(procs: list[Process]) -> None:
    for p in procs:
        if p.is_alive():
            p.terminate()
    for p in procs:
        p.join()


def wait(procs: list[Process]) -> Process:
    while True:
        for p in procs:
            p.join(timeout=0.2)
            if p.exitcode is not None:
                return p


def main() -> None:
    procs = [Process(target=run, args=s, name=s[0]) for s in SERVICES]
    for p in procs:
        p.start()
    try:
        stopped = wait(procs)
        code = stopped.exitcode

        if code:
            click.echo(f"\n{stopped.name} exited with code {code}.", err=True)
            raise SystemExit(code)
    except KeyboardInterrupt:
        click.echo("\nStopping all services...")
    finally:
        stop(procs)


if __name__ == "__main__":
    main()
