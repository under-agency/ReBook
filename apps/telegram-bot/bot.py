#!/usr/bin/env python3
"""ReBook Demo Bot — Telegram-бот записи на чистом Python. KISS."""

import os
import csv
import random
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Base and Root directory paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))

load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.join(ROOT_DIR, ".env"))

bot = telebot.TeleBot(os.environ.get("TELEGRAM_BOT_TOKEN", ""))

# ── Google Sheets (опционально) ────────────────────────────
sheet = None
creds_candidates = [
    os.path.join(BASE_DIR, "google-creds.json"),
    os.path.join(ROOT_DIR, "google-creds.json"),
]
CREDS_FILE = next((p for p in creds_candidates if os.path.exists(p)), creds_candidates[0])
SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

if os.path.exists(CREDS_FILE) and SHEET_ID:
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ])
        gc = gspread.authorize(creds)
        sp = gc.open_by_key(SHEET_ID)
        try:
            sheet = sp.worksheet("Записи")
        except Exception:
            sheet = sp.sheet1
        print(f"✅ Google Sheets подключён! Таблица: '{sp.title}', Лист: '{sheet.title}'")
    except Exception as e:
        print(f"⚠️ Google Sheets не подключён: {e}")
else:
    print("ℹ️  Google Sheets не настроен, пишем только в CSV.")


# ── Каталог услуг ──────────────────────────────────────────
SERVICES = {
    "haircut":  {"name": "✂️ Мужская стрижка",       "price": 1800, "dur": "45 мин"},
    "manicure": {"name": "💅 Маникюр с покрытием",   "price": 2200, "dur": "60 мин"},
    "auto":     {"name": "🚗 Экспресс-ТО",           "price": 1500, "dur": "30 мин"},
}
SLOTS = ["11:00", "14:00", "16:30", "19:00"]
CSV_FILE = os.path.join(ROOT_DIR, "bookings.csv")

# ── Хелперы ────────────────────────────────────────────────
def dates_3():
    wd = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
    mo = ["янв","фев","мар","апр","мая","июн","июл","авг","сен","окт","ноя","дек"]
    out = []
    for i in range(3):
        d = datetime.now() + timedelta(days=i)
        pre = "Сегодня" if i == 0 else ("Завтра" if i == 1 else wd[d.weekday()])
        out.append({
            "label": f"{pre} ({d.day} {mo[d.month-1]})",
            "iso":   d.strftime("%Y-%m-%d"),
            "show":  f"{pre}, {d.day} {mo[d.month-1]}",
        })
    return out

def save(b):
    # CSV (всегда)
    exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(b.keys()))
        if not exists:
            w.writeheader()
        w.writerow(b)
    # Google Sheets (если подключён)
    if sheet:
        try:
            sheet.append_row(list(b.values()), value_input_option="USER_ENTERED")
        except Exception as e:
            print(f"⚠️ Ошибка записи в Sheets: {e}")

def date_display(iso):
    d = next((x for x in dates_3() if x["iso"] == iso), None)
    return d["show"] if d else iso

# ── /start ─────────────────────────────────────────────────
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    kb = InlineKeyboardMarkup()
    for k, s in SERVICES.items():
        kb.add(InlineKeyboardButton(f"{s['name']} — {s['price']} ₽", callback_data=f"s|{k}"))
    bot.send_message(msg.chat.id,
        f"👋 <b>Здравствуйте, {msg.from_user.first_name}!</b>\n\n"
        "Это демо-стенд <b>ReBook</b>.\n"
        "Запишитесь за 30 секунд:\n\n"
        "👇 <b>Выберите услугу:</b>",
        parse_mode="HTML", reply_markup=kb)

# ── Назад к старту ─────────────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data == "back")
def cb_back(c):
    kb = InlineKeyboardMarkup()
    for k, s in SERVICES.items():
        kb.add(InlineKeyboardButton(f"{s['name']} — {s['price']} ₽", callback_data=f"s|{k}"))
    bot.edit_message_text(
        f"👋 <b>Здравствуйте, {c.from_user.first_name}!</b>\n\n"
        "Это демо-стенд <b>ReBook</b>.\n"
        "Запишитесь за 30 секунд:\n\n"
        "👇 <b>Выберите услугу:</b>",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=kb)
    bot.answer_callback_query(c.id)

# ── Выбор услуги → даты ────────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data.startswith("s|"))
def cb_service(c):
    k = c.data.split("|")[1]
    s = SERVICES[k]
    kb = InlineKeyboardMarkup()
    for d in dates_3():
        kb.add(InlineKeyboardButton(d["label"], callback_data=f"d|{k}|{d['iso']}"))
    kb.add(InlineKeyboardButton("« Назад", callback_data="back"))
    bot.edit_message_text(
        f"Вы выбрали: <b>{s['name']}</b> ({s['price']} ₽)\n\n📅 <b>Выберите день:</b>",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=kb)
    bot.answer_callback_query(c.id)

# ── Выбор даты → время ─────────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data.startswith("d|"))
def cb_date(c):
    _, k, iso = c.data.split("|")
    s = SERVICES[k]
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(*[InlineKeyboardButton(f"🕐 {t}", callback_data=f"t|{k}|{iso}|{t}") for t in SLOTS])
    kb.add(InlineKeyboardButton("« Назад", callback_data=f"s|{k}"))
    bot.edit_message_text(
        f"{s['name']}\n📅 {date_display(iso)}\n\n⏰ <b>Выберите время:</b>",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=kb)
    bot.answer_callback_query(c.id)

# ── Подтверждение записи ───────────────────────────────────
@bot.callback_query_handler(func=lambda c: c.data.startswith("t|"))
def cb_time(c):
    _, k, iso, slot = c.data.split("|")
    s = SERVICES[k]
    bid = f"RB-{random.randint(1000, 9999)}"
    name = c.from_user.first_name or "Гость"
    uname = f"@{c.from_user.username}" if c.from_user.username else "—"

    save({
        "id": bid, "created": datetime.now().isoformat(),
        "client_id": c.from_user.id, "name": name, "tg": uname,
        "service": s["name"], "price": s["price"],
        "date": date_display(iso), "time": slot, "status": "Подтверждена",
    })

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔄 Записаться снова", callback_data="back"))
    bot.edit_message_text(
        f"🎉 <b>Запись подтверждена!</b>\n\n"
        f"📋 #{bid}\n"
        f"✂️ {s['name']}\n"
        f"💰 {s['price']} ₽ ({s['dur']})\n"
        f"📅 {date_display(iso)}\n"
        f"⏰ {slot}\n"
        f"👤 {name} ({uname})\n"
        f"📍 ул. Пушкина, д. 10",
        c.message.chat.id, c.message.message_id,
        parse_mode="HTML", reply_markup=kb)
    bot.answer_callback_query(c.id, "✅ Записано!")

# ── Запуск ─────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🤖 ReBook Demo Bot запущен!")
    bot.infinity_polling()
