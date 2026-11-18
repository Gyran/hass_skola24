"""HTTP session with a cookie jar on disk.

File I/O goes through run_io so Home Assistant can push it to an executor.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .auth import (
    ApiError,
    AuthError,
    Credentials,
    looks_like_login_page,
    looks_like_login_url,
    login_url,
    parse_form_fields,
    session_dead,
)
from .const import API_BASE, PORTAL, USER_AGENT

HEADERS = {
    "user-agent": USER_AGENT,
    "accept-language": "sv-SE,sv;q=0.9,en;q=0.8",
}

RunIo = Callable[..., Awaitable[Any]]


async def _run_inline(target: Callable[..., Any], *args: Any) -> Any:
    return target(*args)


@dataclass
class HttpResult:
    url: str
    status: int
    text: str


class Skola24Client:
    """One logged-in parent. Calls are serialized on a lock.

    session_file None keeps cookies in memory only. The jar is read on the
    first session and written when a session ends with changed cookies.
    """

    def __init__(
        self,
        credentials: Credentials,
        session_file: Path | None,
        *,
        http: httpx.AsyncClient | None = None,
        run_io: RunIo = _run_inline,
    ) -> None:
        self.credentials = credentials
        self.session_file = session_file
        self._http = http or httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
        )
        self._http.headers.update(HEADERS)
        self._run_io = run_io
        self._loaded = False
        self._saved: list[dict[str, str]] = []
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    @asynccontextmanager
    async def session(self):
        async with self._lock:
            if not self._loaded:
                await self._load_cookies()
            try:
                yield
            finally:
                await self._save_cookies()

    def cookie_count(self) -> int:
        return len(list(self._http.cookies.jar))

    def clear_cookies(self) -> None:
        self._http.cookies.clear()

    async def get(self, url: str, headers: dict[str, str] | None = None) -> HttpResult:
        extra = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            **(headers or {}),
        }
        response = await self._http.get(url, headers=extra)
        return HttpResult(str(response.url), response.status_code, response.text)

    async def post(
        self,
        url: str,
        body: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> HttpResult:
        response = await self._http.post(url, data=body, headers=headers)
        return HttpResult(str(response.url), response.status_code, response.text)

    async def json_post(
        self,
        url: str,
        body: object,
        *,
        scope: str,
        referer: str,
    ) -> HttpResult:
        raw = "null" if body is None else json.dumps(body)
        response = await self._http.post(
            url,
            content=raw.encode(),
            headers={
                "x-scope": scope,
                "x-requested-with": "XMLHttpRequest",
                "accept": "application/json, text/javascript, */*; q=0.01",
                "content-type": "application/json",
                "referer": referer,
                "origin": "https://web.skola24.se",
            },
        )
        return HttpResult(str(response.url), response.status_code, response.text)

    async def login(self) -> None:
        self.clear_cookies()
        host = self.credentials.host
        start = login_url(host)
        page = await self.get(start)
        if not looks_like_login_page(page.text):
            raise ApiError("Skola24 login page missing username field")
        fields = parse_form_fields(page.text, host)
        username_field = _field(fields, "usernametb")
        password_field = _field(fields, "pwdtb")
        button_field = _field(fields, "loginbutton")
        if not username_field or not password_field or not button_field:
            raise ApiError("Skola24 login form fields missing")
        if not any(key.lower() == "domaindropdown" for key in fields):
            raise ApiError("Skola24 login form missing DomainDropDown")
        fields[username_field] = self.credentials.username
        fields[password_field] = self.credentials.password
        if not fields.get(button_field):
            fields[button_field] = "Logga in"
        try:
            post_id = int(fields.get("__POST_ID") or "0")
        except ValueError:
            post_id = 0
        fields["__POST_ID"] = str(post_id + 1)

        posted = await self.post(
            page.url,
            fields,
            {
                "content-type": "application/x-www-form-urlencoded",
                "origin": f"https://{host}",
                "referer": start,
            },
        )
        if looks_like_login_page(posted.text):
            raise AuthError("Login failed. Check USERNAME/PASSWORD")
        if "web.skola24.se" not in posted.url:
            portal = await self.get(PORTAL, {"referer": posted.url})
            if (
                looks_like_login_page(portal.text)
                or looks_like_login_url(portal.url)
                or "web.skola24.se" not in portal.url
            ):
                raise ApiError("Login did not reach web.skola24.se")

    async def authed_api(self, path: str, body: object, *, scope: str, referer: str):
        retried = False

        async def attempt():
            nonlocal retried
            if self.cookie_count() == 0:
                await self.login()
            result = await self.json_post(
                f"{API_BASE}{path}",
                body,
                scope=scope,
                referer=referer,
            )
            parsed = _parse_envelope(result.text)
            if session_dead(result.status, result.text, result.url, parsed) and not retried:
                retried = True
                await self.login()
                return await attempt()
            if result.status < 200 or result.status >= 300:
                raise ApiError(
                    f"Skola24 API {path} HTTP {result.status}: {result.text[:240]}"
                )
            if parsed is None:
                raise ApiError(f"Skola24 API {path} returned non-JSON")
            if parsed.get("error"):
                raise ApiError(str(parsed["error"]))
            failed = [
                item
                for item in parsed.get("validation") or []
                if isinstance(item, dict) and item.get("isValid") is False and item.get("message")
            ]
            if failed:
                raise ApiError("; ".join(str(item["message"]) for item in failed))
            if parsed.get("data") is None:
                raise ApiError(f"Skola24 API {path} returned no data")
            return parsed["data"]

        return await attempt()

    async def _load_cookies(self) -> None:
        if self.session_file is not None:
            for item in await self._run_io(_read_cookies, self.session_file):
                self._http.cookies.set(
                    item["name"], item["value"], domain=item["domain"], path=item["path"]
                )
        self._saved = self._snapshot()
        self._loaded = True

    async def _save_cookies(self) -> None:
        cookies = self._snapshot()
        if self.session_file is None or cookies == self._saved:
            return
        await self._run_io(_write_cookies, self.session_file, cookies)
        self._saved = cookies

    def _snapshot(self) -> list[dict[str, str]]:
        return [
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
            }
            for cookie in self._http.cookies.jar
        ]


def _read_cookies(path: Path) -> list[dict[str, str]]:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    cookies = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        domain = item.get("domain")
        if not name or value is None or not domain:
            continue
        cookies.append(
            {
                "name": str(name),
                "value": str(value),
                "domain": str(domain),
                "path": str(item.get("path") or "/"),
            }
        )
    return cookies


def _write_cookies(path: Path, cookies: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cookies, indent=2) + "\n")
    tmp.chmod(0o600)
    tmp.replace(path)


def _field(fields: dict[str, str], needle: str) -> str | None:
    for key in fields:
        if needle in key.lower():
            return key
    return None


def _parse_envelope(text: str) -> dict | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed
