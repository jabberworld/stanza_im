"""Startup-laziness guard: heavy optional modules must not load at import.

The login window must appear without pulling in the OMEMO stack, aiortc or
QtWebEngine; those are probed in the background or imported on first use.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_startup.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_SCRATCH = tempfile.mkdtemp(prefix="stanza_startup_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


# Importing the UI must stay light: no OMEMO stack, no aiortc, no WebEngine.
import stanza_im.ui.main_window  # noqa: E402,F401

for module in ("stanza_im.xmpp.omemo", "stanza_im.xmpp.media", "aiortc",
               "av", "stanza_im.core.client", "PyQt6.QtWebEngineWidgets"):
    check("importing the UI does not load %s" % module,
          module not in sys.modules)

# Plugin discovery (run at startup) must not drag in the client/aiortc chain.
import stanza_im.plugins as plugins  # noqa: E402

plugins.discover()
for module in ("stanza_im.core.client", "stanza_im.xmpp.media", "aiortc"):
    check("plugin discovery does not load %s" % module,
          module not in sys.modules)

# The capability probe is pure (find_spec, no import).
from stanza_im.include.constants import webengine_available  # noqa: E402

check("webengine_available returns a bool",
      isinstance(webengine_available(), bool))
check("the webengine probe does not import WebEngine",
      "PyQt6.QtWebEngineWidgets" not in sys.modules)

# The scheme registration lives in its own idempotent helper.
from stanza_im.ui import url_schemes  # noqa: E402

check("url_schemes exposes ensure_registered",
      callable(url_schemes.ensure_registered))

# The attention plugin carries the namespace without importing the client.
from stanza_im.plugins import attention  # noqa: E402

check("the attention plugin defines NS_ATTENTION locally",
      attention.NS_ATTENTION == "urn:xmpp:attention:0")
check("importing the attention plugin does not load the client",
      "stanza_im.core.client" not in sys.modules)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All startup-laziness tests passed.")
