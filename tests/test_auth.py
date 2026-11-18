from custom_components.skola24.auth import (
    looks_like_login_page,
    looks_like_login_url,
    parse_form_fields,
    payload_looks_logged_out,
    session_dead,
)


def test_login_page_detection():
    assert looks_like_login_page('<input name="LoginUC$UserNameTB" />')
    assert not looks_like_login_page("<div>portal</div>")


def test_login_url_detection():
    assert looks_like_login_url(
        "https://gavle.skola24.se/Applications/Authentication/login.aspx"
    )
    assert not looks_like_login_url("https://web.skola24.se/portal/start")


def test_parse_form_picks_host_when_nothing_selected():
    page = """
        <input name="LoginUC$UserNameTB" value="" />
        <select name="DomainDropDown">
            <option value="other.host">other.host</option>
            <option value="gavle.skola24.se">gavle.skola24.se</option>
        </select>
    """
    fields = parse_form_fields(page, "gavle.skola24.se")
    assert fields["DomainDropDown"] == "gavle.skola24.se"


def test_empty_schools_mean_logged_out():
    assert payload_looks_logged_out({"schools": []})
    assert not payload_looks_logged_out({"schools": [{"guid": "x"}]})


def test_401_is_dead():
    assert session_dead(401, "", "https://web.skola24.se/", None)
