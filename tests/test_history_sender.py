"""Old MAM rows must render with the roster name, not their bare JID.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_history_sender.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.ui.chat_widget import ChatWidget


FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _chat(is_muc=False, display_name="zwiftinsider"):
    chat = ChatWidget.__new__(ChatWidget)
    chat.is_muc = is_muc
    chat.display_name = display_name
    chat.jid = "zwiftinsider@rss.jabberworld.info"
    return chat


cw = _chat()
old = {"direction": "incoming",
       "sender": "zwiftinsider@rss.jabberworld.info"}
new = {"direction": "incoming", "sender": "zwiftinsider"}
out = {"direction": "outgoing", "sender": "Me"}

check("old 1:1 MAM rows use the roster name",
      ChatWidget._display_sender(cw, old) == "zwiftinsider")
check("new live rows keep their roster name",
      ChatWidget._display_sender(cw, new) == "zwiftinsider")
check("our own outgoing name is unchanged",
      ChatWidget._display_sender(cw, out) == "Me")

muc = _chat(is_muc=True, display_name="Room")
check("MUC nicks that contain @ are not treated as JIDs",
      ChatWidget._display_sender_name(muc, "user@nick") == "user@nick")
check("reply quotes are normalized too",
      ChatWidget._display_sender_name(
          cw, "zwiftinsider@rss.jabberworld.info") == "zwiftinsider")

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All history-sender tests passed.")
