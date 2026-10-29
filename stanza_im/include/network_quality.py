"""Small, UI-free network quality classification for calls.

The values come from ``AiortcCall.quality_info()``.  Keeping the thresholds
pure makes the call-window icon testable without a live peer connection.
"""
from __future__ import annotations


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def network_quality(info) -> dict:
    """Return ``{level, reason, ...}`` for a call quality snapshot.

    Levels: 0 = no media/unknown, 1 = poor, 2 = weak, 3 = good, 4 = excellent.
    ``reason`` is one of ``unknown``, ``in_loss``, ``out_loss``, ``limited``,
    ``lag`` or ``ok``.
    """
    if not info:
        return {"level": 0, "reason": "unknown"}
    out_loss = max(0.0, _number(info.get("out_loss_pct")))
    in_loss = max(0.0, _number(info.get("in_loss_pct")))
    lag = max(0.0, _number(info.get("lag_peak_ms")))
    target = max(0, int(_number(info.get("target_bps"))))
    cap = max(0, int(_number(info.get("cap_bps"))))
    remb = max(0, int(_number(info.get("remb_bps"))))
    loss = max(out_loss, in_loss)
    ratio = (target / cap) if cap and target else 1.0

    if loss >= 10.0 or ratio < 0.30:
        level = 1
    elif loss >= 5.0 or ratio < 0.50 or lag >= 250.0:
        level = 2
    elif loss >= 1.0 or ratio < 0.80:
        level = 3
    else:
        level = 4

    if in_loss >= max(5.0, out_loss):
        reason = "in_loss"
    elif out_loss >= 5.0:
        reason = "out_loss"
    elif cap and target and target < cap * 0.60:
        reason = "limited"
    elif lag >= 250.0:
        reason = "lag"
    else:
        reason = "ok"
    return {
        "level": level,
        "reason": reason,
        "out_loss": out_loss,
        "in_loss": in_loss,
        "target_bps": target,
        "cap_bps": cap,
        "remb_bps": remb,
        "lag_peak_ms": lag,
    }
