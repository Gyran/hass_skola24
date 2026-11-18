import pytest

from custom_components.skola24.students import (
    School,
    Student,
    match_named,
    school_for_student,
)


def test_match_exact_case_insensitive():
    kids = [type("K", (), {"name": "Alva Andersson"})(), type("K", (), {"name": "Elsa Eriksson"})()]
    assert match_named(kids, "alva andersson").name == "Alva Andersson"


def test_match_unique_prefix():
    kids = [type("K", (), {"name": "Alva Andersson"})(), type("K", (), {"name": "Elsa Eriksson"})()]
    assert match_named(kids, "Alva").name == "Alva Andersson"


def test_match_ambiguous_prefix():
    kids = [type("K", (), {"name": "Alva A"})(), type("K", (), {"name": "Alva B"})()]
    with pytest.raises(ValueError, match="ambiguous"):
        match_named(kids, "Alva")


def test_match_unknown():
    kids = [type("K", (), {"name": "Alva Andersson"})()]
    with pytest.raises(ValueError, match="No child matching"):
        match_named(kids, "Nisse")


def test_school_matches_preschool_name():
    schools = [School("a", "Förskola A"), School("b", "Förskola B")]
    student = Student("s", "Alva", "u", "Förskola B")
    assert school_for_student(student, schools).guid == "b"


def test_school_falls_back_to_first():
    schools = [School("a", "Förskola A"), School("b", "Förskola B")]
    student = Student("s", "Alva", "u")
    assert school_for_student(student, schools).guid == "a"
