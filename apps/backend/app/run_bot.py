"""Dev-процесс: Telegram-полинг + APScheduler в одном процессе.

    python -m app.run_bot

НЕ запускать под --reload и не использовать токен legacy демо-бота
(два полинга на один токен → Telegram 409).
"""
import logging

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Salon
from app.bots.telegram import build_bot
from app.worker.scheduler import build_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("rebook")


def main() -> None:
    db = SessionLocal()
    try:
        if settings.bot_salon_id:
            salon = db.get(Salon, settings.bot_salon_id)
        else:
            salon = db.scalar(select(Salon).where(Salon.tg_bot_token.is_not(None))
                              .order_by(Salon.id))
        if salon is None or not salon.tg_bot_token:
            log.error("Нет салона с токеном бота. Заполните TELEGRAM_BOT_TOKEN в "
                      "apps/backend/.env и пересейдите (python -m app.seed --reset), "
                      "либо задайте токен салону через админку.")
        salon_id, token, name = (salon.id, salon.tg_bot_token, salon.name) if salon else (None, None, None)
    finally:
        db.close()

    scheduler = build_scheduler()
    scheduler.start()
    log.info("Воркер запущен: напоминания и автозакрытие каждые 15 мин.")

    if token:
        bot = build_bot(token, salon_id)
        log.info("Бот салона «%s» слушает…", name)
        bot.infinity_polling(skip_pending=True)
    else:
        log.info("Полинг не запущен (нет токена) — работает только воркер. Ctrl+C для выхода.")
        import time
        while True:
            time.sleep(60)


if __name__ == "__main__":
    main()
