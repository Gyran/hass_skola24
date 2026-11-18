"""Skola24 calls: children, today's exception, timetable."""

from __future__ import annotations

from dataclasses import dataclass

from .client import Skola24Client
from .const import EXCEPTION_SCOPE, EXCEPTION_URL, TIMETABLE_SCOPE, VIEWER_URL
from .dates import assert_ymd, iso_week_from_ymd, today_stockholm
from .students import (
    Child,
    ClockSpan,
    DayTime,
    School,
    Student,
    clock_spans,
    match_named,
    school_for_student,
)

WEEKDAYS = ["", "måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]


@dataclass
class SaveResult:
    child: str
    date: str
    message: str
    confirmation: str


@dataclass
class TemporaryChange:
    child: str
    school: str
    date: str
    message: str | None
    exception_times: list[ClockSpan]
    ordinary_times: list[ClockSpan]


@dataclass
class Lesson:
    day: int
    weekday: str
    start: str
    end: str
    title: str
    details: list[str]


@dataclass
class Timetable:
    child: str
    school: str
    week: int
    year: int
    lessons: list[Lesson]


@dataclass
class ChildDay:
    guid: str
    name: str
    school: str
    date: str
    message: str | None
    exception_times: list[ClockSpan]
    ordinary_times: list[ClockSpan]


@dataclass
class _LoadedDay:
    student: Student
    school: School
    raw: dict


async def list_children(client: Skola24Client) -> list[Child]:
    async with client.session():
        schools, students = await _load_students(client, today_stockholm())
        return [
            Child(
                name=student.name,
                school=student.preschool_name or school_for_student(student, schools).name,
            )
            for student in students
        ]


async def today_overview(client: Skola24Client, date: str | None = None) -> list[ChildDay]:
    day = date or today_stockholm()
    assert_ymd(day)
    async with client.session():
        schools, students = await _load_students(client, day)
        found: list[ChildDay] = []
        for student in students:
            school = school_for_student(student, schools)
            loaded = await _load_day(client, student, school, day)
            comment, exception_times, ordinary_times = _times_from_raw(loaded.raw)
            found.append(
                ChildDay(
                    guid=student.guid,
                    name=student.name,
                    school=student.preschool_name or school.name,
                    date=day,
                    message=comment,
                    exception_times=exception_times,
                    ordinary_times=ordinary_times,
                )
            )
        return found


async def get_temporary_change(
    client: Skola24Client,
    child: str,
    date: str | None = None,
) -> TemporaryChange:
    day = date or today_stockholm()
    assert_ymd(day)
    async with client.session():
        loaded = await _load_exception_day(client, child, day)
        comment, exception_times, ordinary_times = _times_from_raw(loaded.raw)
        return TemporaryChange(
            child=loaded.student.name,
            school=loaded.student.preschool_name or loaded.school.name,
            date=day,
            message=comment,
            exception_times=exception_times,
            ordinary_times=ordinary_times,
        )


async def set_temporary_change_message(
    client: Skola24Client,
    child: str,
    message: str,
    date: str | None = None,
) -> SaveResult:
    text = message.strip()
    if not text:
        raise ValueError("Empty message rejected")
    day = date or today_stockholm()
    assert_ymd(day)
    async with client.session():
        loaded = await _load_exception_day(client, child, day)
        timetable = loaded.raw.get("timetable") or {}
        times = [
            item
            for item in timetable.get("exceptionTimes") or []
            if isinstance(item, dict) and item.get("start") and item.get("stop")
        ]
        saved = await client.authed_api(
            "/save/preschool/schedule/exception/day",
            {
                "studentGuid": loaded.student.guid,
                "schoolGuid": loaded.school.guid,
                "date": f"{day}T00:00:00",
                "comment": text,
                "times": times,
                "isAffectingExpectedPresence": len(times) > 0,
            },
            scope=EXCEPTION_SCOPE,
            referer=EXCEPTION_URL,
        )
        if not isinstance(saved, dict) or not saved.get("success"):
            raise RuntimeError("Skola24 did not confirm save")
        return SaveResult(
            child=loaded.student.name,
            date=day,
            message=text,
            confirmation="Tillfällig ändring sparad.",
        )


async def get_timetable(
    client: Skola24Client,
    *,
    child: str | None = None,
    date: str | None = None,
    week: int | None = None,
    year: int | None = None,
) -> Timetable:
    host = client.credentials.host
    if date:
        assert_ymd(date)
        week, year = iso_week_from_ymd(date)
    elif week is None or year is None:
        current_week, current_year = iso_week_from_ymd(today_stockholm())
        week = current_week if week is None else week
        year = current_year if year is None else year
    if week is None or year is None or week < 1 or week > 53:
        raise ValueError("week must be 1-53")

    async with client.session():
        personal = await client.authed_api(
            "/services/skola24/get/personal/timetables",
            {"getPersonalTimetablesRequest": {"hostName": host}},
            scope=TIMETABLE_SCOPE,
            referer=VIEWER_URL,
        )
        response = personal.get("getPersonalTimetablesResponse") or {}
        people = [
            *(response.get("childrenTimetables") or []),
            *(response.get("studentTimetables") or []),
        ]
        if not people:
            keys = ", ".join(personal.keys()) if isinstance(personal, dict) else ""
            raise RuntimeError(f"No timetables on this account. data keys: {keys}")
        person = _match_timetable_child(people, child)

        years = await client.authed_api(
            "/get/active/school/years",
            {"hostName": host, "checkSchoolYearsFeatures": False},
            scope=TIMETABLE_SCOPE,
            referer=VIEWER_URL,
        )
        active = years.get("activeSchoolYears") or []
        school_year = active[0].get("guid") if active else None
        if not school_year:
            raise RuntimeError("No active school year")

        key_data = await client.authed_api(
            "/get/timetable/render/key",
            None,
            scope=TIMETABLE_SCOPE,
            referer=VIEWER_URL,
        )
        rendered = await client.authed_api(
            "/render/timetable",
            {
                "renderKey": key_data["key"],
                "host": host,
                "unitGuid": person["unitGuid"],
                "schoolYear": school_year,
                "startDate": None,
                "endDate": None,
                "scheduleDay": 0,
                "blackAndWhite": False,
                "width": 1078,
                "height": 550,
                "selectionType": 5,
                "selection": person["personGuid"],
                "showHeader": False,
                "periodText": "",
                "week": week,
                "year": year,
                "privateFreeTextMode": None,
                "privateSelectionMode": True,
                "customerKey": "",
                "personalTimetable": True,
            },
            scope=TIMETABLE_SCOPE,
            referer=VIEWER_URL,
        )
        lessons: list[Lesson] = []
        for lesson in rendered.get("lessonInfo") or []:
            texts = [t.strip() for t in lesson.get("texts") or [] if str(t).strip()]
            day_number = int(lesson.get("dayOfWeekNumber") or 0)
            lessons.append(
                Lesson(
                    day=day_number,
                    weekday=WEEKDAYS[day_number] if 0 < day_number < len(WEEKDAYS) else str(day_number),
                    start=str(lesson.get("timeStart") or "")[:5],
                    end=str(lesson.get("timeEnd") or "")[:5],
                    title=texts[0] if texts else "",
                    details=texts[1:],
                )
            )
        lessons.sort(key=lambda item: (item.day, item.start))
        full_name = f"{person.get('firstName', '')} {person.get('lastName', '')}".strip()
        return Timetable(
            child=full_name,
            school=str(person.get("schoolID") or ""),
            week=week,
            year=year,
            lessons=lessons,
        )


async def _load_students(client: Skola24Client, date: str) -> tuple[list[School], list[Student]]:
    preschool = await client.authed_api(
        "/get/preschools",
        None,
        scope=EXCEPTION_SCOPE,
        referer=EXCEPTION_URL,
    )
    schools = [
        School(guid=item["guid"], name=item.get("name") or "")
        for item in preschool.get("schools") or []
        if item.get("guid")
    ]
    if not schools:
        keys = ", ".join(preschool.keys()) if isinstance(preschool, dict) else ""
        raise RuntimeError(
            f"No preschool/school on this account. data keys: {keys} schools={len(schools)}"
        )
    groups = await client.authed_api(
        "/get/groups/per/preschools/with/students",
        {
            "schoolGuids": [school.guid for school in schools],
            "groupDates": {"start": date, "end": date},
            "groupGuids": [],
            "includeStudents": True,
            "includeArchived": False,
            "dateFrom": date,
            "dateTo": date,
        },
        scope=EXCEPTION_SCOPE,
        referer=EXCEPTION_URL,
    )
    raw_students = [
        *(groups.get("privateStudents") or []),
        *(groups.get("staffStudents") or []),
    ]
    students = [_student(item) for item in raw_students if item.get("guid") and item.get("name")]
    if not students:
        raise RuntimeError("No children found on this account")
    return schools, students


async def _load_exception_day(client: Skola24Client, child: str, date: str) -> _LoadedDay:
    schools, students = await _load_students(client, date)
    student = _match_student(students, child)
    school = school_for_student(student, schools)
    raw = await _load_day(client, student, school, date)
    return _LoadedDay(student=student, school=school, raw=raw)


async def _load_day(client: Skola24Client, student: Student, school: School, date: str) -> dict:
    data = await client.authed_api(
        "/get/timetable/day/with/timeframes/day",
        {
            "studentPersonGuid": student.guid,
            "preschoolUnitGuid": student.preschool_unit_guid,
            "schoolGuid": school.guid,
            "dateFrom": date,
        },
        scope=EXCEPTION_SCOPE,
        referer=EXCEPTION_URL,
    )
    if not isinstance(data, dict):
        raise RuntimeError("Skola24 day payload was not an object")
    return data


def _student(item: dict) -> Student:
    return Student(
        guid=item["guid"],
        name=item["name"],
        preschool_unit_guid=item.get("preschoolUnitGuid") or "",
        preschool_name=item.get("preschoolName"),
    )


def _match_student(students: list[Student], query: str) -> Student:
    for student in students:
        if student.guid == query:
            return student
    return match_named(students, query)


def _times_from_raw(raw: dict) -> tuple[str | None, list[ClockSpan], list[ClockSpan]]:
    timetable = raw.get("timetable") or {}
    comment = (timetable.get("exceptionDayComment") or "").strip() or None
    return (
        comment,
        clock_spans(_day_times(timetable.get("exceptionTimes"))),
        clock_spans(_day_times(timetable.get("timetableTimes"))),
    )


def _day_times(raw: object) -> list[DayTime]:
    if not isinstance(raw, list):
        return []
    times: list[DayTime] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        times.append(
            DayTime(
                start=item.get("start"),
                stop=item.get("stop"),
                number=item.get("number"),
            )
        )
    return times


def _match_timetable_child(children: list[dict], query: str | None) -> dict:
    named = []
    for child in children:
        name = f"{child.get('firstName', '')} {child.get('lastName', '')}".strip()
        named.append(type("Person", (), {"name": name, "raw": child})())
    if not query:
        if len(named) == 1:
            return named[0].raw
        known = ", ".join(person.name for person in named)
        raise ValueError(f"child required. Known: {known}")
    return match_named(named, query).raw
