"""Telegram-адаптер: переводит апдейты telebot в вызовы dialogs и рендерит Reply."""
import logging

import telebot
from telebot.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.db import SessionLocal
from app.models import Salon
from app.bots import dialogs

log = logging.getLogger("rebook.bot")


def _markup(reply: dialogs.Reply):
    if reply.request_contact:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add(KeyboardButton("📱 Поделиться контактом", request_contact=True))
        return kb
    if reply.buttons:
        kb = InlineKeyboardMarkup()
        for row in reply.buttons:
            kb.row(*[InlineKeyboardButton(label, callback_data=data) for label, data in row])
        return kb
    return ReplyKeyboardRemove()


def build_bot(token: str, salon_id: int) -> telebot.TeleBot:
    bot = telebot.TeleBot(token, threaded=True)

    def _deliver(chat_id: int, reply: dialogs.Reply, salon: Salon) -> None:
        bot.send_message(chat_id, reply.text, reply_markup=_markup(reply))
        if reply.admin_notify and salon.admin_tg_chat_id:
            try:
                bot.send_message(salon.admin_tg_chat_id, reply.admin_notify)
            except Exception:
                log.warning("Не доставлено уведомление админу салона %d", salon.id)

    def _with_session(handler):
        def wrapped(update):
            db = SessionLocal()
            try:
                salon = db.get(Salon, salon_id)
                handler(update, db, salon)
                db.commit()
            except Exception:
                db.rollback()
                log.exception("Ошибка обработки апдейта")
            finally:
                db.close()
        return wrapped

    @bot.message_handler(commands=["start"])
    @_with_session
    def cmd_start(msg, db, salon):
        parts = msg.text.split(maxsplit=1)
        param = parts[1].strip() if len(parts) > 1 else None
        reply = dialogs.handle_start(db, salon, msg.from_user.id,
                                     msg.from_user.first_name, param)
        _deliver(msg.chat.id, reply, salon)

    @bot.message_handler(commands=["admin"])
    @_with_session
    def cmd_admin(msg, db, salon):
        # привязка чата админа салона: сюда идут уведомления о записях и тикеты
        salon.admin_tg_chat_id = msg.chat.id
        bot.send_message(msg.chat.id, "✅ Этот чат привязан как чат администратора "
                                      f"салона «{salon.name}». Сюда будут приходить "
                                      "уведомления о записях и вопросы клиентов.")

    @bot.callback_query_handler(func=lambda c: True)
    @_with_session
    def on_callback(call, db, salon):
        reply = dialogs.handle_callback(db, salon, call.from_user.id,
                                        call.from_user.first_name, call.data)
        bot.answer_callback_query(call.id)
        _deliver(call.message.chat.id, reply, salon)

    @bot.message_handler(content_types=["contact"])
    @_with_session
    def on_contact(msg, db, salon):
        reply = dialogs.handle_text(db, salon, msg.from_user.id,
                                    msg.from_user.first_name, "",
                                    contact_phone=msg.contact.phone_number)
        _deliver(msg.chat.id, reply, salon)

    @bot.message_handler(content_types=["text"])
    @_with_session
    def on_text(msg, db, salon):
        reply = dialogs.handle_text(db, salon, msg.from_user.id,
                                    msg.from_user.first_name, msg.text)
        _deliver(msg.chat.id, reply, salon)

    return bot
