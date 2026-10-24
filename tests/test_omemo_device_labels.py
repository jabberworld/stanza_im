"""OMEMO device lists with label/labelsig attributes.

Legacy OMEMO 0.3 does not define the attributes (Conversations/Psi+ add them
anyway); older OMEMO 2 schemas predate the standard signed label.  A strict
validation used to drop the whole list, losing every device id and logging a
traceback.  The plugin strips the labels for the legacy backend and retries
without them when an old OMEMO 2 schema rejects them.

Run with:
    QT_QPA_PLATFORM=offscreen python3 tests/test_omemo_device_labels.py
"""
import base64
import logging
import os
import sys
import tempfile
from xml.etree import ElementTree as ET

_SCRATCH = tempfile.mkdtemp(prefix="stanza_omemo_labels_")
os.environ["XDG_DATA_HOME"] = os.path.join(_SCRATCH, "data")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_SCRATCH, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_SCRATCH, "cache")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stanza_im.xmpp.omemo.plugin  # noqa: E402,F401 - installs the patch
import oldmemo.etree  # noqa: E402
import oldmemo.oldmemo  # noqa: E402
import twomemo.etree  # noqa: E402
import twomemo.twomemo  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name, flush=True)
    if not cond:
        FAILURES.append(name)


# 1. legacy OMEMO 0.3: labels are stripped, devices survive ------------------
ns = oldmemo.oldmemo.NAMESPACE
legacy = ET.Element("{%s}list" % ns)
ET.SubElement(legacy, "{%s}device" % ns,
              {"id": "123", "label": "Psi+"})
devices = oldmemo.etree.parse_device_list(legacy)
check("a legacy list with a label keeps its device",
      list(devices) == [123])

# 2. OMEMO 2: a current schema keeps the signed label ----------------------
ns2 = twomemo.twomemo.NAMESPACE
modern = ET.Element("{%s}devices" % ns2)
ET.SubElement(modern, "{%s}device" % ns2,
              {"id": "7", "label": "Phone",
               "labelsig": base64.b64encode(b"sig").decode("ascii")})
devices = twomemo.etree.parse_device_list(modern)
check("a modern OMEMO 2 list keeps its label",
      list(devices) == [7] and devices[7].label == "Phone")

# 3. an older OMEMO 2 schema: retry without the label keeps the id ---------
import xmlschema  # noqa: E402

strict = xmlschema.XMLSchema("""<?xml version='1.0' encoding='UTF-8'?>
<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'
           targetNamespace='urn:xmpp:omemo:2'
           xmlns='urn:xmpp:omemo:2'>
    <xs:element name='devices'>
        <xs:complexType>
            <xs:sequence minOccurs='0' maxOccurs='unbounded'>
                <xs:element ref='device'/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
    <xs:element name='device'>
        <xs:complexType>
            <xs:attribute name='id' type='xs:unsignedInt' use='required'/>
        </xs:complexType>
    </xs:element>
</xs:schema>
""")
original_schema = twomemo.etree.DEVICE_LIST_SCHEMA
twomemo.etree.DEVICE_LIST_SCHEMA = strict
try:
    devices = twomemo.etree.parse_device_list(modern)
finally:
    twomemo.etree.DEVICE_LIST_SCHEMA = original_schema
check("an old OMEMO 2 schema retries without the label and keeps the id",
      list(devices) == [7] and devices[7] is None)

# 4. the validation traceback is suppressed (a one-line warning stays) ------
class XMLSchemaValidationError(Exception):
    pass


record = logging.LogRecord(
    "slixmpp_omemo.xep_0384", logging.WARNING, __file__, 1, "malformed",
    None, (XMLSchemaValidationError, XMLSchemaValidationError("bad"), None))
for item in logging.getLogger("slixmpp_omemo.xep_0384").filters:
    item.filter(record)
check("a schema validation traceback is dropped from the log",
      record.exc_info is None)

if FAILURES:
    print("FAILURES:", FAILURES)
    sys.exit(1)
print("All OMEMO device-label tests passed.")
