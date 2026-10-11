"""Run with PYTHONPATH=apps/api uv run --env-file apps/api/.env python -m app.jobs.grouping."""

import argparse
import json
import logging
import signal
from datetime import timedelta
from threading import Event as StopEvent
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import make_engine
from app.models import AuditLog, Event, GroupingJob, User, utcnow
from app.schemas.grouping import GroupingInput
from app.services import grouping, notifications
from app.services.grouping_engine import GroupingError

logger = logging.getLogger("rapo.worker")


def process_one(engine: Engine) -> str | None:
    # Per-event transactions release their lock on success, failure, or process death.
    # SKIP LOCKED lets other workers handle different events rather than waiting.
    with Session(engine) as db, db.begin():
        now = utcnow()
        event = db.scalar(
            select(Event)
            .outerjoin(GroupingJob, GroupingJob.event_id == Event.id)
            .where(
                Event.status == "PUBLISHED",
                Event.grouping_at <= now,
                Event.registration_closes_at <= now,
                Event.start_at > now,
                Event.confirmation_deadline > now,
                or_(
                    GroupingJob.event_id.is_(None),
                    (GroupingJob.status != "SUCCEEDED") & (GroupingJob.next_attempt_at <= now),
                ),
            )
            .order_by(Event.grouping_at, Event.id)
            .limit(1)
            .with_for_update(of=Event, skip_locked=True)
        )
        if event is None:
            return None
        job = db.get(GroupingJob, event.id)
        attempts = (job.attempts if job else 0) + 1
        run_id = None
        try:
            # A savepoint rolls back even a failure after proposal rows were written.
            with db.begin_nested():
                owner = db.get(User, event.organizer_id)
                if owner is None or owner.role != "organizer":
                    raise GroupingError(
                        "organizer_unavailable",
                        "Organizer access is required. Contact the event owner.",
                    )
                result = grouping.create(
                    db,
                    event.id,
                    owner,
                    GroupingInput(
                        request_id=uuid5(NAMESPACE_URL, f"rapo:scheduled:{event.id}"),
                        seed=event.id.int % 2147483648,
                    ),
                )
                if utcnow() >= min(event.confirmation_deadline, event.start_at):
                    raise GroupingError(
                        "cutoff_passed", "The grouping cutoff passed; the preview was not saved."
                    )
                run_id = result.id
                notifications.send(
                    db,
                    event,
                    event.organizer_id,
                    "GROUPING_READY",
                    "Your scheduled team preview is ready for review and finalization.",
                    f"scheduled:{event.id}:ready",
                )
                db.add(
                    AuditLog(
                        actor_id=event.organizer_id, event_id=event.id, action="grouping.scheduled"
                    )
                )
                db.flush()
            status, code, message = (
                "SUCCEEDED",
                "preview_ready",
                "Scheduled preview is ready for organizer review.",
            )
        except GroupingError as error:
            run_id = None
            status, code, message = "BLOCKED", error.code, str(error)
            notifications.send(
                db,
                event,
                event.organizer_id,
                "GROUPING_BLOCKED",
                message,
                f"scheduled:{event.id}:blocked:{code}",
            )
        except Exception as error:
            run_id = None
            # Never put raw exceptions, SQL parameters, or participant data in logs/UI.
            status, code, message = (
                "FAILED",
                "processing_failed",
                "Scheduled grouping failed. The worker will retry; check its logs.",
            )
            logger.error(
                json.dumps({"event_id": str(event.id), "error_type": type(error).__name__})
            )
        if job is None:
            job = GroupingJob(event_id=event.id)
            db.add(job)
        job.status, job.code, job.message, job.attempts = status, code, message, attempts
        job.run_id, job.updated_at = run_id, utcnow()
        delay = 300 if status == "BLOCKED" else min(3600, 60 * 2 ** min(attempts - 1, 6))
        job.next_attempt_at = job.updated_at + timedelta(seconds=delay)
        db.flush()
        outcome = {"event_id": str(event.id), "status": status, "attempts": attempts, "code": code}
    # Report success only after the transaction has committed.
    logger.info(json.dumps(outcome))
    return status


def run_once(engine: Engine, batch_size: int = 100) -> dict[str, int]:
    totals: dict[str, int] = {}
    for _ in range(batch_size):
        status = process_one(engine)
        if status is None:
            break
        totals[status] = totals.get(status, 0) + 1
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate due grouping previews safely")
    parser.add_argument("--once", action="store_true", help="Process one bounded batch and exit")
    parser.add_argument("--interval", type=int, default=30, help="Seconds between batches (1–3600)")
    parser.add_argument("--batch-size", type=int, default=100, help="Events per batch (1–1000)")
    args = parser.parse_args()
    if not 1 <= args.interval <= 3600 or not 1 <= args.batch_size <= 1000:
        parser.error("Interval must be 1–3600 and batch size 1–1000")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    engine = make_engine(Settings().database_url)
    stop = StopEvent()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        while not stop.is_set():
            try:
                totals = run_once(engine, args.batch_size)
                logger.info(json.dumps({"batch": totals}))
                if args.once:
                    if totals.get("FAILED", 0):
                        raise SystemExit(1)
                    return
            except Exception as error:
                logger.error(json.dumps({"worker_error_type": type(error).__name__}))
                if args.once:
                    raise SystemExit(1) from None
            stop.wait(args.interval)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
