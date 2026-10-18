"""Tests for the pure SVG transform helper (no Qt).

Run with:
    python3 tests/test_svg_transform.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stanza_im.include import svg_transform as st  # noqa: E402

FAILURES = []


def check(name, cond):
    print(("PASS" if cond else "FAIL") + ": " + name)
    if not cond:
        FAILURES.append(name)


check("a matrix parses",
      st.parse_matrix("matrix(1 0 0 1 10 20)") == (1.0, 0.0, 0.0, 1.0, 10.0, 20.0))
check("commas are accepted", st.parse_matrix("matrix(1,0,0,1,5,7)") ==
      (1.0, 0.0, 0.0, 1.0, 5.0, 7.0))
check("an empty value parses to None", st.parse_matrix("") is None)
check("a non-matrix parses to None", st.parse_matrix("translate(5)") is None)
check("identity is detected", st.is_identity((1, 0, 0, 1, 0, 0)))
check("None is identity", st.is_identity(None))
check("a translation is not identity", not st.is_identity((1, 0, 0, 1, 5, 0)))
check("identity serialises to ''", st.to_str((1, 0, 0, 1, 0, 0)) == "")

# compose(outer, inner): inner is applied first, then outer.
m = st.compose((1, 0, 0, 1, 10, 0), (2, 0, 0, 2, 0, 0))
check("compose applies the inner matrix then the outer", m == (2.0, 0.0, 0.0, 2.0,
                                                               10.0, 0.0))
check("to_str round-trips through parse_matrix",
      st.parse_matrix(st.to_str((2, 0, 0, 2, 10, 0))) == (2.0, 0.0, 0.0, 2.0,
                                                          10.0, 0.0))

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("All svg-transform tests passed.")
