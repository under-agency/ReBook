"""Расчёт свободных окон: чистые функции, время — только aware-UTC на входе/выходе.

Формат work_hours: {"mon": ["10:00","20:00"], ...} — один интервал,
либо {"mon": [["10:00","14:00"], ["15:00","20:00"]]} — с перерывами.
Отсутствующий/пустой день = выходной.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _day_ranges(hours: dict, day: date) -> list[tuple[time, time]]:
    entry = (hours or {}).get(DAY_KEYS[day.weekday()])
    if not entry:
        return []
    if isinstance(entry[0], str):
        entry = [entry]
    out = []
    for rng in entry:
        h1, m1 = map(int, rng[0].split(":"))
        h2, m2 = map(int, rng[1].split(":"))
        out.append((time(h1, m1), time(h2, m2)))
    return out


def overlaps(a_start: datetime, a_dur_min: int, b_start: datetime, b_dur_min: int) -> bool:
    return a_start < b_start + timedelta(minutes=b_dur_min) and b_start < a_start + timedelta(minutes=a_dur_min)


def free_slots(
    *,
    work_hours: dict,
    staff_hours: dict | None,
    duration_min: int,
    day: date,
    tz: ZoneInfo,
    busy: list[tuple[datetime, int]],  # [(starts_at UTC, duration_min), ...]
    now: datetime,                     # aware UTC
    step_min: int = 30,
) -> list[datetime]:
    """Свободные начала слотов на дату (aware UTC, по возрастанию)."""
    hours = staff_hours if staff_hours else work_hours
    result: list[datetime] = []
    for open_t, close_t in _day_ranges(hours, day):
        start_local = datetime.combine(day, open_t, tzinfo=tz)
        close_local = datetime.combine(day, close_t, tzinfo=tz)
        cur = start_local
        while cur + timedelta(minutes=duration_min) <= close_local:
            cur_utc = cur.astimezone(timezone.utc)
            if cur_utc >= now and not any(
                overlaps(cur_utc, duration_min, b_start, b_dur) for b_start, b_dur in busy
            ):
                result.append(cur_utc)
            cur += timedelta(minutes=step_min)
    return result


def within_work_hours(
    *, work_hours: dict, staff_hours: dict | None,
    starts_at: datetime, duration_min: int, tz: ZoneInfo,
) -> bool:
    """Визит целиком внутри рабочих часов (для валидации ручной записи)."""
    local = starts_at.astimezone(tz)
    end_local = local + timedelta(minutes=duration_min)
    hours = staff_hours if staff_hours else work_hours
    for open_t, close_t in _day_ranges(hours, local.date()):
        rng_start = datetime.combine(local.date(), open_t, tzinfo=tz)
        rng_end = datetime.combine(local.date(), close_t, tzinfo=tz)
        if local >= rng_start and end_local <= rng_end:
            return True
    return False
