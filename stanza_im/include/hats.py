"""XEP-0317 Hats and XEP-0392 consistent colour generation.

Pure helpers (no Qt, no slixmpp) shared by the client and the UI:

* build the hat URI from the room JID and the title;
* parse the ``<hats/>`` presence payload into ``{uri, title, hue, lang}``;
* build and parse the ``urn:xmpp:hats:commands`` ad-hoc command forms;
* turn a hue angle into an RGB colour with the HSLuv algorithm from XEP-0392.
"""
from __future__ import annotations

import hashlib
import math
from xml.etree import ElementTree as ET

NS_HATS = "urn:xmpp:hats:0"
NS_COMMANDS = "http://jabber.org/protocol/commands"
NS_DATA = "jabber:x:data"
NS_HATS_COMMANDS = "urn:xmpp:hats:commands"
NS_XML = "http://www.w3.org/XML/1998/namespace"

CMD_CREATE = "urn:xmpp:hats:commands:create"
CMD_DESTROY = "urn:xmpp:hats:commands:destroy"
CMD_LIST = "urn:xmpp:hats:commands:list"
CMD_LIST_ASSIGNED = "urn:xmpp:hats:commands:list-assigned"
CMD_ASSIGN = "urn:xmpp:hats:commands:assign"
CMD_UNASSIGN = "urn:xmpp:hats:commands:unassign"

FORM_TYPE = NS_HATS_COMMANDS


def hat_uri(room: str, title: str) -> str:
    """Return a stable hat URI derived from the room JID and the title."""
    key = f"{str(room or '').strip().lower()}\x00{str(title or '').strip()}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return f"urn:xmpp:hats:{digest}"


def parse_hue(value) -> float | None:
    """Parse a ``hue`` attribute/field into an angle in ``[0, 360)``."""
    try:
        hue = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(hue) or math.isinf(hue):
        return None
    return hue % 360.0


def _as_element(obj):
    """Accept an ElementTree element or anything exposing ``.xml``."""
    return getattr(obj, "xml", obj)


def parse_hats(obj) -> list[dict]:
    """Parse the ``<hats/>`` element of a MUC presence stanza."""
    root = _as_element(obj)
    hats_el = root.find(f"{{{NS_HATS}}}hats")
    if hats_el is None:
        return []
    hats: list[dict] = []
    for hat in hats_el.findall(f"{{{NS_HATS}}}hat"):
        uri = str(hat.get("uri") or "")
        title = str(hat.get("title") or "")
        if not uri and not title:
            continue
        hats.append({
            "uri": uri,
            "title": title or uri,
            "hue": parse_hue(hat.get("hue")),
            "lang": str(hat.get(f"{{{NS_XML}}}lang") or ""),
        })
    return hats


def parse_result_form(obj) -> list[dict]:
    """Parse a ``<x type='result'/>`` data form with ``<reported>``+``<item>``."""
    root = _as_element(obj)
    form = None
    for x in root.iter(f"{{{NS_DATA}}}x"):
        if x.get("type") == "result":
            form = x
            break
    if form is None:
        return []
    rows: list[dict] = []
    for item in form.findall(f"{{{NS_DATA}}}item"):
        row: dict = {}
        for field in item.findall(f"{{{NS_DATA}}}field"):
            var = str(field.get("var") or "")
            if not var:
                continue
            value = field.find(f"{{{NS_DATA}}}value")
            row[var] = (value.text or "") if value is not None else ""
        rows.append(row)
    return rows


def command_session(obj) -> tuple[str, str]:
    """Return ``(sessionid, status)`` of an ad-hoc command response."""
    root = _as_element(obj)
    command = root.find(f"{{{NS_COMMANDS}}}command")
    if command is None:
        return "", ""
    return (str(command.get("sessionid") or ""),
            str(command.get("status") or ""))


def build_command(node: str, values: dict | None = None,
                  sessionid: str = "") -> ET.Element:
    """Build an XEP-0050 ``<command/>`` element for a Hats operation.

    With ``values`` the command carries a ``type='submit'`` form; otherwise it
    is a bare ``execute`` request.
    """
    command = ET.Element(f"{{{NS_COMMANDS}}}command")
    command.set("action", "execute")
    command.set("node", node)
    if sessionid:
        command.set("sessionid", sessionid)
    if values is not None:
        form = ET.SubElement(command, f"{{{NS_DATA}}}x")
        form.set("type", "submit")
        ordered: dict = {"FORM_TYPE": FORM_TYPE}
        ordered.update(values)
        for var, value in ordered.items():
            field = ET.SubElement(form, f"{{{NS_DATA}}}field")
            field.set("var", var)
            if var == "FORM_TYPE":
                field.set("type", "hidden")
            val = ET.SubElement(field, f"{{{NS_DATA}}}value")
            val.text = "" if value is None else str(value)
    return command


# ── XEP-0392 HSLuv colour generation ──────────────────────────────────

_M = (
    (3.240969941904521, -1.537383177570093, -0.498610760293),
    (-0.96924363628087, 1.87596750150772, 0.041555057407175),
    (0.055630079696993, -0.20397695888897, 1.056971514242878),
)
_M_INV = (
    (0.41239079926595, 0.35758433938387, 0.18048078840183),
    (0.21263900587151, 0.71516867876775, 0.072192315360733),
    (0.019330818715591, 0.11919477979462, 0.95053215224966),
)
_REF_Y = 1.0
_REF_U = 0.19783000664283
_REF_V = 0.46831999493879
_KAPPA = 903.2962962
_EPSILON = 0.0088564516


def _y_to_l(y: float) -> float:
    if y <= _EPSILON:
        return y / _REF_Y * _KAPPA
    return 116.0 * (y / _REF_Y) ** (1.0 / 3.0) - 16.0


def _l_to_y(l: float) -> float:
    if l <= 8.0:
        return _REF_Y * l / _KAPPA
    return _REF_Y * ((l + 16.0) / 116.0) ** 3


def _get_bounds(l: float):
    sub1 = (l + 16.0) ** 3 / 1560896.0
    sub2 = sub1 if sub1 > _EPSILON else l / _KAPPA
    bounds = []
    for row in _M:
        m1, m2, m3 = row
        for t in (0, 1):
            top1 = (284517.0 * m1 - 94839.0 * m3) * sub2
            top2 = ((838422.0 * m3 + 769860.0 * m2 + 731718.0 * m1)
                    * l * sub2 - 769860.0 * t * l)
            bottom = (632260.0 * m3 - 126452.0 * m2) * sub2 + 126452.0 * t
            bounds.append((top1 / bottom, top2 / bottom))
    return bounds


def _length_of_ray_until_intersect(theta: float, line) -> float:
    slope, intercept = line
    return intercept / (math.sin(theta) - slope * math.cos(theta))


def _max_chroma_for_lh(l: float, h: float) -> float:
    if l <= 0.0:
        return 0.0
    hrad = math.radians(h)
    bounds = _get_bounds(l)
    min_chroma = float("inf")
    for bound in bounds:
        length = _length_of_ray_until_intersect(hrad, bound)
        if length >= 0.0 and length < min_chroma:
            min_chroma = length
    return min_chroma


def _luv_to_xyz(l: float, u: float, v: float):
    if l == 0.0:
        return 0.0, 0.0, 0.0
    var_u = u / (13.0 * l) + _REF_U
    var_v = v / (13.0 * l) + _REF_V
    y = _l_to_y(l)
    x = -(9.0 * y * var_u) / ((var_u - 4.0) * var_v - var_u * var_v)
    z = (9.0 * y - 15.0 * var_v * y - var_v * x) / (3.0 * var_v)
    return x, y, z


def _from_linear(c: float) -> float:
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * c ** (1.0 / 2.4) - 0.055


def _xyz_to_rgb(x: float, y: float, z: float):
    return tuple(_from_linear(row[0] * x + row[1] * y + row[2] * z)
                 for row in _M)


def hsluv_to_rgb(h: float, s: float, l: float):
    """Convert an HSLuv triple (h 0-360, s/l 0-100) to sRGB components."""
    if l > 99.9999999:
        l = 100.0
    elif l < 0.00000001:
        l = 0.0
    max_chroma = _max_chroma_for_lh(l, h % 360.0)
    chroma = max_chroma / 100.0 * s
    hrad = math.radians(h)
    return _xyz_to_rgb(*_luv_to_xyz(
        l, math.cos(hrad) * chroma, math.sin(hrad) * chroma))


def hue_to_color(hue, saturation: float = 100.0,
                 lightness: float = 50.0) -> str:
    """Return ``#rrggbb`` for a hue angle (``None``/invalid → empty string)."""
    angle = parse_hue(hue)
    if angle is None:
        return ""
    r, g, b = hsluv_to_rgb(angle, saturation, lightness)

    def channel(value: float) -> int:
        return max(0, min(255, int(round(value * 255.0))))

    return "#%02x%02x%02x" % (channel(r), channel(g), channel(b))
