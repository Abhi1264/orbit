"""Worker entrypoint: a Dramatiq worker plus an in-process scheduler.

    python -m probelens.worker

One process is enough for this deployment: the scheduler enqueues periodic
jobs through Redis and the same process's worker threads execute them, so the
job path is identical to an ad-hoc `detect_anomalies.send()` from the API.
"""

import signal
import sys
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dramatiq import Worker

from probelens.core.logging import configure_logging, get_logger
from probelens.worker import jobs

log = get_logger("worker")

def main() -> int:
    configure_logging()
    worker = Worker(jobs.broker, worker_threads=2)
    worker.start()

    scheduler = BackgroundScheduler(timezone="UTC")
    # Daily sweep shortly after midnight UTC; a first run right away so a fresh
    # environment has anomalies without waiting a day.
    scheduler.add_job(jobs.detect_anomalies.send, CronTrigger(hour=0, minute=15), id="detect_anomalies")
    scheduler.add_job(jobs.detect_anomalies.send, id="detect_anomalies_boot")
    scheduler.add_job(jobs.heartbeat, "interval", seconds=60, id="heartbeat", next_run_time=None)
    scheduler.start()
    jobs.heartbeat()
    log.info("worker_started", jobs=[j.id for j in scheduler.get_jobs()])

    stop = threading.Event()

    def _shutdown(*_: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    stop.wait()

    log.info("worker_stopping")
    scheduler.shutdown(wait=False)
    worker.stop()
    return 0

if __name__ == "__main__":
    sys.exit(main())
