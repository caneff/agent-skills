#!/usr/bin/env python3
"""Base hex -> full Peacock .vscode/settings.json fragment.

Encodes the recipe so nobody has to rediscover it:
  - peacock.remoteColor is REQUIRED for WSL/SSH/remote windows; without it
    Peacock's cleanup strips workbench.colorCustomizations on every save.
  - foreground per element is chosen by luminance for contrast.

Usage: uv run derive.py "#9580ff"   (prints JSON to stdout)
"""
import json
import sys


def _clamp(x): return max(0, min(255, round(x)))


def _rgb(hex_str):
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb): return "#{:02x}{:02x}{:02x}".format(*(_clamp(c) for c in rgb))


def _mix(rgb, target, t):  # t=0 -> rgb, t=1 -> target
    return tuple(c + (target[i] - c) * t for i, c in enumerate(rgb))


def lighten(rgb, t): return _mix(rgb, (255, 255, 255), t)
def darken(rgb, t): return _mix(rgb, (0, 0, 0), t)


def readable_fg(rgb):
    # WCAG relative luminance; dark ink on light bg, light ink on dark bg.
    r, g, b = (c / 255 for c in rgb)
    lin = [((v + 0.055) / 1.055) ** 2.4 if v > 0.03928 else v / 12.92 for v in (r, g, b)]
    lum = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.4152 * lin[2]
    return "#15141b" if lum > 0.35 else "#f8f8f2"


def build(base_hex):
    base = _rgb(base_hex)
    base_h = _hex(base)
    activity = lighten(base, 0.20)          # activity bar a touch lighter
    activity_h = _hex(activity)
    hover_h = _hex(darken(base, 0.15))      # status item hover a touch darker
    fg = readable_fg(base)                   # ink on the base color
    fg_activity = readable_fg(activity)      # ink on the (lighter) activity bar
    fg99 = fg + "99"                         # inactive = 60% alpha
    return {
        "peacock.color": base_h,
        "peacock.remoteColor": base_h,       # <-- the bit everyone forgets
        "peacock.showColorInStatusBar": True,
        "workbench.colorCustomizations": {
            "activityBar.activeBackground": activity_h,
            "activityBar.background": activity_h,
            "activityBar.foreground": fg_activity,
            "activityBar.inactiveForeground": fg_activity + "99",
            "activityBarBadge.background": _hex(darken(base, 0.25)),
            "activityBarBadge.foreground": readable_fg(darken(base, 0.25)),
            "commandCenter.border": fg99,
            "sash.hoverBorder": activity_h,
            "statusBar.background": base_h,
            "statusBar.foreground": fg,
            "statusBarItem.hoverBackground": hover_h,
            "statusBarItem.remoteBackground": base_h,
            "statusBarItem.remoteForeground": fg,
            "titleBar.activeBackground": base_h,
            "titleBar.activeForeground": fg,
            "titleBar.inactiveBackground": base_h + "99",
            "titleBar.inactiveForeground": fg99,
        },
    }


def _demo():
    # ponytail: one runnable check on the money path (contrast + remoteColor).
    out = build("#9580ff")
    assert out["peacock.remoteColor"] == "#9580ff", "remoteColor must mirror base"
    assert out["workbench.colorCustomizations"]["statusBar.foreground"] == "#15141b", "dark ink on light purple"
    dark = build("#22212c")  # near-black base -> light ink
    assert dark["workbench.colorCustomizations"]["statusBar.foreground"] == "#f8f8f2", "light ink on dark base"
    assert _hex(lighten((0, 0, 0), 0.5)) == "#808080"
    print("ok")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--demo":
        _demo()
    elif len(sys.argv) == 2:
        print(json.dumps(build(sys.argv[1]), indent=2))
    else:
        sys.exit("usage: derive.py '#RRGGBB'   |   derive.py --demo")
