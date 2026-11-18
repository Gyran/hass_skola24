"""Login form parsing and session checks. No network."""

import html
import re
from dataclasses import dataclass


class AuthError(Exception):
    """Skola24 rejected the username or password."""


class ApiError(Exception):
    """Skola24 answered with something other than the data we asked for."""


@dataclass
class Credentials:
    username: str
    password: str
    host: str


def login_url(host: str) -> str:
    return f"https://{host}/Applications/Authentication/login.aspx?host={host}"


def looks_like_login_page(page: str) -> bool:
    return "LoginUC_UserNameTB" in page or "LoginUC$UserNameTB" in page


def looks_like_login_url(url: str) -> bool:
    return re.search(r"login\.aspx|/authentication/login", url, re.I) is not None


def parse_form_fields(page: str, host: str) -> dict[str, str]:
    fields = _parse_inputs(page)
    for block in re.finditer(r"<select\b([^>]*)>([\s\S]*?)</select>", page, re.I):
        name_match = re.search(r'name\s*=\s*"([^"]+)"', block.group(1), re.I)
        if not name_match:
            continue
        name = name_match.group(1)
        body = block.group(2)
        selected = re.search(
            r'<option\b[^>]*selected(?:\s*=\s*(?:"selected"|\'selected\'|selected))[^>]*value\s*=\s*"([^"]*)"',
            body,
            re.I,
        ) or re.search(
            r'<option\b[^>]*value\s*=\s*"([^"]*)"[^>]*selected',
            body,
            re.I,
        )
        if selected:
            fields[name] = html.unescape(selected.group(1))
            continue
        for opt in re.finditer(
            r'<option\b[^>]*value\s*=\s*"([^"]*)"[^>]*>([\s\S]*?)</option>',
            body,
            re.I,
        ):
            if html.unescape(opt.group(2)).strip() == host:
                fields[name] = html.unescape(opt.group(1))
                break
    return fields


def payload_looks_logged_out(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    schools = data.get("schools")
    if isinstance(schools, list) and len(schools) == 0:
        return True
    personal = data.get("getPersonalTimetablesResponse")
    if isinstance(personal, dict):
        children = personal.get("childrenTimetables") or []
        students = personal.get("studentTimetables") or []
        if len(children) + len(students) == 0:
            return True
    return False


def session_dead(
    status: int,
    text: str,
    url: str,
    parsed: dict | None,
) -> bool:
    if status in (401, 403):
        return True
    if looks_like_login_page(text) or looks_like_login_url(url):
        return True
    if parsed and parsed.get("needSessionRefresh"):
        return True
    err = "" if not parsed or parsed.get("error") is None else str(parsed["error"])
    if re.search(r"session|unauthorized|not logged|inlogg", err, re.I):
        return True
    if parsed and payload_looks_logged_out(parsed.get("data")):
        return True
    return False


def _parse_inputs(page: str) -> dict[str, str]:
    inputs: dict[str, str] = {}
    for tag in re.finditer(r"<input\b[^>]*>", page, re.I):
        attrs: dict[str, str] = {}
        for match in re.finditer(r'([a-zA-Z:_-]+)\s*=\s*"([^"]*)"', tag.group(0)):
            attrs[match.group(1).lower()] = match.group(2)
        for match in re.finditer(r"([a-zA-Z:_-]+)\s*=\s*'([^']*)'", tag.group(0)):
            attrs[match.group(1).lower()] = match.group(2)
        name = attrs.get("name")
        if not name:
            continue
        inputs[name] = html.unescape(attrs.get("value", ""))
    return inputs
