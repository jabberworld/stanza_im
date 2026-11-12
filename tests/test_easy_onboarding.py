"""Offscreen tests for Easy Onboarding primitives and single-instance forwarding.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_easy_onboarding.py
"""
import asyncio
import os
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_onboarding_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ["XDG_RUNTIME_DIR"] = os.path.join(_SCRATCH, "runtime")
os.makedirs(os.environ["XDG_RUNTIME_DIR"], mode=0o700, exist_ok=True)
os.chmod(os.environ["XDG_RUNTIME_DIR"], 0o700)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtCore, QtWidgets

import slixmpp

from stanza_im import app as app_mod
from stanza_im.core.client import JabberClient
from stanza_im.include import constants
from stanza_im.include.xmpp_uri import make_xmpp_uri, parse_invitation
from stanza_im.core import pars_tokens
from stanza_im.single_instance import (
    SingleInstance, decode_payload, encode_payload)

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
constants.DATA_DIR = os.path.join(_SCRATCH, "data")
os.makedirs(constants.DATA_DIR, exist_ok=True)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# 1. URI grammar -------------------------------------------------------------
roster = parse_invitation(
    "xmpp:romeo@example.com?roster;preauth=abc;name=Romeo;ibr=y")
check("roster invitation parsed",
      bool(roster)
      and roster["action"] == "roster"
      and roster["jid"] == "romeo@example.com"
      and roster["server"] == "example.com"
      and roster["token"] == "abc"
      and roster["ibr"] is True
      and roster["name"] == "Romeo")
register = parse_invitation(
    "xmpp:juliet@example.com?register;preauth=def")
check("account invitation parsed",
      bool(register) and register["action"] == "register"
      and register["username"] == "juliet"
      and register["server"] == "example.com")
domain_only = parse_invitation("xmpp:example.com?register;preauth=ghi")
check("server-only account invitation parsed",
      bool(domain_only) and domain_only["username"] == ""
      and domain_only["server"] == "example.com")
check("invitation without token is rejected",
      parse_invitation("xmpp:romeo@example.com?roster") is None)
check("ordinary xmpp URI is not an invitation",
      parse_invitation("xmpp:romeo@example.com?message") is None)
made = make_xmpp_uri("romeo@example.com", "roster",
                     preauth="abc", name="Romeo")
check("invitation URI round-trips through make_xmpp_uri",
      parse_invitation(made)["token"] == "abc")

# 2. argv extraction ---------------------------------------------------------
uris, rest = app_mod.extract_xmpp_uris(
    ["--debug", "xmpp:a@b?roster;preauth=x", "xmpp:c@d?register;preauth=y",
     "--log"])
check("all xmpp: argv entries are extracted",
      uris == ["xmpp:a@b?roster;preauth=x", "xmpp:c@d?register;preauth=y"]
      and rest == ["--debug", "--log"])

# 3. local PARS token store --------------------------------------------------
token = pars_tokens.issue(name="Alice")
check("PARS token is URL-safe", bool(token) and " " not in token)
entry = pars_tokens.consume(token)
check("PARS token is consumed once", entry is not None
      and entry.get("name") == "Alice")
check("a used PARS token is rejected", pars_tokens.consume(token) is None)
expired = pars_tokens.issue(ttl=1)
time.sleep(1.1)
check("an expired PARS token is rejected", pars_tokens.consume(expired) is None)

# 4. single-instance forwarding ----------------------------------------------
first = SingleInstance()
check("single-instance listener starts", first.listen())
received = []
first.uris_received.connect(lambda uris, raise_window: received.append(
    (uris, raise_window)))
second = SingleInstance()
check("second instance forwards", second.forward(
    ["xmpp:a@b?roster;preauth=x"], True, timeout_ms=800))
for _ in range(20):
    app.processEvents()
    QtCore.QThread.msleep(10)
check("the first instance receives the URI",
      received == [(["xmpp:a@b?roster;preauth=x"], True)])
check("payload validates only xmpp: URIs",
      decode_payload(encode_payload(["xmpp:a", "https://x"], True))
      == (["xmpp:a"], True))
second_listener = SingleInstance()
check("an active socket is never stolen", not second_listener.listen())
first.close()

# 4a. onboarding choices ----------------------------------------------------
from stanza_im.ui.easy_onboarding_dialog import EasyOnboardingDialog
onboarding_payloads = []
roster_dialog = EasyOnboardingDialog({
    "uri": "xmpp:romeo@example.com?roster;preauth=x;ibr=y",
    "action": "roster", "jid": "romeo@example.com",
    "server": "example.com", "username": "romeo", "token": "x",
    "ibr": True, "name": "Romeo"})
roster_dialog.register_requested.connect(onboarding_payloads.append)
roster_dialog._register("example.com")
check("a roster invitation does not lock the account name",
      onboarding_payloads and not onboarding_payloads[0]["username_locked"]
      and onboarding_payloads[0]["preauth"] == "x")
register_dialog = EasyOnboardingDialog({
    "uri": "xmpp:juliet@example.com?register;preauth=y",
    "action": "register", "jid": "juliet@example.com",
    "server": "example.com", "username": "juliet", "token": "y",
    "ibr": False, "name": ""})
onboarding_payloads.clear()
register_dialog.register_requested.connect(onboarding_payloads.append)
register_dialog._register("example.com")
check("a register invitation locks the account name",
      onboarding_payloads and onboarding_payloads[0]["username_locked"])

# 4b. incoming PARS token auto-approval -------------------------------------
pars_client = JabberClient("me@example.com/res", "pw")
pars_client.subscription = lambda jid: "none"
pars_calls = []
pars_client.approve_subscription = lambda jid: pars_calls.append(("approve", jid))
pars_client.request_subscription = lambda jid: pars_calls.append(("request", jid))
pars_client.xmpp.update_roster = lambda jid, **kw: pars_calls.append(
    ("roster", jid))
pars_events = []
pars_client.on("pars_subscription_accepted",
               lambda jid, name: pars_events.append((jid, name)))
pars_token = pars_tokens.issue(name="New contact")
pars_pres = slixmpp.Presence()
pars_pres["from"] = "new@example.net/phone"
pars_pres["type"] = "subscribe"
preauth_el = pars_pres.xml.makeelement(
    "{urn:xmpp:pars:0}preauth", {"token": pars_token})
pars_pres.xml.append(preauth_el)
pars_client._on_subscription_request(pars_pres)
check("a valid PARS token is auto-approved",
      ("approve", "new@example.net") in pars_calls
      and pars_events == [("new@example.net", "New contact")])
pars_client._on_subscription_request(pars_pres)
check("a used PARS token falls back to a normal request",
      len(pars_events) == 1)

# 5. desktop entry -----------------------------------------------------------
desktop = open(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources", "stanza-im.desktop"), encoding="utf-8").read()
check("desktop entry handles all xmpp: arguments", "Exec=" in desktop
      and "%U" in desktop
      and "x-scheme-handler/xmpp" in desktop)
from tools import install_desktop  # noqa: E402
contents = install_desktop.desktop_contents()
check("generated desktop entry has a command and %U",
      "Exec=" in contents and "%U" in contents)

# 6. invitation result parsing ------------------------------------------------
class _Field:
    def __init__(self, var, value):
        self._data = {"var": var, "value": value}
    def get(self, key, default=None):
        return self._data.get(key, default)


class _Form:
    def __init__(self, fields):
        self._fields = fields
    def __getitem__(self, key):
        if key == "fields":
            return self._fields
        raise KeyError(key)


class _Client:
    _invitation_result = staticmethod(
        __import__("stanza_im.core.client", fromlist=["JabberClient"])
        .JabberClient._invitation_result)


result = _Client._invitation_result({
    "form": _Form([
        _Field("uri", "xmpp:a@b?roster;preauth=x"),
        _Field("landing-url", "https://example.com/i/x"),
        _Field("expiry", "2026-01-01T00:00:00Z"),
    ])})
check("invitation result fields parsed",
      result["uri"].startswith("xmpp:")
      and result["landing_url"] == "https://example.com/i/x"
      and result["expire"] == "2026-01-01T00:00:00Z")

# 7. Account invitation submits the form -------------------------------------
from slixmpp.plugins.xep_0004.stanza import Form, FormField


def _form(kind, fields):
    form = Form()
    form["type"] = kind
    for var, value, ftype in fields:
        field = FormField()
        field["var"] = var
        field["type"] = ftype
        if value is not None:
            field["value"] = value
        form.append(field)
    return form


captured = {}


async def _start_command(jid, node):
    return {
        "session": {"sessionid": "s1"}, "status": "executing",
        "error": "",
        "form": _form("form", [
            ("username", None, "text-single"),
            ("roster-subscription", None, "boolean"),
        ]),
    }


async def _continue_command(session, action, form):
    captured["type"] = form["type"]
    captured["values"] = {field["var"]: field["value"]
                          for field in form["fields"]}
    return {
        "session": session, "status": "completed", "error": "",
        "form": _form("result", [
            ("uri", "xmpp:new@example.com?register;preauth=t", "text-single"),
            ("landing-url", "https://example.com/invite/t", "text-single"),
            ("expire", "2026-01-01T00:00:00Z", "text-single"),
        ]),
    }


async_client = JabberClient("me@example.com/res", "pw")
async_client.start_command = _start_command
async_client.continue_command = _continue_command
_account_result = asyncio.run(
    async_client.create_account_invitation("new", True))
check("account invitation submits a submit form",
      captured.get("type") == "submit"
      and captured.get("values", {}).get("username") == "new"
      and str(captured.get("values", {}).get("roster-subscription")).lower()
      in ("1", "true"))
check("account invitation parses the server result",
      _account_result["uri"].startswith("xmpp:")
      and _account_result["landing_url"].endswith("/invite/t"))

# 8. Pre-auth IBR bypasses the pre-session stanza queue ----------------------
captured_preauth = {}


class _FakeIq:
    def __init__(self, owner):
        self._owner = owner
        self.xml = ET.Element("iq")

    def __setitem__(self, key, value):
        self.xml.set(key, str(value))

    async def send(self, timeout=None):
        captured_preauth["timeout"] = timeout
        captured_preauth["sends_before_session"] = (
            self._owner._always_send_everything)
        return None


class _FakeXmpp:
    def __init__(self):
        self._always_send_everything = False

    def Iq(self):
        return _FakeIq(self)


_preauth_client = async_client
_fake_xmpp = _FakeXmpp()
_preauth_client.xmpp = _fake_xmpp
asyncio.run(_preauth_client.preauth_ibr("example.com", "token-1"))
check("pre-auth IQ is sent before session start",
      captured_preauth.get("sends_before_session") is True
      and captured_preauth.get("timeout") == 20)
check("the pre-session send override is restored",
      _fake_xmpp._always_send_everything is False)

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)
