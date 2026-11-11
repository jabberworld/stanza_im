#!/usr/bin/env python3
"""Install Stanza IM's desktop entry and xmpp: URI handler for the current user."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "resources" / "stanza-im.desktop"
ICON = ROOT / "resources" / "images" / "scalable" / "apps" / "stanza-im.svg"
APP_ID = "stanza-im"


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or
                (Path.home() / ".local" / "share"))


def desktop_path() -> Path:
    return data_home() / "applications" / f"{APP_ID}.desktop"


def icon_path() -> Path:
    return data_home() / "icons" / "hicolor" / "scalable" / "apps" / \
        f"{APP_ID}.svg"


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') \
        .replace("`", "\\`").replace("$", "\\$") + '"'


def launch_command() -> tuple[str, str]:
    """Return ``(Exec value, TryExec value)`` for this installation."""
    found = shutil.which("stanza-im")
    if found:
        return _quote(found), found
    return f"{_quote(sys.executable)} {_quote(str(ROOT / 'main.py'))}", ""


def desktop_contents() -> str:
    exec_value, try_exec = launch_command()
    text = TEMPLATE.read_text(encoding="utf-8")
    lines = []
    for line in text.splitlines():
        if line.startswith("Exec="):
            lines.append(f"Exec={exec_value} %U")
        elif line.startswith("TryExec="):
            if try_exec:
                lines.append(f"TryExec={try_exec}")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def _run(*args) -> None:
    try:
        subprocess.run(args, check=False, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except OSError:
        pass


def install() -> int:
    if not TEMPLATE.is_file() or not ICON.is_file():
        print(f"Missing template or icon under {ROOT}", file=sys.stderr)
        return 1
    desktop = desktop_path()
    icon = icon_path()
    desktop.parent.mkdir(parents=True, exist_ok=True)
    icon.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(desktop_contents(), encoding="utf-8")
    os.chmod(desktop, 0o644)
    shutil.copyfile(ICON, icon)
    os.chmod(icon, 0o644)
    _run("update-desktop-database", str(data_home() / "applications"))
    _run("gtk-update-icon-cache", "-f", "-t",
         str(data_home() / "icons" / "hicolor"))
    _run("xdg-mime", "default", f"{APP_ID}.desktop",
         "x-scheme-handler/xmpp")
    print(f"Installed {desktop}")
    print(f"Installed {icon}")
    print("Registered x-scheme-handler/xmpp for stanza-im.desktop")
    return 0


def uninstall() -> int:
    for path in (desktop_path(), icon_path()):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    _run("update-desktop-database", str(data_home() / "applications"))
    _run("gtk-update-icon-cache", "-f", "-t",
         str(data_home() / "icons" / "hicolor"))
    print("Removed the Stanza IM desktop entry and icon")
    print("If xdg-mime still points to it, choose another handler with "
          "xdg-mime default")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true",
                        help="remove the user desktop entry and icon")
    parser.add_argument("--check", action="store_true",
                        help="print the generated desktop entry without writing")
    args = parser.parse_args(argv)
    if args.check:
        print(desktop_contents())
        print(f"# desktop: {desktop_path()}")
        print(f"# icon: {icon_path()}")
        return 0
    return uninstall() if args.uninstall else install()


if __name__ == "__main__":
    raise SystemExit(main())
