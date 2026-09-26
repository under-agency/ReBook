"""Бот заявок: кнопки лендинга и Avito ведут сюда, заявка приходит нам в личку.

Запуск:  LEAD_BOT_TOKEN=... LEAD_NOTIFY_CHAT_IDS=111,222 python bot.py
Свой chat id можно узнать, написав боту /id.
"""
import logging
import os

import telebot
from telebot import types

from leads import Lead, Reply, answer, notify_html, start

log = logging.getLogger("lead-bot")

TOKEN = os.environ["LEAD_BOT_TOKEN"]
NOTIFY = [int(x) for x in os.environ.get("LEAD_NOTIFY_CHAT_IDS", "").split(",") if x.strip()]
PRIVACY_URL = os.environ.get("PRIVACY_URL", "").strip()

bot = telebot.TeleBot(TOKEN, threaded=False)
# только пока человек отвечает на вопросы; после отправки заявки запись удаляется
sessions: dict[int, Lead] = {}


def _markup(reply: Reply):
    if reply.done:
        return types.ReplyKeyboardRemove()
    if not reply.buttons and not reply.ask_phone:
        return None
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    if reply.ask_phone:
        kb.add(types.KeyboardButton("📱 Поделиться номером", request_contact=True))
    for label in reply.buttons:
        kb.add(types.KeyboardButton(label))
    return kb


def _send(chat_id: int, reply: Reply) -> None:
    bot.send_message(chat_id, reply.text, reply_markup=_markup(reply))


@bot.message_handler(commands=["id"])
def on_id(msg):
    bot.reply_to(msg, f"Ваш chat id: {msg.chat.id}")


def _begin(chat_id: int, payload: str | None) -> None:
    lead, reply = start(payload)
    sessions[chat_id] = lead
    if PRIVACY_URL:
        reply.text += f"\n\nОставляя заявку, вы соглашаетесь с политикой конфиденциальности: {PRIVACY_URL}"
    _send(chat_id, reply)


@bot.message_handler(commands=["start"])
def on_start(msg):
    parts = (msg.text or "").split(maxsplit=1)
    _begin(msg.chat.id, parts[1] if len(parts) > 1 else None)


@bot.message_handler(content_types=["text", "contact"])
def on_message(msg):
    lead = sessions.get(msg.chat.id)
    if lead is None:  # написали без /start — начинаем заявку без метки
        _begin(msg.chat.id, None)
        return
    phone = msg.contact.phone_number if msg.content_type == "contact" and msg.contact else None
    reply = answer(lead, msg.text, phone)
    _send(msg.chat.id, reply)
    if not reply.done:
        return
    sessions.pop(msg.chat.id, None)
    text = notify_html(lead, msg.from_user.id, msg.from_user.username)
    delivered = 0
    for chat_id in NOTIFY:
        try:
            bot.send_message(chat_id, text, parse_mode="HTML")
            delivered += 1
        except Exception:
            # в лог — только чат получателя, без данных заявки
            log.exception("заявка не доставлена в чат %s", chat_id)
    if not delivered:
        log.error("заявку некуда доставить: проверьте LEAD_NOTIFY_CHAT_IDS")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not NOTIFY:
        log.warning("LEAD_NOTIFY_CHAT_IDS пуст: напишите боту /id и впишите chat id в .env")
    bot.infinity_polling(skip_pending=True)
