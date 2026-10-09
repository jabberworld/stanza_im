"""XEP-0394 Message Markup — structured markup rendered to HTML.

Unlike XEP-0393 (markup embedded in the body), XEP-0394 keeps the message
``<body/>`` as the single source of truth and carries the styling in a
separate ``<markup xmlns='urn:xmpp:markup:0'/>`` element whose ``start``/
``end`` attributes index the body in unicode code points.

Supported elements: ``<span>`` (with ``<emphasis/>``/``<strong/>``/``<code/>``/
``<deleted/>`` children), ``<bcode/>`` (code block), ``<list>``/``<li>`` and
``<bquote/>`` (blockquote, nestable).  Unknown elements/attributes are silently
ignored so future extensions never break rendering.

The body text is handed to the caller's *fragment* callback for plain regions,
so the surrounding pipeline (escaping, URL linking, emoticons) stays in one
place.  Leading quote/list markers (``>``/``*``) are stripped from the body for
presentation.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

from stanza_im.include.utils import escape_html

MARKUP_NS = "urn:xmpp:markup:0"

_SPAN_TYPES = ("emphasis", "strong", "code", "deleted")

_CODE_STYLE = ("font-family:monospace;background:rgba(127,127,127,0.18);"
               "padding:0 2px;border-radius:3px;")
_PRE_STYLE = ("font-family:monospace;white-space:pre-wrap;word-wrap:break-word;"
              "margin:2px 0;")
_QUOTE_STYLE = ("margin:2px 0;padding-left:8px;"
                "border-left:2px solid rgba(127,127,127,0.5);")
_LIST_STYLE = "margin:2px 0;padding-left:20px;"
_DELETED_STYLE = "text-decoration:line-through;"

_LIST_MARKERS = "*-+"


def _int(value) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def parse_message(msg_or_xml) -> dict | None:
    """Parse the ``<markup/>`` element of a message into a plain dict.

    Accepts a slixmpp message (uses ``msg.xml``) or an ElementTree element.
    Returns ``None`` when there is no markup or it carries nothing usable.
    """
    xml = getattr(msg_or_xml, "xml", msg_or_xml)
    if xml is None:
        return None
    markup = xml.find("{%s}markup" % MARKUP_NS)
    if markup is None:
        return None
    spans: list[dict] = []
    blocks: list[dict] = []
    for child in list(markup):
        tag = child.tag
        if tag == "{%s}span" % MARKUP_NS:
            start = _int(child.get("start"))
            end = _int(child.get("end"))
            types = [name for name in _SPAN_TYPES
                     if child.find("{%s}%s" % (MARKUP_NS, name)) is not None]
            if start is not None and end is not None and types:
                spans.append({"start": start, "end": end, "types": types})
        elif tag == "{%s}bcode" % MARKUP_NS:
            start = _int(child.get("start"))
            end = _int(child.get("end"))
            if start is not None and end is not None:
                blocks.append({"start": start, "end": end, "type": "bcode",
                               "language": str(child.get("language") or "")})
        elif tag == "{%s}list" % MARKUP_NS:
            start = _int(child.get("start"))
            end = _int(child.get("end"))
            items = [x for x in (_int(li.get("start"))
                                 for li in child.findall("{%s}li" % MARKUP_NS))
                     if x is not None]
            if start is not None and end is not None and items:
                ordered = str(child.get("ordered") or "").lower() == "true"
                blocks.append({"start": start, "end": end, "type": "list",
                               "ordered": ordered, "items": sorted(items)})
        elif tag == "{%s}bquote" % MARKUP_NS:
            start = _int(child.get("start"))
            end = _int(child.get("end"))
            if start is not None and end is not None:
                blocks.append({"start": start, "end": end, "type": "bquote"})
    if not spans and not blocks:
        return None
    return {"spans": spans, "blocks": blocks}


def render(body: str, markup: dict, fragment) -> str:
    """Render *body* with XEP-0394 *markup* to HTML.

    *fragment(raw)->html* renders plain-text regions (escape + URLs +
    emoticons).  Ranges are clamped to the body; malformed ones are dropped.
    """
    if not isinstance(body, str):
        body = "" if body is None else str(body)
    if not markup:
        return fragment(body)
    length = len(body)
    spans = _normalize_spans(markup.get("spans"), length)
    blocks = _normalize_blocks(markup.get("blocks"), length)
    if not spans and not blocks:
        return fragment(body)
    removed = _stripped_indices(body, blocks)
    if removed:
        stripped, old_to_new = _apply_strip(body, removed)
        spans = [_remap(s, old_to_new) for s in spans]
        blocks = [_remap(b, old_to_new) for b in blocks]
        body = stripped
    return _render_range(body, 0, len(body), spans, blocks, fragment)


# ── normalization ────────────────────────────────────────────────

def _normalize_spans(spans, length: int) -> list[dict]:
    out: list[dict] = []
    for span in spans or ():
        try:
            start = max(0, int(span["start"]))
            end = min(length, int(span["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        if start >= end:
            continue
        types = [t for t in span.get("types", ()) if t in _SPAN_TYPES]
        if types:
            out.append({"start": start, "end": end, "types": types})
    return out


def _normalize_blocks(blocks, length: int) -> list[dict]:
    out: list[dict] = []
    for block in blocks or ():
        try:
            start = max(0, int(block["start"]))
            end = min(length, int(block["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        if start >= end:
            continue
        kind = block.get("type")
        if kind not in ("bcode", "bquote", "list"):
            continue
        norm = {"start": start, "end": end, "type": kind}
        if kind == "bcode":
            norm["language"] = str(block.get("language") or "")
        elif kind == "list":
            items = sorted(x for x in (block.get("items") or ())
                           if start <= x < end)
            if not items:
                continue
            norm["items"] = items
            norm["ordered"] = bool(block.get("ordered"))
        out.append(norm)
    return out


def _remap(item: dict, old_to_new) -> dict:
    new = dict(item)
    new["start"] = old_to_new[item["start"]]
    new["end"] = old_to_new[item["end"]]
    if new.get("type") == "list":
        new["items"] = [old_to_new[x] for x in item.get("items", ())]
    return new


# ── marker stripping ─────────────────────────────────────────────

def _stripped_indices(body: str, blocks) -> set[int]:
    """Original indices to drop: one quote/list marker per line/item/level."""
    removed: set[int] = set()
    # Outer blocks first so a nested quote strips one level at a time.
    ordered = sorted(blocks, key=lambda b: (b["start"], -b["end"]))
    for block in ordered:
        if block["type"] == "bquote":
            for line_start in _line_starts(body, block["start"], block["end"]):
                _strip_marker(body, removed, line_start, block["end"], ">")
        elif block["type"] == "list":
            for item_start in block["items"]:
                _strip_marker(body, removed, item_start, block["end"],
                              _LIST_MARKERS)
    return removed


def _line_starts(body: str, start: int, end: int):
    yield start
    for i in range(start, end - 1):
        if body[i] == "\n":
            yield i + 1


def _strip_marker(body: str, removed: set[int], pos: int, end: int,
                  markers: str) -> None:
    j = pos
    while j < end and j in removed:
        j += 1
    if j >= end or body[j] not in markers:
        return
    removed.add(j)
    k = j + 1
    if k < end and k not in removed and body[k] == " ":
        removed.add(k)


def _apply_strip(body: str, removed: set[int]) -> tuple[str, list[int]]:
    kept: list[str] = []
    old_to_new = [0] * (len(body) + 1)
    for i, ch in enumerate(body):
        old_to_new[i] = len(kept)
        if i not in removed:
            kept.append(ch)
    old_to_new[len(body)] = len(kept)
    return "".join(kept), old_to_new


# ── rendering ────────────────────────────────────────────────────

def _render_range(body: str, start: int, end: int, spans, blocks,
                  fragment, exclude: dict | None = None) -> str:
    here = _top_level_blocks(blocks, start, end, exclude)
    out: list[str] = []
    pos = start
    for block in here:
        if block["start"] < pos:
            continue
        out.append(_render_inline(body, pos, block["start"], spans, fragment))
        out.append(_render_block(body, block, spans, blocks, fragment))
        pos = block["end"]
    out.append(_render_inline(body, pos, end, spans, fragment))
    return "".join(out)


def _top_level_blocks(blocks, start: int, end: int,
                      exclude: dict | None = None) -> list[dict]:
    inside = [b for b in blocks
              if b is not exclude and b["start"] >= start and b["end"] <= end]
    top: list[dict] = []
    for block in inside:
        if any(other is not block
               and other["start"] <= block["start"]
               and block["end"] <= other["end"]
               and (other["start"] < block["start"]
                    or other["end"] > block["end"])
               for other in inside):
            continue
        top.append(block)
    top.sort(key=lambda b: b["start"])
    return top


def _render_block(body: str, block: dict, spans, blocks, fragment) -> str:
    start, end, kind = block["start"], block["end"], block["type"]
    if kind == "bcode":
        return '<pre style="%s">%s</pre>' % (
            _PRE_STYLE, escape_html(body[start:end]))
    if kind == "bquote":
        bend = end
        while bend > start and body[bend - 1] == "\n":
            bend -= 1
        inner = _render_range(body, start, bend, spans, blocks, fragment,
                              exclude=block)
        return '<blockquote style="%s">%s</blockquote>' % (_QUOTE_STYLE, inner)
    if kind == "list":
        items = block.get("items") or [start]
        parts: list[str] = []
        for index, item_start in enumerate(items):
            item_end = items[index + 1] if index + 1 < len(items) else end
            text_end = item_end
            while text_end > item_start and body[text_end - 1] == "\n":
                text_end -= 1
            inner = _render_inline(body, item_start, text_end, spans, fragment)
            parts.append("<li>%s</li>" % inner)
        tag = "ol" if block.get("ordered") else "ul"
        return '<%s style="%s">%s</%s>' % (
            tag, _LIST_STYLE, "".join(parts), tag)
    return _render_inline(body, start, end, spans, fragment)


def _render_inline(body: str, start: int, end: int, spans, fragment,
                   exclude: dict | None = None) -> str:
    if start >= end:
        return ""
    here = _top_level_spans(spans, start, end, exclude)
    out: list[str] = []
    pos = start
    for span in here:
        if span["start"] < pos:
            continue
        out.append(fragment(body[pos:span["start"]]))
        out.append(_render_span(body, span, spans, fragment))
        pos = span["end"]
    out.append(fragment(body[pos:end]))
    return "".join(out)


def _top_level_spans(spans, start: int, end: int,
                     exclude: dict | None = None) -> list[dict]:
    inside = [s for s in spans
              if s is not exclude and s["start"] >= start and s["end"] <= end]
    top: list[dict] = []
    for span in inside:
        if any(other is not span
               and other["start"] <= span["start"]
               and span["end"] <= other["end"]
               and (other["start"] < span["start"]
                    or other["end"] > span["end"])
               for other in inside):
            continue
        top.append(span)
    top.sort(key=lambda s: s["start"])
    return top


def _render_span(body: str, span: dict, spans, fragment) -> str:
    types = span["types"]
    raw = body[span["start"]:span["end"]]
    if "code" in types:
        inner = escape_html(raw)
    else:
        inner = _render_inline(body, span["start"], span["end"], spans, fragment,
                               exclude=span)
    for kind in reversed([t for t in _SPAN_TYPES if t in types]):
        if kind == "strong":
            inner = "<strong>%s</strong>" % inner
        elif kind == "emphasis":
            inner = "<em>%s</em>" % inner
        elif kind == "code":
            inner = '<code style="%s">%s</code>' % (_CODE_STYLE, inner)
        elif kind == "deleted":
            inner = '<span style="%s">%s</span>' % (_DELETED_STYLE, inner)
    return inner
