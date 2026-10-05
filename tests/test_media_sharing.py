"""Offscreen tests for XEP-0385 SIMS / XEP-0372 references / XEP-0300 hashes.

Parses the auxiliary media metadata a Monocles-style client attaches to an
HTTP-uploaded image and the XEP-0428 fallback / XEP-0066 OOB companions.

Run with:
    LD_LIBRARY_PATH=$HOME/.local/qtlibs/usr/lib/x86_64-linux-gnu \
    QT_QPA_PLATFORM=offscreen python3 tests/test_media_sharing.py
"""
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_sims_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.core.client import message_media  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


class _Msg:
    """Minimal stanza stand-in exposing only ``.xml``."""

    def __init__(self, xml):
        self.xml = xml


DUMP = """
<message id="a041882f" type="groupchat" to="rain@jabberworld.info/walkbook"
         from="rpng@conference.linuxoid.in/rain">
  <reference xmlns="urn:xmpp:reference:0" type="data">
    <media-sharing xmlns="urn:xmpp:sims:1">
      <file xmlns="urn:xmpp:jingle:apps:file-transfer:5">
        <name>IMG_20261001_155153.jpg</name>
        <hash xmlns="urn:xmpp:hashes:2" algo="sha-256">HXADAAwoYmV1E7hGFR2d5pbcWqWtSCYCVfHmCjCT9S0=</hash>
        <hash xmlns="urn:xmpp:hashes:2" algo="sha-1">0WRCrAkGZ2DIQyKQ7tQ0yAW+D8g=</hash>
        <hash xmlns="urn:xmpp:hashes:2" algo="sha-512">vBMqTL2B0QNsQKM8AelGVgXFbhaDkfYJI/0XAEw3eIQiUrbjU5T8h4ukIG9mwqDXJ4hg7AwRoJYaMj3ACfeshQ==</hash>
        <media-type>image/jpeg</media-type>
        <size>132534</size>
        <width xmlns="https://schema.org/">1920</width>
        <height xmlns="https://schema.org/">1079</height>
      </file>
      <sources>
        <reference xmlns="urn:xmpp:reference:0" type="data"
                   uri="https://upload.jabberworld.info/u/ec27/Ukq/IMG.jpg"/>
      </sources>
    </media-sharing>
  </reference>
  <fallback xmlns="urn:xmpp:fallback:0" for="jabber:x:oob">
    <body end="110" start="1"/>
  </fallback>
  <fallback xmlns="urn:xmpp:fallback:0" for="urn:xmpp:sims:1">
    <body end="110" start="1"/>
  </fallback>
  <x xmlns="jabber:x:oob">
    <url>https://upload.jabberworld.info/u/ec27/Ukq/IMG.jpg</url>
  </x>
  <body> https://upload.jabberworld.info/u/ec27/Ukq/IMG.jpg</body>
</message>
"""

# 1. SIMS metadata ------------------------------------------------------------
media = message_media(_Msg(ET.fromstring(DUMP)))
check("SIMS metadata is parsed", media is not None)
check("the file name is read",
      media and media["name"] == "IMG_20261001_155153.jpg")
check("the file size is read", media and media["size"] == 132534)
check("the media type is read", media and media["media_type"] == "image/jpeg")
check("the dimensions are read",
      media and media["width"] == 1920 and media["height"] == 1079)
check("all three hashes are read",
      media and media["hashes"] == {
          "sha-256": "HXADAAwoYmV1E7hGFR2d5pbcWqWtSCYCVfHmCjCT9S0=",
          "sha-1": "0WRCrAkGZ2DIQyKQ7tQ0yAW+D8g=",
          "sha-512": "vBMqTL2B0QNsQKM8AelGVgXFbhaDkfYJI/0XAEw3eIQiUrbjU5T8h4ukIG9mwqDXJ4hg7AwRoJYaMj3ACfeshQ==",
      })
check("the source URL is read",
      media and media["url"].endswith("/IMG.jpg"))
check("the SIMS fallback body range is read",
      media and media["hide_body"] == (1, 110))

# 2. OOB-only message ---------------------------------------------------------
oob = _Msg(ET.fromstring(
    '<message><x xmlns="jabber:x:oob">'
    '<url>https://host/pic.png</url></x></message>'))
check("an OOB-only message yields media",
      message_media(oob) == {
          "name": "", "size": 0, "media_type": "", "width": 0, "height": 0,
          "hashes": {}, "url": "https://host/pic.png", "hide_body": None})

# 3. a bare XEP-0372 data reference -------------------------------------------
ref = _Msg(ET.fromstring(
    '<message><reference xmlns="urn:xmpp:reference:0" type="data" '
    'uri="https://host/clip.mp4"/></message>'))
check("a bare data reference yields media",
      message_media(ref) and message_media(ref)["url"] == "https://host/clip.mp4")

# 4. a plain message has no media ---------------------------------------------
check("a plain message has no media",
      message_media(_Msg(ET.fromstring("<message><body>hi</body></message>")))
      is None)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All media-sharing tests passed.")
