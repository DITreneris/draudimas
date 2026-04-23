"""Entry point: APScheduler always-on workeris Railway'ui."""
from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.agent import run_cycle
from src.config import Settings, load_settings


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
        "Start: keywords=%s interval=%dmin headless=%s state_dir=%s run_on_start=%s",
        settings.keywords,
        settings.check_interval_minutes,
        settings.headless,
        settings.state_dir,
        settings.run_on_start,
    )

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        _job,
        trigger=IntervalTrigger(minutes=settings.check_interval_minutes),
        args=[settings],
        id="hourly_check",
        name="viesiejipirkimai hourly check",
        next_run_time=datetime.utcnow() if settings.run_on_start else None,
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
