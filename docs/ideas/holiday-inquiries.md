# Idea: unanswered holiday inquiries (frågor om lov och studiedagar)

Parked on 2026-11-20. Nothing here is in the integration. Pick it up when there is a real inquiry to answer, so the sensor can be tested against live data.

## What it is

Fritids sends a question per group about a lov or studiedag (STUDIEDAG, HÖSTLOV, JULLOV). The guardian answers per child and day on
`https://web.skola24.se/portal/start/timetable/reply-to-holiday-inquiry`.

The idea: one sensor per child counting inquiries that still need an answer, with the deadlines as attributes, so an automation can nag before the deadline.

## How to read it (verified against a real account)

- Call `POST /api/services/skola24/get/preschool/holiday/inquiries` with scope `83f01def-65e5-4cc3-93d7-d6b769949e96` and referer `.../reply-to-holiday-inquiry`.
- Body: `{"getPreschoolHolidayInquiriesRequest": {"dateFrom": "YYYY-MM-DD", "dateTo": "<a year later>", "schoolGuid": "<id>", "queryFromInquiryDate": false}}`
- Response: `data.getPreschoolHolidayInquiriesResponse.inquiries[]` with `inquiryName`, `groupName`, `timeTableStart/End`, `responseStart/End`, `remainingResponses`, `remainingPrivateResponses`, `isPrivate`, `infoText`.
- **School ids are different in each scope.** The id from `/get/preschools` under the exception scope (`47b9...`) or the timetable scope returns an empty list here. Call `/get/preschools` with the inquiry scope and use that id.
- Group to child: the child's record from `/get/groups/per/preschools/with/students` has `preschoolUnitName`, which equals the inquiry's `groupName` (a name like a class or avdelning).

## Things not yet known

- Which field means "I have not answered". The best guess is `remainingPrivateResponses > 0`. `remainingResponses` looks like the whole group's count (24 and 17 for the same inquiry in two groups). With no open inquiry to answer, every `remainingPrivateResponses` was 0, so the guess is untested.
- Past inquiries stay in the list (a deadline in September was still returned in November), so filter on `responseEnd >= today`.
- Whether `remainingPrivateResponses` counts days or children.

To settle it: when a real inquiry arrives, read this endpoint before and after answering one child and see which number moves.

## Sketch that was working

`api.py`:

```python
def open_inquiries(raw: list[dict], today: str) -> list[HolidayInquiry]:
    """Inquiries that can still be answered, soonest deadline first."""
    found = [
        HolidayInquiry(
            name=str(item.get("inquiryName") or ""),
            group=str(item.get("groupName") or ""),
            start=str(item.get("timeTableStart") or "")[:10],
            end=str(item.get("timeTableEnd") or "")[:10],
            deadline=str(item.get("responseEnd") or "")[:10],
            unanswered=int(item.get("remainingPrivateResponses") or 0),
            text=str(item.get("infoText") or ""),
        )
        for item in raw
        if isinstance(item, dict)
    ]
    return sorted(
        (inquiry for inquiry in found if inquiry.deadline >= today),
        key=lambda inquiry: (inquiry.deadline, inquiry.name),
    )


async def get_holiday_inquiries(client: Skola24Client, today: str | None = None) -> list[HolidayInquiry]:
    day = today or today_stockholm()
    assert_ymd(day)
    end = datetime.strptime(day, "%Y-%m-%d").replace(year=datetime.strptime(day, "%Y-%m-%d").year + 1)
    async with client.session():
        # School ids differ per scope, so ask this scope for its own.
        preschools = await client.authed_api(
            "/get/preschools", None, scope=INQUIRY_SCOPE, referer=INQUIRY_URL
        )
        raw: list[dict] = []
        for school in preschools.get("schools") or []:
            if not school.get("guid"):
                continue
            data = await client.authed_api(
                "/services/skola24/get/preschool/holiday/inquiries",
                {
                    "getPreschoolHolidayInquiriesRequest": {
                        "dateFrom": day,
                        "dateTo": end.strftime("%Y-%m-%d"),
                        "schoolGuid": school["guid"],
                        "queryFromInquiryDate": False,
                    }
                },
                scope=INQUIRY_SCOPE,
                referer=INQUIRY_URL,
            )
            response = data.get("getPreschoolHolidayInquiriesResponse") or {}
            raw.extend(response.get("inquiries") or [])
    return open_inquiries(raw, day)
```

`sensor.py` (state is the count of inquiries with `unanswered > 0`, attributes list all open ones):

```python
class InquirySensor(_ChildSensor):
    """Holiday and study-day questions still waiting for an answer."""

    _attr_translation_key = "holiday_inquiries"
    _attr_icon = "mdi:calendar-question"

    def __init__(self, coordinator: Skola24Coordinator, guid: str, name: str) -> None:
        super().__init__(coordinator, guid, name)
        self._attr_unique_id = f"{guid}_holiday_inquiries"

    def _unanswered(self):
        day = self._day()
        return [i for i in day.holiday_inquiries if i.unanswered > 0] if day else []

    @property
    def native_value(self) -> int | None:
        return None if self._day() is None else len(self._unanswered())

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        day = self._day()
        unanswered = self._unanswered()
        return {
            "next_deadline": unanswered[0].deadline if unanswered else None,
            "inquiries": [
                {
                    "name": item.name,
                    "from": item.start,
                    "to": item.end,
                    "deadline": item.deadline,
                    "unanswered": item.unanswered,
                    "text": item.text,
                }
                for item in (day.holiday_inquiries if day else [])
            ],
        }
```

Wiring: a `get_holiday_inquiries()` call in the coordinator (failure must not break the other sensors), `group` on `Student` and `ChildDay` from `preschoolUnitName`, an `INQUIRY_SCOPE` and `INQUIRY_URL` in `const.py`, and a `holiday_inquiries` entity name in both translation files.

## Related find: attendance status

The per-child record from `/get/groups/per/preschools/with/students` also has `studentAttendanceStatus` (0 for both children at 14:00 on a school day), `holidayInquiryStatus`, `hasUnconfirmedPlannedAbsence`, `isOnLeave`, `hasPlannedAbsenceTimesOnDay` and `hasAbsenceWholeDay`. `studentAttendanceStatus` may be the check-in state from the mobile app. Compare it with the app while a child is checked in, then map the numbers.
