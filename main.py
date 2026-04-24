"""Entry point: APScheduler always-on workeris Railway'ui."""
from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.agent import run_cycle
from src.config import Settings, load_settings

# Fiksuotas tvarkarastis: darbo dienos (pir-pen), 7:00-21:00 Vilniaus laiku
# (15 valandiniu slot'u x 5 dienos = 75 ciklai per savaite). Keiciant - cia.
SCHEDULE_TIMEZONE = "Europe/Vilnius"
SCHEDULE_DAYS = "mon-fri"
SCHEDULE_HOURS = "7-21"
SCHEDULE_MINUTE = 0


def setup_logging(level: str) -> None:
    # Force stdout to UTF-8 so Lithuanian diacritics don't explode on Windows
    # PowerShell (cp1252 default). No-op on Linux where stdout is already
    # UTF-8 (Railway container).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def _job(settings: Settings) -> None:
    try:
        run_cycle(settings)
    except Exception:
        logging.getLogger(__name__).exception("run_cycle nepavyko")


def main() -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    log = logging.getLogger("main")

    settings.state_dir.mkdir(parents=True, exist_ok=True)

    log.info(
        "Start: keywords=%s schedule='%s %s:%02d %s' headless=%s state_dir=%s "
        "run_on_start=%s",
        settings.keywords,
        SCHEDULE_DAYS,
        SCHEDULE_HOURS,
        SCHEDULE_MINUTE,
        SCHEDULE_TIMEZONE,
        settings.headless,
        settings.state_dir,
        settings.run_on_start,
    )
    if settings.check_interval_minutes != 60:
        log.warning(
            "CHECK_INTERVAL_MINUTES=%d ignoruojamas - tvarkarastis hardcoded "
            "(cron %s %s:%02d %s)",
            settings.check_interval_minutes,
            SCHEDULE_DAYS,
            SCHEDULE_HOURS,
            SCHEDULE_MINUTE,
            SCHEDULE_TIMEZONE,
        )

    scheduler = BlockingScheduler(timezone=SCHEDULE_TIMEZONE)
    scheduler.add_job(
        _job,
        trigger=CronTrigger(
            day_of_week=SCHEDULE_DAYS,
            hour=SCHEDULE_HOURS,
            minute=SCHEDULE_MINUTE,
            timezone=SCHEDULE_TIMEZONE,
        ),
        args=[settings],
        id="business_hours_check",
        name=f"viesiejipirkimai {SCHEDULE_DAYS} {SCHEDULE_HOURS}:00 {SCHEDULE_TIMEZONE}",
        next_run_time=datetime.now(timezone.utc) if settings.run_on_start else None,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    def _shutdown(signum, frame):
        log.info("Gautas signalas %s, stabdau scheduler", signum)
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGINT, _shutdown)
    try:
        signal.signal(signal.SIGTERM, _shutdown)
    except (AttributeError, ValueError):
        pass

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler sustabdytas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
