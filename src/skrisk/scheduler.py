"""Scheduling primitives for recurring SK Risk scans."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from collections.abc import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("skrisk.scheduler")


def next_scan_time(*, interval_hours: int = 72, now: datetime | None = None) -> datetime:
    """Compute the next scan time from the current point."""

    now = now or datetime.now(UTC)
    return now + timedelta(hours=interval_hours)


class ScanScheduler:
    """Manage recurring collection and analysis cycles."""

    def __init__(
        self,
        *,
        run_cycle: Callable[[], Awaitable[None]],
        interval_hours: int = 72,
    ) -> None:
        self._run_cycle = run_cycle
        self._interval_hours = interval_hours
        self._scheduler = AsyncIOScheduler()

    def start(self, run_immediately: bool = False) -> None:
        """Start the scheduler."""

        self._scheduler.add_job(
            self._run_cycle,
            trigger=IntervalTrigger(hours=self._interval_hours),
            id="skrisk-cycle",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            "Started SK Risk scheduler with %s-hour interval",
            self._interval_hours,
        )

        if run_immediately:
            self._scheduler.add_job(self._run_cycle, id="skrisk-initial", replace_existing=True)

    def stop(self) -> None:
        """Stop the scheduler if it is running."""

        if getattr(self._scheduler, "running", False):
            self._scheduler.shutdown(wait=False)
