"""XEP-0284 Shared XML Editing — record model and shared document.

A :class:`SxeDocument` keeps an unordered set of :class:`Record` objects (one
per DOM node) and can apply the XEP-0284 ``<new>``/``<set>``/``<remove>`` edits,
serialise the whole state as ``<new>`` elements, and rebuild the XML document.

Only the subset the whiteboard needs is implemented (element/attr/text records,
last-writer-wins ``<set>`` handling); the wire vocabulary and ordering rules
(``primary-weight`` then RID) follow the specification.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

NS_SXE = "urn:xmpp:sxe:0"
NS_SXE_TRANSPORT = "urn:xmpp:jingle:transports:sxe"

RECORD_TYPES = ("element", "attr", "text", "comment", "processinginstruction")


def _new_rid() -> str:
    return uuid.uuid4().hex


@dataclass
class Record:
    """One DOM node's synchronized state."""

    rid: str
    type: str = "element"
    version: int = 0
    parent: str = ""
    primary_weight: float = 0.0
    ns: str = ""
    name: str = ""
    chdata: str = ""
    pitarget: str = ""
    pidata: str = ""
    children: list[str] = field(default_factory=list)

    def new_element(self) -> ET.Element:
        """Serialise this record as an XEP-0284 ``<new/>`` element."""
        el = ET.Element(f"{{{NS_SXE}}}new")
        el.set("rid", self.rid)
        el.set("type", self.type)
        if self.version:
            el.set("version", str(self.version))
        if self.parent:
            el.set("parent", self.parent)
        el.set("primary-weight", "%g" % self.primary_weight)
        if self.type in ("element", "attr"):
            if self.ns:
                el.set("ns", self.ns)
            el.set("name", self.name)
        if self.type in ("attr", "text", "comment"):
            el.set("chdata", self.chdata)
        if self.type == "processinginstruction":
            el.set("pitarget", self.pitarget)
            el.set("pidata", self.pidata)
        return el

    @classmethod
    def from_new(cls, el: ET.Element) -> "Record":
        rid = str(el.get("rid") or "")
        try:
            version = int(el.get("version") or 0)
        except (TypeError, ValueError):
            version = 0
        try:
            weight = float(el.get("primary-weight") or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        return cls(
            rid=rid, type=str(el.get("type") or "element"), version=version,
            parent=str(el.get("parent") or ""), primary_weight=weight,
            ns=str(el.get("ns") or ""), name=str(el.get("name") or ""),
            chdata=str(el.get("chdata") or ""),
            pitarget=str(el.get("pitarget") or ""),
            pidata=str(el.get("pidata") or ""))


class SxeDocument:
    """A shared XML document synchronized with the SXE record model."""

    def __init__(self, root_name: str = "svg",
                 root_ns: str = "http://www.w3.org/2000/svg"):
        self.records: dict[str, Record] = {}
        self._next_weight: dict[str, float] = {}
        self.root_rid = _new_rid()
        root = Record(rid=self.root_rid, type="element", name=root_name,
                      ns=root_ns)
        self.records[self.root_rid] = root

    # ── Building ──────────────────────────────────────────────────

    def _weight(self, parent: str) -> float:
        value = self._next_weight.get(parent, 0.0) + 1.0
        self._next_weight[parent] = value
        return value

    def _attach(self, record: Record) -> None:
        self.records[record.rid] = record
        parent = self.records.get(record.parent)
        if parent is not None and record.rid not in parent.children:
            parent.children.append(record.rid)

    def add_element(self, parent: str, name: str, ns: str = "",
                    attrs: dict | None = None) -> str:
        rid = _new_rid()
        self._attach(Record(rid=rid, type="element", parent=parent, name=name,
                            ns=ns, primary_weight=self._weight(parent)))
        for key, value in (attrs or {}).items():
            self.add_attr(rid, key, value)
        return rid

    def add_attr(self, parent: str, name: str, value: str,
                 ns: str = "") -> str:
        rid = _new_rid()
        self._attach(Record(rid=rid, type="attr", parent=parent, name=name,
                            chdata=str(value), ns=ns,
                            primary_weight=self._weight(parent)))
        return rid

    def find_attr(self, element: str, name: str) -> str | None:
        for child in self.children(element):
            record = self.records[child]
            if record.type == "attr" and record.name == name:
                return child
        return None

    def set_chdata(self, rid: str, value: str) -> bool:
        record = self.records.get(rid)
        if record is None:
            return False
        record.chdata = str(value)
        record.version += 1
        return True

    def set_attr(self, element: str, name: str, value: str,
                 ns: str = "") -> str:
        """Set (creating if needed) an attribute; returns the attr record id."""
        rid = self.find_attr(element, name)
        if rid is None:
            return self.add_attr(element, name, value, ns=ns)
        self.set_chdata(rid, value)
        return rid

    def remove(self, rid: str) -> list[str]:
        """Remove *rid* and its descendants; returns the removed record ids."""
        record = self.records.get(rid)
        if record is None:
            return []
        removed: list[str] = []
        for child in list(record.children):
            removed.extend(self.remove(child))
        parent = self.records.get(record.parent)
        if parent is not None and rid in parent.children:
            parent.children.remove(rid)
        self.records.pop(rid, None)
        removed.append(rid)
        return removed

    def children(self, rid: str) -> list[str]:
        record = self.records.get(rid)
        if record is None:
            return []
        return sorted(record.children,
                      key=lambda r: (self.records[r].primary_weight, r))

    # ── Edits (local → wire) ──────────────────────────────────────

    def new_elements_for(self, rid: str) -> list[ET.Element]:
        """``<new/>`` elements for *rid* and its subtree (parents first)."""
        record = self.records.get(rid)
        if record is None:
            return []
        out = [record.new_element()]
        for child in self.children(rid):
            out.extend(self.new_elements_for(child))
        return out

    def all_new_elements(self) -> list[ET.Element]:
        """The whole document as ``<new/>`` elements (state snapshot)."""
        return self.new_elements_for(self.root_rid)

    # ── Edits (wire → local) ──────────────────────────────────────

    def apply_new(self, el: ET.Element) -> None:
        record = Record.from_new(el)
        if not record.rid:
            return
        if record.type == "element" and not record.parent:
            # A state snapshot carries its own root element; adopt it so the
            # received document is rendered from that root.
            old_root = self.root_rid
            self.root_rid = record.rid
            self.records[record.rid] = record
            if old_root != record.rid:
                self.records.pop(old_root, None)
            return
        self.records[record.rid] = record
        parent = self.records.get(record.parent)
        if parent is not None and record.rid not in parent.children:
            parent.children.append(record.rid)
        self._next_weight[record.parent] = max(
            self._next_weight.get(record.parent, 0.0), record.primary_weight)

    def apply_set(self, el: ET.Element) -> None:
        target = str(el.get("target") or "")
        record = self.records.get(target)
        if record is None:
            return
        for attr, name in (("parent", "parent"), ("ns", "ns"), ("name", "name"),
                           ("chdata", "chdata"), ("pitarget", "pitarget"),
                           ("pidata", "pidata")):
            if el.get(attr) is not None:
                setattr(record, name, str(el.get(attr)))
        if el.get("primary-weight") is not None:
            try:
                record.primary_weight = float(el.get("primary-weight"))
            except (TypeError, ValueError):
                pass
        if el.get("parent") is not None:
            for candidate in self.records.values():
                if record.rid in candidate.children \
                        and candidate.rid != record.parent:
                    candidate.children.remove(record.rid)
            parent = self.records.get(record.parent)
            if parent is not None and record.rid not in parent.children:
                parent.children.append(record.rid)
        record.version += 1

    def apply_remove(self, el: ET.Element) -> None:
        self.remove(str(el.get("target") or ""))

    # ── Rendering ─────────────────────────────────────────────────

    def to_element(self) -> ET.Element | None:
        return self._element_for(self.root_rid)

    def _element_for(self, rid: str) -> ET.Element | None:
        record = self.records.get(rid)
        if record is None or record.type != "element":
            return None
        tag = f"{{{record.ns}}}{record.name}" if record.ns else record.name
        el = ET.Element(tag)
        for child in self.children(rid):
            child_record = self.records[child]
            if child_record.type == "attr":
                key = (f"{{{child_record.ns}}}{child_record.name}"
                       if child_record.ns else child_record.name)
                el.set(key, child_record.chdata)
        for child in self.children(rid):
            child_record = self.records[child]
            if child_record.type == "element":
                sub = self._element_for(child)
                if sub is not None:
                    el.append(sub)
            elif child_record.type == "text":
                el.text = (el.text or "") + child_record.chdata
        return el

    def to_xml(self) -> str:
        el = self.to_element()
        if el is None:
            return ""
        return ET.tostring(el, encoding="unicode")
