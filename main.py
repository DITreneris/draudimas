"""Entry point: APScheduler always-on workeris Railway'ui."""
from __future__ import annotations

import logging
import signal
import subprocess
import sys
from datetime import datetime, timezone
from logging import Handler, LogRecord
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import Settings, load_settings
from src.notifier import send_ops_alert, telegram_from_settings

# Fiksuotas tvarkarastis: darbo dienos (pir-pen), 7:00-21:00 Vilniaus laiku
# (15 valandiniu slot'u x 5 dienos = 75 ciklai per savaite). Keiciant - cia.
SCHEDULE_TIMEZONE = "Europe/Vilnius"
SCHEDULE_DAYS = "mon-fri"
SCHEDULE_HOURS = "7-21"
SCHEDULE_MINUTE = 0

_RUN_ONCE_PATH = Path(__file__).resolve().parent / "run_once.py"


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


class _SchedulerSkipAlertHandler(Handler):
    """Ops alert when APScheduler skips a job (max_instances reached)."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(level=logging.WARNING)
        self._settings = settings
        self._telegram = telegram_from_settings(
            settings.telegram_enabled,
            settings.telegram_bot_token,
            settings.telegram_chat_id,
        )

    def emit(self, record: LogRecord) -> None:
        try:
            msg = record.getMessage()
            if "maximum number of running instances reached" not in msg:
                return
            send_ops_alert(
                state_path=self._settings.ops_alert_state_path,
                ops_alert_enabled=self._settings.ops_alert_enabled,
                telegram=self._telegram,
                alert_key="scheduler_skip",
                message=(
                    "Scheduler praleido cikla: uzstriges run_cycle "
                    "(max_instances=1). Jei kartojasi po deploy — restart."
                ),
            )
        except Exception:
            self.handleError(record)


def _job(settings: Settings) -> None:
    log = logging.getLogger(__name__)
    telegram = telegram_from_settings(
        settings.telegram_enabled,
        settings.telegram_bot_token,
        settings.telegram_chat_id,
    )
    try:
        proc = subprocess.run(
            [sys.executable, str(_RUN_ONCE_PATH)],
            timeout=settings.cycle_max_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.error(
            "Ciklas virsijo %ds (subprocess timeout) — nutrauktas",
            settings.cycle_max_seconds,
        )
        send_ops_alert(
            state_path=settings.ops_alert_state_path,
            ops_alert_enabled=settings.ops_alert_enabled,
            telegram=telegram,
            alert_key="cycle_timeout",
            message=(
                f"Ciklas virsijo {settings.cycle_max_seconds}s ir buvo nutrauktas "
                "(subprocess timeout)"
            ),
        )
        return
    except Exception:
        log.exception("Subprocess run_once nepavyko")
        send_ops_alert(
            state_path=settings.ops_alert_state_path,
            ops_alert_enabled=settings.ops_alert_enabled,
            telegram=telegram,
            alert_key="subprocess_error",
            message="Subprocess run_once nepavyko (exception)",
        )
        return

    if proc.returncode != 0:
        log.warning("run_once baigesi su exit code %d", proc.returncode)
        send_ops_alert(
            state_path=settings.ops_alert_state_path,
            ops_alert_enabled=settings.ops_alert_enabled,
            telegram=telegram,
            alert_key="cycle_exit_fail",
            message=f"Ciklas baigesi su klaida (exit code {proc.returncode})",
        )


def main() -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    log = logging.getLogger("main")

    settings.state_dir.mkdir(parents=True, exist_ok=True)

    skip_handler = _SchedulerSkipAlertHandler(settings)
    logging.getLogger("apscheduler.scheduler").addHandler(skip_handler)

    if settings.wipe_db_on_start:
        settings.db_path.unlink(missing_ok=True)
        log.warning(
            "WIPE_DB_ON_START=true -> istrinta DB %s. ISJUNK si kintamaji po "
            "wipe'o, kad nebutu trinama kiekvieno restart'o metu.",
            settings.db_path,
        )
        send_ops_alert(
            state_path=settings.ops_alert_state_path,
            ops_alert_enabled=settings.ops_alert_enabled,
            telegram=telegram_from_settings(
                settings.telegram_enabled,
                settings.telegram_bot_token,
                settings.telegram_chat_id,
            ),
            alert_key="wipe_db",
            message="DB wiped — isjunk WIPE_DB_ON_START",
        )

    if settings.seed_items_json:
        seed_path = Path(settings.seed_items_json)
        if not seed_path.is_absolute():
            seed_path = (_RUN_ONCE_PATH.parent / seed_path).resolve()
        if not seed_path.is_file():
            log.error("SEED_ITEMS_JSON nerastas: %s", seed_path)
            return 1
        try:
            from run_seed_items import _load_payload, seed_items

            payload_items = _load_payload(seed_path)
            inserted, skipped, total = seed_items(
                settings.db_path,
                payload_items,
                fresh=settings.seed_items_fresh,
            )
            log.warning(
                "SEED_ITEMS_JSON=%s -> inserted=%d skipped=%d db_total=%d. "
                "ISJUNK SEED_ITEMS_JSON (ir SEED_ITEMS_FRESH) po vienkartinio seed.",
                settings.seed_items_json,
                inserted,
                skipped,
                total,
            )
        except Exception:
            log.exception("SEED_ITEMS_JSON seed nepavyko")
            return 1

    log.info(
        "Start: keywords=%s schedule='%s %s:%02d %s' headless=%s state_dir=%s "
        "run_on_start=%s cycle_max_seconds=%d",
        settings.keywords,
        SCHEDULE_DAYS,
        SCHEDULE_HOURS,
        SCHEDULE_MINUTE,
        SCHEDULE_TIMEZONE,
        settings.headless,
        settings.state_dir,
        settings.run_on_start,
        settings.cycle_max_seconds,
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
