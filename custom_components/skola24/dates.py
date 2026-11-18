"""Stockholm dates and ISO weeks."""

from datetime import datetime
from zoneinfo import ZoneInfo

_STOCKHOLM = ZoneInfo("Europe/Stockholm")


def today_stockholm(now: datetime | None = None) -> str:
    moment = now.astimezone(_STOCKHOLM) if now else datetime.now(_STOCKHOLM)
    return moment.strftime("%Y-%m-%d")


def iso_week_from_ymd(ymd: str) -> tuple[int, int]:
    year_s, month_s, day_s = ymd.split("-")
    date = datetime(int(year_s), int(month_s), int(day_s))
    year, week, _ = date.isocalendar()
    return week, year


def service_date(raw: object) -> str | None:
    """Empty means today. A date object or YYYY-MM-DD is that day."""
    if raw in (None, ""):
        return None
    if hasattr(raw, "isoformat"):
        text = raw.isoformat()[:10]
    else:
        text = str(raw).strip()
    assert_ymd(text)
    return text


def assert_ymd(date: str) -> None:
    if len(date) != 10 or date[4] != "-" or date[7] != "-":
        raise ValueError("date must be YYYY-MM-DD")
    datetime.strptime(date, "%Y-%m-%d")
