"""Slot assignment logic: 7 AM / 9 PM Pacific, converted to UTC RFC 3339."""

from datetime import datetime, timedelta

import pytz


def generate_slots(
    start_date: datetime,
    count: int,
    schedule_times: list[str],  # ["07:00", "21:00"]
    timezone: str,
) -> list[str]:
    """
    Return `count` publish-time strings in UTC RFC 3339 format,
    starting from start_date, cycling through schedule_times.
    """
    tz = pytz.timezone(timezone)
    utc = pytz.utc
    slots = []
    day = start_date.date() if hasattr(start_date, "date") else start_date

    while len(slots) < count:
        for slot_str in schedule_times:
            if len(slots) >= count:
                break
            h, m = map(int, slot_str.split(":"))
            naive_dt = datetime(day.year, day.month, day.day, h, m, 0)
            local_dt = tz.localize(naive_dt, is_dst=None)
            utc_dt = local_dt.astimezone(utc)
            slots.append(utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
        day += timedelta(days=1)

    return slots


def format_schedule_summary(
    video_titles: list[str],
    slots: list[str],
    timezone: str,
) -> str:
    """Return a human-readable publish schedule string for clipboard copy."""
    tz = pytz.timezone(timezone)
    utc = pytz.utc
    lines = []
    for title, slot_utc in zip(video_titles, slots):
        utc_dt = utc.localize(datetime.strptime(slot_utc, "%Y-%m-%dT%H:%M:%SZ"))
        local_dt = utc_dt.astimezone(tz)
        lines.append(f"{local_dt.strftime('%b %d %Y %I:%M %p %Z')} — {title}")
    return "\n".join(lines)
