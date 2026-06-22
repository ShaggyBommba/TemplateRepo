"""Worker application entry point."""

from __future__ import annotations

import asyncio

from application.app import get_app


async def run() -> None:
    app = get_app()
    await app.start()
    try:
        await app.daemon()
    finally:
        await app.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
