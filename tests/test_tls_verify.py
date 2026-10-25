"""TLS verification context and certificate-error handling.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_tls_verify.py
"""
import os
import ssl
import sys
import tempfile
from types import SimpleNamespace

_SCRATCH = tempfile.mkdtemp(prefix="stanza_tls_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6 import QtWidgets  # noqa: E402

from stanza_im.core.client import (  # noqa: E402
    JabberClient, build_ssl_context)
from stanza_im.core.storage import Config  # noqa: E402
from stanza_im.i18n import load as i18n_load  # noqa: E402
from stanza_im.ui.certificate_error_dialog import (  # noqa: E402
    CertificateErrorDialog)

i18n_load("en")
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


verified = build_ssl_context(True)
check("the default context requires a trusted certificate",
      verified.verify_mode == ssl.CERT_REQUIRED
      and verified.check_hostname)
unverified = build_ssl_context(False)
check("the ignore context disables verification",
      unverified.verify_mode == ssl.CERT_NONE
      and not unverified.check_hostname)

cert_exc = ssl.SSLCertVerificationError(1, "certificate verify failed")
check("a certificate verification error is recognised",
      JabberClient._is_cert_error(cert_exc))
check("an unrelated socket error is not a certificate error",
      not JabberClient._is_cert_error(OSError("connection refused")))


class _Fake:
    def __init__(self):
        self._cert_error_sent = False
        self._cert_blocked = False
        self.host = ""
        self.jid_str = "alice@example.org"
        self.xmpp = SimpleNamespace(auto_reconnect=True)
        self.events = []

    def emit(self, *args):
        self.events.append(args)


fake = _Fake()
JabberClient._report_cert_error(fake, cert_exc)
check("a certificate error is reported once",
      len(fake.events) == 1
      and fake.events[0][0] == "certificate_error"
      and fake.events[0][1] == "example.org")
check("the reconnect loop is blocked while the prompt is open",
      fake._cert_blocked and fake.xmpp.auto_reconnect is False)
JabberClient._report_cert_error(fake, cert_exc)
check("a repeated error does not open a second prompt", len(fake.events) == 1)
JabberClient.clear_certificate_block(fake)
check("clearing the block allows a retry",
      not fake._cert_blocked and fake.xmpp.auto_reconnect is True)


class _Ctx:
    def __init__(self):
        self.xmpp = SimpleNamespace(ssl_context=None)
        self.allow_invalid_cert = False


ctx = _Ctx()
JabberClient.set_tls_verification(ctx, False)
check("set_tls_verification(false) switches to an unverified context",
      ctx.allow_invalid_cert
      and ctx.xmpp.ssl_context.verify_mode == ssl.CERT_NONE)
JabberClient.set_tls_verification(ctx, True)
check("set_tls_verification(true) restores verification",
      not ctx.allow_invalid_cert
      and ctx.xmpp.ssl_context.verify_mode == ssl.CERT_REQUIRED)

# Dialog choices ------------------------------------------------------------
dlg = CertificateErrorDialog("example.org", "certificate verify failed")
dlg._choose("once")
check("the dialog exposes the one-off choice",
      dlg.choice == "once" and dlg.result() == QtWidgets.QDialog.DialogCode.Accepted)
dlg2 = CertificateErrorDialog("example.org", "certificate verify failed")
dlg2._choose("always")
check("the dialog exposes the persistent choice", dlg2.choice == "always")
dlg3 = CertificateErrorDialog("example.org", "certificate verify failed")
dlg3.reject()
check("closing the dialog defaults to cancel", dlg3.choice == "cancel")

# Config + Preferences setting ---------------------------------------------
from stanza_im.ui.chat_themes import ChatThemeFactory  # noqa: E402
from stanza_im.ui.preferences import PreferencesDialog  # noqa: E402

cfg = Config()
check("certificate verification is on by default",
      getattr(cfg.connection, "allow_invalid_cert", None) is False)
prefs = PreferencesDialog(cfg, ChatThemeFactory())
prefs._ensure_all_pages()
check("the connection page has the certificate checkbox",
      "allow_invalid_cert" in prefs._controls)
prefs._controls["allow_invalid_cert"].setChecked(True)
prefs._apply_settings()
check("the certificate override is persisted in the profile",
      cfg.connection.allow_invalid_cert is True)
prefs.close()

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All TLS-verification tests passed.")
