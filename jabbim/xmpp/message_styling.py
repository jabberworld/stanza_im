"""XEP-0393 Message Styling — plain-text markup parsed into HTML.

Implements the Stable v1.1.1 rules: block parsing first (preformatted
blocks, quotations, plain lines), then lazy span matching (strong ``*``,
emphasis ``_``, strike ``~``, preformatted `` ` ``).  Plain-text regions
are handed to the caller's *fragment* callback so the surrounding pipeline
(escaping, URL linking, emoticons) stays in one place; preformatted content
is emitted verbatim (escaped only), per §6.1.2/§6.2.5.
"""
from __future__ import annotations

from jabbim.include.utils import escape_html

_STRONG = "*"
_EMPH = "_"
_STRIKE = "~"
_CODE = "`"

_SPAN_TAGS = {_STRONG: "strong", _EMPH: "em", _STRIKE: "s"}

_CODE_STYLE = ("font-family:monospace;background:rgba(127,127,127,0.18);"
               "padding:0 2px;border-radius:3px;")
_PRE_STYLE = ("font-family:monospace;white-space:pre-wrap;word-wrap:break-word;"
              "margin:2px 0;")
_QUOTE_STYLE = ("margin:2px 0;padding-left:8px;"
                "border-left:2px solid rgba(127,127,127,0.5);")

_PRE_OPEN = "```"


def render(body: str, fragment) -> str:
    """Parse *body* (XEP-0393) into HTML using *fragment(raw)->html* for
    plain-text regions.
    """
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    return _parse_blocks(normalized, fragment)


def _parse_blocks(text: str, fragment) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    prev_was_plain = False
    while i < n:
        line = lines[i]
        if line.startswith(_PRE_OPEN):
            buf: list[str] = []
            i += 1
            while i < n and lines[i].strip() != _PRE_OPEN:
                buf.append(lines[i])
                i += 1
            i += 1  # skip the closing fence (may be past the end)
            out.append('<pre style="%s">%s</pre>'
                       % (_PRE_STYLE, escape_html("\n".join(buf))))
            prev_was_plain = False
        elif line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                inner = lines[i][1:]
                if inner and inner[0].isspace():
                    inner = inner[1:]
                buf.append(inner)
                i += 1
            inner_html = _parse_blocks("\n".join(buf), fragment)
            out.append('<blockquote style="%s">%s</blockquote>'
                       % (_QUOTE_STYLE, inner_html))
            prev_was_plain = False
        else:
            if prev_was_plain:
                out.append("<br>")
            out.append(_parse_spans(line, fragment))
            prev_was_plain = True
            i += 1
    return "".join(out)


def _parse_spans(text: str, fragment) -> str:
    """Parse the span directives inside a single plain block line."""
    parts: list[str] = []
    buf: list[str] = []
    at_block_start = True
    i, n = 0, len(text)

    def flush() -> None:
        if buf:
            parts.append(fragment("".join(buf)))
            buf.clear()

    while i < n:
        ch = text[i]
        if ch in _SPAN_TAGS or ch == _CODE:
            if _open_valid(text, i, at_block_start, ch):
                close = _find_close(text, i, ch)
                if close is not None:
                    flush()
                    inner = text[i + 1:close]
                    if ch == _CODE:
                        parts.append('<code style="%s">%s%s%s</code>'
                                     % (_CODE_STYLE, ch,
                                        escape_html(inner), ch))
                    else:
                        tag = _SPAN_TAGS[ch]
                        parts.append("<%s>%s%s%s</%s>" % (
                            tag, ch, _parse_spans(inner, fragment), ch, tag))
                    i = close + 1
                    at_block_start = False
                    continue
            buf.append(ch)
            i += 1
            at_block_start = False
            continue
        buf.append(ch)
        at_block_start = ch.isspace()
        i += 1
    flush()
    return "".join(parts)


def _open_valid(text: str, i: int, at_block_start: bool, ch: str) -> bool:
    """An opening directive sits at the block start, after whitespace or
    after another opening directive, and is not followed by whitespace."""
    if not at_block_start:
        return False
    if i + 1 >= len(text):
        return False
    return not text[i + 1].isspace()


def _find_close(text: str, start: int, ch: str) -> int | None:
    """Return the lazily-matched closing directive index.

    A close preceded by whitespace is ignored (§6.2).  A close directly
    adjacent to the opening makes "neither directive valid" (§6.2), which
    invalidates the opening entirely — this keeps ``**``/``***`` literal.
    """
    j = start + 1
    while j < len(text):
        if text[j] != ch:
            j += 1
            continue
        if j == start + 1:
            return None
        if text[j - 1].isspace():
            j += 1
            continue
        return j
    return None