"""Offscreen tests for the persistent prepared-chat render cache.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_chat_render_cache.py
"""
import os
import sys
import tempfile

os.environ["XDG_CACHE_HOME"] = os.path.join(tempfile.mkdtemp(), "cache")
os.environ["XDG_CONFIG_HOME"] = os.path.join(tempfile.mkdtemp(), "config")
os.environ["XDG_DATA_HOME"] = os.path.join(tempfile.mkdtemp(), "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core import chat_render_cache as cache
from stanza_im.ui.chat_themes import ChatThemeFactory
from stanza_im.ui.chat_widget import ChatWidget

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


cache.clear()
refs = ["r1", "r2"]
html = ["<div>one</div>", "<div>two</div>"]
cache.put("me@example.com", "bob@example.com", "settings-a", refs, html, 50)
check("a matching window is returned",
      cache.get("me@example.com", "bob@example.com", "settings-a", refs) == html)
check("a changed settings hash misses",
      cache.get("me@example.com", "bob@example.com", "settings-b", refs) is None)
check("changed message refs miss",
      cache.get("me@example.com", "bob@example.com", "settings-a",
                ["r1", "r3"]) is None)
check("another account does not see the window",
      cache.get("other@example.com", "bob@example.com", "settings-a",
                refs) is None)
check("the database stores one entry", cache.count() == 1)

cache.invalidate("me@example.com", "bob@example.com")
check("invalidate removes one chat", cache.count() == 0)

for index in range(105):
    cache.put("me@example.com", f"u{index}@example.com", "s",
              ["r"], [f"<div>{index}</div>"], 1)
check("the count limit is enforced", cache.count() <= cache.MAX_CHATS)
check("the newest entries survive",
      cache.get("me@example.com", "u104@example.com", "s", ["r"]) == ["<div>104</div>"])
check("the oldest entries were evicted",
      cache.get("me@example.com", "u0@example.com", "s", ["r"]) is None)

cache.clear()
check("clear empties the cache", cache.count() == 0)

# ChatWidget reads a prepared window using its content-sensitive refs.
w = ChatWidget.__new__(ChatWidget)
w.jid = "bob@example.com"
w.is_muc = False
w._own_jid = "me@example.com"
w._own_avatar = ""
w._peer_avatar = ""
w._avatar_radius = 20
w._colored_muc_nicks = True
w._show_muc_hats = True
w._show_avatars = True
w._text_scale = 1.0
w._users = []
w._theme = ChatThemeFactory()
w._view = type("V", (), {"supports_prepared": True})()
entry = {"sender": "Bob", "body": "hello", "direction": "incoming",
         "timestamp": "2026-10-21T11:00:00Z", "origin_id": "m1"}
refs = [w._render_ref(entry)]
settings = w._render_settings_hash()
cache.put("me@example.com", "bob@example.com", settings, refs,
          ["<div class='stanza-message'>hello</div>"], 50)
check("ChatWidget loads its prepared window",
      w.load_prepared([entry]) == ["<div class='stanza-message'>hello</div>"])
entry["body"] = "edited"
check("an edited row invalidates the prepared window",
      w.load_prepared([entry]) is None)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All chat render cache tests passed.")
