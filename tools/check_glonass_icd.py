#!/usr/bin/env python3
"""Check model/bdmodel/glonass.py against the GLONASS ICD L1, L2 Edition 5.1 PDF
(needs poppler-utils: pdftotext). Writes nothing: G1 has no per-satellite code tables.

usage: check_glonass_icd.py <ICD_GLONASS_eng_v5.1.pdf>

Checks:
- Table 3.1: all 14 L1 and L2 frequencies equal f01 + K*df1 and f02 + K*df2 (3.3.1.1), and
  K = -7..+6 is the set the table lists;
- 3.3.2.1: G(X) = 1 + X5 + X9, initial vector 111111111, output at the 7th stage, and the
  generated code starts with the printed 111111100 (the feedback stages are from Fig. 3.2;
  the first chips alone do not separate G(X) from its reciprocal);
- 3.3.2.2: the printed time mark equals the first 30 chips generated from g(x) = 1 + x3 + x5,
  and the 31st chip is 0, the idle bit that 3.3.2.2 says completes the sequence.
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from bdmodel import glonass as glo  # noqa: E402


def main():
    pdf = Path(sys.argv[1])
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True,
                          capture_output=True, text=True).stdout
    assert re.search(r"Edition 5\.1 2008", text)

    rows = {}
    for m in re.finditer(r"^\s*(-?\d{2})\s+(\d{4},\d+)\s+(-?\d{2})\s+(\d{4},\d+)\s*$", text, re.M):
        k1, f1, k2, f2 = int(m.group(1)), float(m.group(2).replace(",", ".")), \
            int(m.group(3)), float(m.group(4).replace(",", "."))
        assert k1 == k2 and k1 not in rows, k1
        rows[k1] = (f1, f2)
    assert sorted(rows) == list(glo.K_RANGE), sorted(rows)
    for k, (f1, f2) in rows.items():
        assert abs(f1 * 1e6 - glo.carrier_hz(k)) < 1e-3, (k, f1)
        assert abs(f2 * 1e6 - (1246e6 + k * 437.5e3)) < 1e-3, (k, f2)

    assert re.search(r"G\(X\)\s*=\s*1\s*\+\s*X5\s*\+\s*X9", text)
    assert "initialization vector to generate this\nsequence is (111111111)" in text
    assert re.search(r"output\s+of 7th stage of the 9-stage shift register", text)
    m = re.search(r"first\s+character in the group (\d{9})", text)
    assert m and "".join(map(str, glo.ranging_code()[:9])) == m.group(1), m and m.group(1)

    assert re.search(r"g\(x\)\s*=\s*1\s*\+\s*x3\s*\+\s*x5", text)
    m = re.search(r"may be shown as ([01]{30})", text)
    assert m and m.group(1) == glo.TIME_MARK
    full = glo.time_mark_from_polynomial(31)
    assert full[:30] == glo.TIME_MARK and full[30] == "0"

    print(f"GLONASS ICD 5.1 (sha256 {digest}): Table 3.1 (14 x 2 frequencies), ranging code "
          f"and time mark agree with bdmodel/glonass.py")


if __name__ == "__main__":
    main()
