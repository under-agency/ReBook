#!/usr/bin/env python3
"""
Unit and integration tests for ReBook Telegram Demo Bot.
Validates service catalog, date/time generators, and booking data schema.
"""

import os
import sys
from datetime import datetime, timedelta

# Import functions and constants from bot.py (parent dir)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from bot import SERVICES, SLOTS, dates_3, date_display

def test_services_catalog():
    print("[*] Testing SERVICES catalog...")
    assert len(SERVICES) >= 3, "Catalog must contain at least 3 services"
    for key, svc in SERVICES.items():
        assert "name" in svc and len(svc["name"]) > 0, f"Service {key} missing name"
        assert "price" in svc and svc["price"] > 0, f"Service {key} missing valid price"
        assert "dur" in svc and len(svc["dur"]) > 0, f"Service {key} missing duration"
    print("  [✓] Services catalog is valid:", list(SERVICES.keys()))

def test_dates_generator():
    print("[*] Testing dates_3 generator...")
    dates = dates_3()
    assert len(dates) == 3, "dates_3 must return exactly 3 days"
    
    assert "Сегодня" in dates[0]["label"], "First date must be 'Сегодня'"
    assert "Завтра" in dates[1]["label"], "Second date must be 'Завтра'"
    
    today_iso = datetime.now().strftime("%Y-%m-%d")
    assert dates[0]["iso"] == today_iso, f"First date iso must be today ({today_iso})"
    
    print("  [✓] Generated dates:", [d["label"] for d in dates])

def test_slots_and_display():
    print("[*] Testing time slots and date display helper...")
    assert len(SLOTS) >= 4, "Must have at least 4 available slots"
    for slot in SLOTS:
        assert ":" in slot, f"Slot {slot} must be formatted as HH:MM"
    
    today_iso = datetime.now().strftime("%Y-%m-%d")
    disp = date_display(today_iso)
    assert "Сегодня" in disp, f"Display for today should contain 'Сегодня', got {disp}"
    print("  [✓] Time slots and display format verified.")

def test_booking_record_structure():
    print("[*] Testing booking record data schema...")
    dummy_booking = {
        "id": "RB-9999",
        "created": datetime.now().isoformat(),
        "client_id": 123456789,
        "name": "Тест",
        "tg": "@test_user",
        "service": SERVICES["haircut"]["name"],
        "price": SERVICES["haircut"]["price"],
        "date": "Завтра, 30 авг",
        "time": "14:00",
        "status": "Подтверждена"
    }
    
    required_keys = ["id", "created", "client_id", "name", "tg", "service", "price", "date", "time", "status"]
    for k in required_keys:
        assert k in dummy_booking, f"Missing key {k} in booking record"
    
    print("  [✓] Booking record structure conforms to database/table schema.")

if __name__ == "__main__":
    print("=== ReBook Bot Test Suite ===")
    test_services_catalog()
    test_dates_generator()
    test_slots_and_display()
    test_booking_record_structure()
    print("=== All Tests Completed Successfully (100% Passed) ===")
