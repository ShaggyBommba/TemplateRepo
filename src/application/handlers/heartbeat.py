"""Heartbeat demo-job handler."""

from __future__ import annotations

import asyncio
import logging

from domain.event import Heartbeat

logger = logging.getLogger(__name__)


class HeartbeatHandler:
    """Emit each beat for one heartbeat job, pausing between beats."""

    async def __call__(self, event: Heartbeat) -> None:
        beats = int(event.payload["beats"])
        interval = float(event.payload["interval"])

        logger.info("Heartbeat job started id=%s beats=%s", event.id, beats)
        for beat in range(1, beats + 1):
            logger.info("Heartbeat id=%s beat=%s/%s", event.id, beat, beats)
            await asyncio.sleep(interval)
        logger.info("Heartbeat job finished id=%s", event.id)
