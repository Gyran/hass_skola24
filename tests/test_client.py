import asyncio
import json

import httpx
import pytest

from custom_components.skola24.auth import ApiError, AuthError, Credentials
from custom_components.skola24.client import Skola24Client

LOGIN_PAGE = """
    <form>
    <input name="LoginUC$UserNameTB" value="" />
    <input name="LoginUC$PwdTB" value="" />
    <input name="LoginUC$LoginButton" value="Logga in" />
    <select name="DomainDropDown"><option value="h" selected="selected">h</option></select>
    </form>
"""


def _transport(password: str = "pw", api=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if "login.aspx" in request.url.path and request.method == "GET":
            return httpx.Response(200, text=LOGIN_PAGE)
        if "login.aspx" in request.url.path:
            if f"PwdTB={password}" not in request.content.decode():
                return httpx.Response(200, text=LOGIN_PAGE)
            return httpx.Response(
                302,
                headers={"location": "https://web.skola24.se/", "set-cookie": "s=1; Path=/"},
            )
        if request.url.path == "/":
            return httpx.Response(200, text="portal")
        return api(request) if api else httpx.Response(200, json={"data": {"ok": True}})

    return httpx.MockTransport(handler)


def _client(tmp_path, transport, password="pw", calls=None):
    async def run_io(target, *args):
        if calls is not None:
            calls.append(target.__name__)
        return target(*args)

    return Skola24Client(
        Credentials("u", password, "gavle.skola24.se"),
        tmp_path / "session.json",
        http=httpx.AsyncClient(transport=transport, follow_redirects=True),
        run_io=run_io,
    )


def test_login_and_cookie_io_go_through_run_io(tmp_path):
    calls: list[str] = []
    client = _client(tmp_path, _transport(), calls=calls)

    async def go():
        async with client.session():
            return await client.authed_api("/x", None, scope="s", referer="r")

    assert asyncio.run(go()) == {"ok": True}
    assert calls == ["_read_cookies", "_write_cookies"]
    saved = json.loads((tmp_path / "session.json").read_text())
    assert [c["name"] for c in saved] == ["s"]


def test_unchanged_cookies_are_not_rewritten(tmp_path):
    calls: list[str] = []
    client = _client(tmp_path, _transport(), calls=calls)

    async def go():
        for _ in range(2):
            async with client.session():
                await client.authed_api("/x", None, scope="s", referer="r")

    asyncio.run(go())
    assert calls.count("_write_cookies") == 1


def test_dead_session_relogs_once(tmp_path):
    hits = []

    def api(request):
        hits.append(1)
        if len(hits) == 1:
            return httpx.Response(401)
        return httpx.Response(200, json={"data": {"ok": True}})

    client = _client(tmp_path, _transport(api=api))

    async def go():
        async with client.session():
            return await client.authed_api("/x", None, scope="s", referer="r")

    assert asyncio.run(go()) == {"ok": True}
    assert len(hits) == 2


def test_wrong_password_is_auth_error(tmp_path):
    client = _client(tmp_path, _transport(password="right"), password="wrong")

    async def go():
        async with client.session():
            await client.authed_api("/x", None, scope="s", referer="r")

    with pytest.raises(AuthError):
        asyncio.run(go())


def test_api_failure_is_not_auth_error(tmp_path):
    client = _client(
        tmp_path,
        _transport(api=lambda r: httpx.Response(500, text="boom")),
    )

    async def go():
        async with client.session():
            await client.authed_api("/x", None, scope="s", referer="r")

    with pytest.raises(ApiError):
        asyncio.run(go())
