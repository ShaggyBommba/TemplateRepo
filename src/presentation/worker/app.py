"""Worker application entry point."""

from __future__ import annotations

import asyncio

from application.app import get_app


def main() -> None:
    app = get_app()
    app.start()
    try:
        asyncio.run(app.daemon())
    finally:
        app.close()


if __name__ == "__main__":
    main()
