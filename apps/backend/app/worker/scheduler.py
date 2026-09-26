import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from app.db import SessionLocal
from app.worker.billing import update_billing_statuses
from app.worker.reminders import run_autoclose, send_reminders

log = logging.getLogger("rebook.worker")


def job_reminders() -> None:
    db = SessionLocal()
    try:
        stats = send_reminders(db)
        db.commit()
        if any(stats.values()):
            log.info("Напоминания: %s", stats)
    except Exception:
        db.rollback()
        log.exception("Ошибка каскада напоминаний")
    finally:
        db.close()


def job_autoclose() -> None:
    db = SessionLocal()
    try:
        n = run_autoclose(db)
        db.commit()
        if n:
            log.info("Автозакрытие: %d записей", n)
    except Exception:
        db.rollback()
        log.exception("Ошибка автозакрытия")
    finally:
        db.close()


def job_billing() -> None:
    db = SessionLocal()
    try:
        changes = update_billing_statuses(
            db, datetime.now(ZoneInfo("Europe/Moscow")).date())
        db.commit()
        for salon_id, status in changes:
            log.info("Биллинг: салон %d → %s", salon_id, status)
    except Exception:
        db.rollback()
        log.exception("Ошибка биллинга")
    finally:
        db.close()


def build_scheduler() -> BackgroundScheduler:
    # tzlocal на Windows ненадёжен — таймзону задаём явно
    sched = BackgroundScheduler(timezone=timezone.utc)
    sched.add_job(job_reminders, "interval", minutes=15,
                  next_run_time=datetime.now(timezone.utc))
    sched.add_job(job_autoclose, "interval", minutes=15)
    sched.add_job(job_billing, "cron", hour=1)  # 01:00 UTC ≈ 04:00 МСК
    return sched
