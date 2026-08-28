#!/usr/bin/env python3
"""
Test & Validation script for ReBook Demo Booking Workflow (AI-5)
Validates n8n JSON schema, connections, parameters and simulates conversational flow.
"""

import json
import os
import sys
from datetime import datetime

def test_workflow_json_structure():
    workflow_path = os.path.join(os.path.dirname(__file__), "..", "workflows", "demo-booking.json")
    print(f"[*] Validating workflow file: {workflow_path}")
    
    assert os.path.exists(workflow_path), f"File not found: {workflow_path}"
    
    with open(workflow_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert "nodes" in data, "Workflow must contain 'nodes'"
    assert "connections" in data, "Workflow must contain 'connections'"
    
    node_names = [n.get("name") for n in data["nodes"]]
    print(f"[*] Found {len(node_names)} nodes: {node_names}")
    
    required_nodes = [
        "Telegram Trigger",
        "Process Bot Logic",
        "Is Booking Confirmed?",
        "Save to Google Sheets",
        "Send Confirmation Telegram",
        "Send Interactive Telegram"
    ]
    
    for req in required_nodes:
        assert req in node_names, f"Missing required node: {req}"
    
    # Check connections graph
    connections = data["connections"]
    assert "Telegram Trigger" in connections, "Missing Telegram Trigger connection"
    assert "Process Bot Logic" in connections, "Missing Process Bot Logic connection"
    assert "Is Booking Confirmed?" in connections, "Missing router branching connection"
    
    print("[✓] Workflow JSON structure and node connections are valid!")
    return data

class BotSimulator:
    SERVICES = {
        'haircut': {'name': '✂️ Мужская стрижка', 'price': 1800, 'duration': '45 мин'},
        'manicure': {'name': '💅 Маникюр с покрытием', 'price': 2200, 'duration': '60 мин'},
        'autocheck': {'name': '🚗 Экспресс-ТО / Диагностика', 'price': 1500, 'duration': '30 мин'}
    }
    TIME_SLOTS = ['11:00', '14:00', '16:30', '19:00']

    @staticmethod
    def process_update(update):
        # Python mirror of the n8n JavaScript code node logic
        chat_id = None
        message_id = None
        from_user = {}
        text = ''
        callback_data = None

        if 'callback_query' in update:
            cq = update['callback_query']
            chat_id = cq['message']['chat']['id']
            message_id = cq['message']['message_id']
            from_user = cq['from']
            callback_data = cq.get('data')
        elif 'message' in update:
            msg = update['message']
            chat_id = msg['chat']['id']
            message_id = msg['message_id']
            from_user = msg['from']
            text = msg.get('text', '')

        first_name = from_user.get('first_name', 'Гость')
        username = f"@{from_user['username']}" if from_user.get('username') else 'Не указан'
        user_id = str(from_user.get('id', ''))

        response_text = ''
        reply_markup = {}
        is_booking_confirmed = False
        booking_data = None

        if callback_data:
            parts = callback_data.split('|')
            action = parts[0]

            if action == 'srv':
                srv_key = parts[1]
                service = BotSimulator.SERVICES.get(srv_key, {'name': 'Услуга', 'price': 0})
                response_text = f"Вы выбрали: <b>{service['name']}</b> ({service['price']} ₽)\n\n📅 <b>Выберите удобный день:</b>"
                inline_keyboard = [
                    [{'text': 'Сегодня (29 авг)', 'callback_data': f"dt|{srv_key}|2026-08-29"}],
                    [{'text': 'Завтра (30 авг)', 'callback_data': f"dt|{srv_key}|2026-08-30"}],
                    [{'text': 'Вс (31 авг)', 'callback_data': f"dt|{srv_key}|2026-08-31"}]
                ]
                inline_keyboard.append([{'text': '« Назад к услугам', 'callback_data': 'start'}])
                reply_markup = {'inline_keyboard': inline_keyboard}

            elif action == 'dt':
                srv_key = parts[1]
                date_iso = parts[2]
                date_display = "Завтра, 30 авг" if date_iso == "2026-08-30" else date_iso
                service = BotSimulator.SERVICES.get(srv_key, {'name': 'Услуга'})
                response_text = f"Услуга: <b>{service['name']}</b>\nДата: <b>{date_display}</b>\n\n⏰ <b>Выберите свободное время:</b>"
                inline_keyboard = []
                for i in range(0, len(BotSimulator.TIME_SLOTS), 2):
                    row = [{'text': f"🕐 {BotSimulator.TIME_SLOTS[i]}", 'callback_data': f"tm|{srv_key}|{date_iso}|{BotSimulator.TIME_SLOTS[i]}"}]
                    if i + 1 < len(BotSimulator.TIME_SLOTS):
                        row.append({'text': f"🕐 {BotSimulator.TIME_SLOTS[i+1]}", 'callback_data': f"tm|{srv_key}|{date_iso}|{BotSimulator.TIME_SLOTS[i+1]}"})
                    inline_keyboard.append(row)
                inline_keyboard.append([{'text': '« Назад к выбору даты', 'callback_data': f"srv|{srv_key}"}])
                reply_markup = {'inline_keyboard': inline_keyboard}

            elif action == 'tm':
                srv_key = parts[1]
                date_iso = parts[2]
                time_slot = parts[3]
                date_display = "Завтра, 30 авг" if date_iso == "2026-08-30" else date_iso
                service = BotSimulator.SERVICES.get(srv_key, {'name': 'Услуга', 'price': 0, 'duration': '30 мин'})

                booking_id = "RB-1042"
                created_at = datetime.now().isoformat()
                is_booking_confirmed = True
                booking_data = {
                    'booking_id': booking_id,
                    'created_at': created_at,
                    'client_id': user_id,
                    'client_name': first_name,
                    'telegram_username': username,
                    'service_key': srv_key,
                    'service_name': service['name'],
                    'price': service['price'],
                    'duration': service['duration'],
                    'date_iso': date_iso,
                    'date_display': date_display,
                    'time_slot': time_slot,
                    'status': 'Подтверждена',
                    'chat_id': chat_id
                }

                response_text = (
                    f"🎉 <b>Запись успешно подтверждена!</b>\n\n"
                    f"📋 <b>Номер брони:</b> #{booking_id}\n"
                    f"✂️ <b>Услуга:</b> {service['name']}\n"
                    f"💰 <b>Стоимость:</b> {service['price']} ₽ ({service['duration']})\n"
                    f"📅 <b>Дата:</b> {date_display}\n"
                    f"⏰ <b>Время:</b> {time_slot}\n"
                    f"👤 <b>Клиент:</b> {first_name} ({username})\n"
                    f"📍 <b>Адрес:</b> ул. Пушкина, д. 10\n\n"
                    f"─────────────\n"
                    f"💡 <i>Информация для владельца бизнеса:</i>\n"
                    f"• Запись за 2 секунды занесена в таблицу расписания.\n"
                    f"• Через 1 минуту бот пришлёт проверочное напоминание с кнопками подтверждения визита."
                )
                reply_markup = {'inline_keyboard': [[{'text': '🔄 Записаться снова (Тест)', 'callback_data': 'start'}]]}
            else:
                callback_data = 'start'

        if not callback_data or callback_data == 'start':
            response_text = (
                f"👋 <b>Здравствуйте, {first_name}!</b>\n\n"
                f"Это интерактивный демо-стенд системы <b>«ReBook»</b>.\n\n"
                f"Попробуйте оформить тестовую запись за 30 секунд так, как это делают ваши реальные клиенты:\n\n"
                f"👇 <b>Выберите желаемую услугу:</b>"
            )
            reply_markup = {
                'inline_keyboard': [
                    [{'text': f"{BotSimulator.SERVICES['haircut']['name']} — {BotSimulator.SERVICES['haircut']['price']} ₽", 'callback_data': 'srv|haircut'}],
                    [{'text': f"{BotSimulator.SERVICES['manicure']['name']} — {BotSimulator.SERVICES['manicure']['price']} ₽", 'callback_data': 'srv|manicure'}],
                    [{'text': f"{BotSimulator.SERVICES['autocheck']['name']} — {BotSimulator.SERVICES['autocheck']['price']} ₽", 'callback_data': 'srv|autocheck'}]
                ]
            }

        return {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': response_text,
            'reply_markup': json.dumps(reply_markup, ensure_ascii=False),
            'parse_mode': 'HTML',
            'is_booking_confirmed': is_booking_confirmed,
            'booking_data': booking_data
        }

def test_full_conversational_simulation():
    print("[*] Starting Conversational Flow Simulation...")
    
    # 1. /start
    res1 = BotSimulator.process_update({
        'message': {
            'message_id': 1001,
            'chat': {'id': 7770001},
            'from': {'id': 7770001, 'first_name': 'Артем', 'username': 'artem_lead'},
            'text': '/start'
        }
    })
    assert 'Здравствуйте, Артем' in res1['text'], "Start step failed to greet user"
    assert not res1['is_booking_confirmed'], "Booking should not be confirmed on /start"
    print("  [✓] Step 1 (/start) -> Catalog & Welcome passed.")

    # 2. Select haircut
    res2 = BotSimulator.process_update({
        'callback_query': {
            'message': {'message_id': 1002, 'chat': {'id': 7770001}},
            'from': {'id': 7770001, 'first_name': 'Артем', 'username': 'artem_lead'},
            'data': 'srv|haircut'
        }
    })
    assert 'Мужская стрижка' in res2['text'], "Service selection step failed"
    assert 'Выберите удобный день' in res2['text']
    print("  [✓] Step 2 (srv|haircut) -> Date Picker passed.")

    # 3. Select date
    res3 = BotSimulator.process_update({
        'callback_query': {
            'message': {'message_id': 1003, 'chat': {'id': 7770001}},
            'from': {'id': 7770001, 'first_name': 'Артем', 'username': 'artem_lead'},
            'data': 'dt|haircut|2026-08-30'
        }
    })
    assert 'Выберите свободное время' in res3['text'], "Date selection step failed"
    print("  [✓] Step 3 (dt|haircut|...) -> Time Slot Picker passed.")

    # 4. Confirm slot
    res4 = BotSimulator.process_update({
        'callback_query': {
            'message': {'message_id': 1004, 'chat': {'id': 7770001}},
            'from': {'id': 7770001, 'first_name': 'Артем', 'username': 'artem_lead'},
            'data': 'tm|haircut|2026-08-30|14:00'
        }
    })
    assert res4['is_booking_confirmed'] is True, "Booking must be marked as confirmed"
    assert res4['booking_data'] is not None, "Booking data missing"
    assert res4['booking_data']['time_slot'] == '14:00'
    assert res4['booking_data']['price'] == 1800
    assert 'Запись успешно подтверждена' in res4['text']
    print("  [✓] Step 4 (tm|haircut|...|14:00) -> Final Booking Confirmation passed.")
    print("  [✓] Generated Booking Record:", json.dumps(res4['booking_data'], ensure_ascii=False))

if __name__ == "__main__":
    print("=== ReBook Demo Bot Test Suite ===")
    test_workflow_json_structure()
    test_full_conversational_simulation()
    print("=== All Tests Completed Successfully (100% Passed) ===")
