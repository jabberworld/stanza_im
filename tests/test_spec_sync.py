"""Spec-sync guard: registered XEP plugins must be documented in XEPs.md.

Run with:
    python3 tests/test_spec_sync.py
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLIENT = os.path.join(_ROOT, "stanza_im", "core", "client.py")
_XEPS = os.path.join(_ROOT, "XEPs.md")
_AGENTS = os.path.join(_ROOT, "AGENTS.md")
_SPEC = os.path.join(_ROOT, "SPEC.md")

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


with open(_CLIENT, encoding="utf-8") as fh:
    client_src = fh.read()
with open(_XEPS, encoding="utf-8") as fh:
    xeps_md = fh.read()
with open(_AGENTS, encoding="utf-8") as fh:
    agents_md = fh.read()
with open(_SPEC, encoding="utf-8") as fh:
    spec_md = fh.read()


# ── Every register_plugin("xep_NNNN") is listed in XEPs.md ────────

registered = {
    int(num) for num in re.findall(r'register_plugin\(\s*["\']xep_(\d{4})["\']',
                                   client_src)
}
documented = {int(num) for num in re.findall(r"XEP-(\d{4})", xeps_md)}

check("client registers XEP plugins", bool(registered))
check("XEPs.md lists XEPs", bool(documented))

missing = sorted(registered - documented)
check("all registered XEPs documented in XEPs.md (%s)"
      % (", ".join("XEP-%04d" % x for x in missing) if missing else "none"),
      not missing)

# The XEP-docs direction is allowed to have extras (non-plugin XEPs used by the
# client), but every row should look like a XEP reference.

extra = sorted(documented - registered)
print("INFO: documented but not a registered plugin:",
      ", ".join("XEP-%04d" % x for x in extra) or "none")


# ── Living-document cross-references stay in place ────────────────

check("AGENTS.md has the Documentation Maintenance rule",
      "## Documentation Maintenance" in agents_md)
check("AGENTS.md references SPEC.md and XEPs.md",
      "SPEC.md" in agents_md and "XEPs.md" in agents_md)
check("SPEC.md references XEPs.md", "XEPs.md" in spec_md)
check("XEPs.md marks itself a living document",
      "living document" in xeps_md.lower())


print("\nAll tests passed ✓" if not FAILURES
      else f"\n{len(FAILURES)} failures")
sys.exit(1 if FAILURES else 0)
