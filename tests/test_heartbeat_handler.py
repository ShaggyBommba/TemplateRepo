from __future__ import annotations

import asyncio

import pytest

from application.handlers.heartbeat import HeartbeatHandler
from domain.event import Heartbeat


async def test_heartbeat_handler_sleeps_once_per_beat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    handler = HeartbeatHandler()

    # Act
    await handler(Heartbeat(payload={"beats": 3, "interval": 0.25}))

    # Assert
    assert delays == [0.25, 0.25, 0.25]
