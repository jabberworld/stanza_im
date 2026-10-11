"""Tests for the XEP-0284 Shared XML Editing record model.

Run with:
    python3 tests/test_sxe.py
"""
import os
import sys
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.xmpp.sxe import NS_SXE, SxeDocument

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


def _q(tag):
    return "{%s}%s" % (NS_SXE, tag)


# 1. build a document --------------------------------------------------------
doc = SxeDocument()
doc.set_attr(doc.root_rid, "viewBox", "0 0 600 400")
path_rid = doc.add_element(doc.root_rid, "path")
doc.add_attr(path_rid, "d", "M 0 0 L 10 10")
doc.add_attr(path_rid, "stroke", "#000000")

check("the root record exists", doc.records[doc.root_rid].name == "svg")
check("the path element is a child of the root",
      path_rid in doc.children(doc.root_rid))
check("the attribute is found", doc.find_attr(path_rid, "d") is not None)

# 2. set_attr updates in place ----------------------------------------------
attr_rid = doc.find_attr(path_rid, "d")
returned = doc.set_attr(path_rid, "d", "M 0 0 L 20 20")
check("set_attr reuses the existing attribute record", returned == attr_rid)
check("set_attr bumps the version",
      doc.records[attr_rid].version == 1)
check("set_attr changed the data",
      doc.records[attr_rid].chdata == "M 0 0 L 20 20")

# 3. new_elements_for returns parents before children ------------------------
elements = doc.new_elements_for(path_rid)
check("new_elements_for includes the element and its attributes",
      len(elements) == 3)
check("the element comes first", elements[0].get("rid") == path_rid)

# 4. serialise the whole document -------------------------------------------
snapshot = doc.all_new_elements()
check("the snapshot starts with the root",
      snapshot[0].get("rid") == doc.root_rid)

# 5. round-trip into a fresh document ---------------------------------------
doc2 = SxeDocument()
for el in snapshot:
    doc2.apply_new(el)
check("the fresh document has the same XML",
      ET.tostring(doc2.to_element(), encoding="unicode")
      == ET.tostring(doc.to_element(), encoding="unicode"))

# 6. apply a <set> -----------------------------------------------------------
set_el = ET.Element(_q("set"))
set_el.set("target", doc2.find_attr(path_rid, "d"))
set_el.set("chdata", "M 0 0 L 30 30")
doc2.apply_set(set_el)
check("apply_set updated the attribute",
      doc2.records[doc2.find_attr(path_rid, "d")].chdata == "M 0 0 L 30 30")

# 7. apply a <remove> --------------------------------------------------------
remove_el = ET.Element(_q("remove"))
remove_el.set("target", path_rid)
doc2.apply_remove(remove_el)
check("apply_remove dropped the element", path_rid not in doc2.records)
check("apply_remove detached it from the root",
      path_rid not in doc2.children(doc2.root_rid))

# 8. remove cascades ---------------------------------------------------------
doc3 = SxeDocument()
el_rid = doc3.add_element(doc3.root_rid, "g")
child_rid = doc3.add_element(el_rid, "path")
attr_id = doc3.add_attr(child_rid, "d", "M 0 0")
removed = doc3.remove(el_rid)
check("remove cascades to descendants",
      set(removed) == {el_rid, child_rid, attr_id})

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All sxe tests passed.")
