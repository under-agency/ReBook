from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.services.slots import free_slots, within_work_hours

TZ = ZoneInfo("Europe/Moscow")
HOURS = {"mon": ["10:00", "20:00"], "tue": ["10:00", "14:00"]}
MONDAY = date(2026, 9, 7)
TUESDAY = date(2026, 9, 8)
SUNDAY = date(2026, 9, 6)
EARLY = datetime(2026, 9, 1, tzinfo=timezone.utc)  # «сейчас» задолго до дня


def _slots(**kw):
    defaults = dict(work_hours=HOURS, staff_hours=None, duration_min=60,
                    day=MONDAY, tz=TZ, busy=[], now=EARLY, step_min=30)
    defaults.update(kw)
    return free_slots(**defaults)


def _local(slots):
    return [s.astimezone(TZ).strftime("%H:%M") for s in slots]


def test_open_day_produces_slots_within_hours():
    labels = _local(_slots())
    assert labels[0] == "10:00"
    # услуга 60 мин: последний старт 19:00, чтобы уложиться до 20:00
    assert labels[-1] == "19:00"


def test_service_must_fit_before_closing():
    labels = _local(_slots(day=TUESDAY, duration_min=120))
    # 10:00–14:00, услуга 2 часа → старты только 10:00, 11:00, 11:30, 12:00
    assert labels[-1] == "12:00"


def test_day_off_is_empty():
    assert _slots(day=SUNDAY) == []


def test_busy_slot_excluded():
    busy_start = datetime(2026, 9, 7, 12, 0, tzinfo=TZ).astimezone(timezone.utc)
    labels = _local(_slots(busy=[(busy_start, 60)]))
    # занято 12:00–13:00 услугой; старты 11:30, 12:00, 12:30 пересекаются
    assert "12:00" not in labels and "11:30" not in labels and "12:30" not in labels
    assert "11:00" in labels and "13:00" in labels


def test_past_time_cut_by_now():
    now = datetime(2026, 9, 7, 15, 10, tzinfo=TZ).astimezone(timezone.utc)
    labels = _local(_slots(now=now))
    assert labels[0] == "15:30"


def test_staff_hours_override_salon_hours():
    staff_hours = {"mon": ["12:00", "16:00"]}
    labels = _local(_slots(staff_hours=staff_hours))
    assert labels[0] == "12:00" and labels[-1] == "15:00"


def test_hours_with_break():
    hours = {"mon": [["10:00", "13:00"], ["15:00", "18:00"]]}
    labels = _local(_slots(work_hours=hours))
    assert "12:00" in labels and "15:00" in labels
    assert "13:00" not in labels and "14:30" not in labels


def test_within_work_hours():
    ok = datetime(2026, 9, 7, 11, 0, tzinfo=TZ)
    late = datetime(2026, 9, 7, 19, 30, tzinfo=TZ)
    assert within_work_hours(work_hours=HOURS, staff_hours=None,
                             starts_at=ok, duration_min=60, tz=TZ)
    assert not within_work_hours(work_hours=HOURS, staff_hours=None,
                                 starts_at=late, duration_min=60, tz=TZ)
