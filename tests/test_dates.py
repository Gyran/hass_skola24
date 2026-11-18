from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.skola24.dates import assert_ymd, iso_week_from_ymd, today_stockholm


def test_iso_week_thursday_in_january():
    assert iso_week_from_ymd("2026-01-08") == (2, 2026)


def test_iso_week_year_end():
    assert iso_week_from_ymd("2026-12-31") == (53, 2026)


def test_assert_ymd_accepts_dashed_date():
    assert_ymd("2026-09-09")


def test_assert_ymd_rejects_slashes():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        assert_ymd("2026/09/09")


def test_service_date_defaults_and_accepts_a_day():
    from datetime import date

    from custom_components.skola24.dates import service_date

    assert service_date(None) is None
    assert service_date("") is None
    assert service_date("2026-11-16") == "2026-11-16"
    assert service_date(date(2026, 11, 16)) == "2026-11-16"


def test_today_uses_stockholm():
    moment = datetime(2026, 1, 1, 0, 30, tzinfo=ZoneInfo("UTC"))
    assert today_stockholm(moment) == "2026-01-01"
