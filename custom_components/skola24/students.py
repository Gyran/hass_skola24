"""Child matching and timetable shapes."""

from dataclasses import dataclass


@dataclass
class School:
    guid: str
    name: str


@dataclass
class Student:
    guid: str
    name: str
    preschool_unit_guid: str
    preschool_name: str | None = None


@dataclass
class Child:
    name: str
    school: str


@dataclass(frozen=True)
class ClockSpan:
    start: str
    end: str


@dataclass
class DayTime:
    start: str | None
    stop: str | None
    number: int | None = None


def match_child[T](students: list[T], query: str, name_of) -> T:
    needle = query.strip().lower()
    exact = [s for s in students if name_of(s).lower() == needle]
    if len(exact) == 1:
        return exact[0]
    starts = [s for s in students if name_of(s).lower().startswith(needle)]
    if len(starts) == 1:
        return starts[0]
    contains = [s for s in students if needle in name_of(s).lower()]
    names = ", ".join(name_of(s) for s in students)
    if len(contains) == 1:
        return contains[0]
    if len(contains) > 1 or len(starts) > 1:
        raise ValueError(f'Child name "{query}" is ambiguous. Matches: {names}')
    raise ValueError(f'No child matching "{query}". Known: {names}')


def match_named[T](students: list[T], query: str) -> T:
    return match_child(students, query, lambda s: s.name)


def school_for_student(student: Student, schools: list[School]) -> School:
    if len(schools) == 1:
        return schools[0]
    for school in schools:
        if student.preschool_name and school.name == student.preschool_name:
            return school
    return schools[0]


def clock_spans(times: list[DayTime] | None) -> list[ClockSpan]:
    spans: list[ClockSpan] = []
    for item in times or []:
        if item.start and item.stop:
            spans.append(ClockSpan(item.start[:5], item.stop[:5]))
    return spans
