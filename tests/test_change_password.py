"""Change-password flow tests (no network required).

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_change_password.py
"""
import asyncio
import os
import sys
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="stanza_pw_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets
from stanza_im.core.storage import Config
from stanza_im.i18n import load as load_i18n
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.change_password_dialog import ChangePasswordDialog
from stanza_im.ui.preferences import PreferencesDialog

load_i18n("en")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)


class _FakeClient:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    async def change_password(self, new_password, server=None):
        self.calls.append((new_password, server))
        if self.fail:
            raise RuntimeError("not-allowed")


# 1. dialog validation ------------------------------------------------------
d1 = ChangePasswordDialog()
check("empty rejected", bool(d1._validate()))
d1._new.setText("abc123")
check("unfilled confirm rejected", bool(d1._validate()))
d1._confirm.setText("abc124")
check("mismatch rejected", bool(d1._validate()))
d1._confirm.setText("abc123")
check("match accepted", d1._validate() == "")
_check = d1.password()
check("password getter", _check == "abc123")

# 2. OK handler only accepts a valid input ---------------------------------
d2 = ChangePasswordDialog()
d2._new.setText("one")
d2._confirm.setText("two")
d2._on_accept()
check("OK keeps dialog open on mismatch",
      d2.result() != QtWidgets.QDialog.DialogCode.Accepted)
d2._confirm.setText("one")
d2._on_accept()
check("OK accepts on match",
      d2.result() == QtWidgets.QDialog.DialogCode.Accepted)

# 3. button disabled without a client ---------------------------------------
cfg = Config()
cfg.save_password = True
dlg = PreferencesDialog(cfg, ChatThemeFactory())
check("button disabled when client is None",
      not dlg._btn_change_password.isEnabled())
check("save_password control present", "save_password" in dlg._controls)

# 4. success path -----------------------------------------------------------
cfg2 = Config()
cfg2.save_password = True
client = _FakeClient()
dlg2 = PreferencesDialog(cfg2, ChatThemeFactory(), client=client)
check("button enabled with client", dlg2._btn_change_password.isEnabled())
heard = []
dlg2.password_changed.connect(heard.append)
ok = asyncio.run(dlg2._do_change_password("new-pass"))
check("success returns ok", ok == "ok")
check("client called", client.calls == [("new-pass", None)])
check("config password updated", cfg2.password == "new-pass")
check("signal emitted", heard == ["new-pass"])

# 5. failure path -----------------------------------------------------------
cfg3 = Config()
cfg3.save_password = False
cfg3.password = "keepme"
client3 = _FakeClient(fail=True)
dlg3 = PreferencesDialog(cfg3, ChatThemeFactory(), client=client3)
res = asyncio.run(dlg3._do_change_password("new-pass"))
check("failure returns error text", res and res != "ok")
check("config untouched on failure", cfg3.password == "keepme")

# 6. not connected ----------------------------------------------------------
dlg4 = PreferencesDialog(Config(), ChatThemeFactory())
res4 = asyncio.run(dlg4._do_change_password("x"))
check("not connected reports", res4 == "You are not connected.")

print("FAILURES:", FAILURES if FAILURES else "none")
sys.exit(1 if FAILURES else 0)