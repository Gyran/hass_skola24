from custom_components.skola24.api import Lesson, current_lesson, lessons_on


def _l(day, start, end, title):
    return Lesson(day=day, weekday="", start=start, end=end, title=title, details=[])


LESSONS = [_l(5, "08:15", "09:25", "SV"), _l(5, "10:00", "10:55", "SO"), _l(4, "08:00", "09:00", "X")]


def test_lessons_on_picks_weekday():
    assert [l.title for l in lessons_on(LESSONS, "2026-11-20")] == ["SV", "SO"]


def test_current_and_next():
    day = lessons_on(LESSONS, "2026-11-20")
    assert current_lesson(day, "08:15")[0].title == "SV"
    assert current_lesson(day, "09:25") == (None, day[1])
    assert current_lesson(day, "11:00") == (None, None)

