"""Paleidzia viena cikla ir iseina. Naudinga lokaliam testavimui."""
from __future__ import annotations

import logging
import sys

from src.agent import run_cycle
from src.config import load_settings
from main import setup_logging


def main() -> int:
    settings = load_settings()
    setup_logging(settings.log_level)
    log = logging.getLogger("run_once")
    log.info("Vienkartinis ciklas: keywords=%s", settings.keywords)
    summary = run_cycle(settings)
    log.info("Apibendrinimas: %s", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
