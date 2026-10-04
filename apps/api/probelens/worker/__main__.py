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
    # Daily, plus once at startup so a fresh environment has data without waiting a day.
    scheduler.add_job(jobs.detect_anomalies.send, CronTrigger(hour=0, minute=15), id="detect_anomalies")
    scheduler.add_job(jobs.detect_anomalies.send, id="detect_anomalies_boot")
    scheduler.add_job(
        jobs.snapshot_experiments.send, CronTrigger(hour=0, minute=30), id="snapshot_experiments"
    )
    scheduler.add_job(jobs.snapshot_experiments.send, id="snapshot_experiments_boot")
    scheduler.add_job(jobs.heartbeat, "interval", seconds=60, id="heartbeat")
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
