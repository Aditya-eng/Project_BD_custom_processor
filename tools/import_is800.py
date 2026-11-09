#!/usr/bin/env python3
"""Import L1C code tables from the official IS-GPS-800J PDF (needs poppler-utils: pdftotext).

usage: import_is800.py <IS-GPS-800J.pdf>  -> model/bdmodel/tables/gps_l1c_table.py

Every value is cross-checked before anything is written:
- the Legendre sequence computed from its definition equals Table 6.2-1 (all 10223 bits);
- for each PRN 1-63 and both L1CP and L1CD, the code built from the Weil index and
  insertion index reproduces the table's initial 24 and final 24 chips (octal);
- each L1CO overlay generated from its polynomial and initial 11 bits reproduces the
  table's final 11 bits after 1800 bits;
- PRN 64-210 (Tables 6.3-1 and 6.3-2, which include QZSS 193-202): the ranging codes
  are checked like PRN 1-63; each additional overlay S1 xor S2 (S1 from the listed
  polynomial, S2 fixed at octal 5001) reproduces both the starting and the ending
  11 symbols.

Errata handled explicitly: IS-GPS-800J Table 3.2-2 (sheet 2) prints the PRN of the
row between 37 and 39 as "3" (visible on the rendered page, not an extraction
artefact). PRN 3 already appears in sheet 1 with different parameters, so that row
is PRN 38; its own initial/final chips are still checked like every other row.
"""
import hashlib
import subprocess
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from bdmodel.gps_l1c import L1C_N, S2_POLY, legendre, overlay_bits, weil_code  # noqa: E402


def sheets(lines, title_re):
    return [i for i, l in enumerate(lines) if re.match(title_re, l.strip())]


def octal_bits(s, nbits):
    return format(int(s, 8), f"0{3 * len(s)}b")[-nbits:]


def main():
    pdf = Path(sys.argv[1])
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True,
                          capture_output=True, text=True).stdout
    lines = [re.sub(r"[ \t]+", " ", l.strip()) for l in text.splitlines()]
    issue = re.search(r"IS-GPS-800([A-Z])\s*\n\s*(\d{2}-[A-Z]{3}-\d{4})", text)

    # Table 6.2-1: 10224 listed bits, the first (0) ignored.
    i0 = sheets(lines, r"^Table 6\.2-1\. Legendre Sequence \(Octal\)$")[-1]
    digits = []
    for l in lines[i0 + 1:]:
        if l.startswith("NOTE"):
            break
        if re.fullmatch(r"([0-7]{8}\s*)+", l):
            digits.append(re.sub(r"\s+", "", l))
    tbl = "".join(format(int(d, 8), "03b") for d in "".join(digits))
    assert len(tbl) == L1C_N + 1 and tbl[0] == "0", len(tbl)
    assert tbl[1:] == "".join(map(str, legendre())), "Legendre table mismatch"

    codes = {}
    prev = None
    heads = (sheets(lines, r"^Table 3\.2-2\.? L1C Ranging Codes Parameter Assignments \(sheet \d of 3\)$")
             + sheets(lines, r"^Table 6\.3-1\.? Additional L1C Ranging Codes Parameter Assignments "
                             r"\(sheet \d of 7\)$"))
    assert len(heads) == 10, heads
    for h in heads:
        for l in lines[h + 1:h + 80]:
            if l.startswith("NOTES"):
                break
            m = re.fullmatch(r"(\d+)\**\s+(\d+)\s+(\d+)\s+([0-7]{8})\s+([0-7]{8})\s+(\d+)\s+(\d+)"
                             r"\s+([0-7]{8})\s+([0-7]{8})", l)
            if m:
                g = m.groups()
                prn = int(g[0])
                row = {"P": (int(g[1]), int(g[2]), g[3], g[4]),
                       "D": (int(g[5]), int(g[6]), g[7], g[8])}
                if prn == 3 and prev == 37:                     # errata, see module docstring
                    assert 3 in codes and codes[3] != row
                    prn = 38
                assert prn not in codes, prn
                codes[prn] = row
                prev = prn
    allp = list(range(1, 64)) + list(range(64, 211))
    assert sorted(codes) == allp, sorted(set(allp) ^ set(codes))
    for prn, comps in codes.items():
        for comp, (w, p, first, last) in comps.items():
            c = "".join(map(str, weil_code(w, p)))
            assert c[:24] == octal_bits(first, 24) and c[-24:] == octal_bits(last, 24), (prn, comp)

    overlay = {}
    for h in sheets(lines, r"^Table 3\.2-3\.? L1CO Overlay Code Parameter Assignments \(sheet \d of 3\)$"):
        for l in lines[h + 1:h + 80]:
            if l.startswith("NOTES"):
                break
            m = re.fullmatch(r"(\d+)\**\s+([0-7]{4})\s+([0-7]{4})\s+([0-7]{4})", l)
            if m:
                overlay[int(m.group(1))] = (int(m.group(2), 8), octal_bits(m.group(3), 11),
                                            octal_bits(m.group(4), 11))
    assert sorted(overlay) == list(range(1, 64)), sorted(set(range(1, 64)) - set(overlay))
    for prn, (poly, init, final) in overlay.items():
        s = overlay_bits(poly, init)
        assert "".join(map(str, s[:11])) == init and "".join(map(str, s[-11:])) == final, prn

    # Table 6.3-2: L1CO = S1 xor S2 for PRN 64-210.
    ext = {}
    heads = sheets(lines, r"^Table 6\.3-2\.? Additional L1CO Overlay Code Parameter Assignments "
                          r"\([Ss]heet \d of 7\)$")
    assert len(heads) == 7, heads
    for h in heads:
        for l in lines[h + 1:h + 80]:
            if l.startswith("NOTES"):
                break
            m = re.fullmatch(r"(\d+)\s+([0-7]{4})" + r"\s+([0-7]{4})" * 4, l)
            if m:
                prn = int(m.group(1))
                assert prn not in ext, prn
                ext[prn] = (int(m.group(2), 8),) + tuple(octal_bits(g, 11) for g in m.groups()[2:])
    assert sorted(ext) == list(range(64, 211)), sorted(set(range(64, 211)) ^ set(ext))
    for prn, (poly, s1, s2, start, end) in ext.items():
        assert poly in (0o5111, 0o5421, 0o5403, 0o6501), prn
        g = [a ^ b for a, b in zip(overlay_bits(poly, s1), overlay_bits(S2_POLY, s2))]
        assert "".join(map(str, g[:11])) == start and "".join(map(str, g[-11:])) == end, prn

    src = f"IS-GPS-800{issue.group(1)} ({issue.group(2)}), PDF sha256 {digest}" if issue else digest
    out = ROOT / "model" / "bdmodel" / "tables" / "gps_l1c_table.py"
    body = [f"# Generated by tools/import_is800.py from {src}, Tables 3.2-2, 3.2-3, 6.3-1 and 6.3-2. Do not edit.",
            "# L1C_CODES[prn][component] = (Weil index w, insertion index p, first 24 chips octal, last 24 octal)",
            "L1C_CODES = {"]
    body += [f"    {p}: {{\"P\": {c['P']}, \"D\": {c['D']}}}," for p, c in sorted(codes.items())]
    body += ["}", "", "# L1CO[prn] = (polynomial 1,m10..m1,1 as int, initial 11 bits, final 11 bits)",
             "L1CO = {"]
    body += [f"    {p}: (0o{v[0]:o}, \"{v[1]}\", \"{v[2]}\")," for p, v in sorted(overlay.items())]
    body += ["}", "", "# L1CO_EXT[prn] = (S1 polynomial m11..m0 as int, S1 initial, S2 initial, starting 11,",
             "# ending 11 symbols); PRN 64-210, overlay = S1 xor S2 with S2 polynomial 0o5001",
             "L1CO_EXT = {"]
    body += [f"    {p}: (0o{v[0]:o}, \"{v[1]}\", \"{v[2]}\", \"{v[3]}\", \"{v[4]}\"),"
             for p, v in sorted(ext.items())]
    body += ["}", ""]
    out.write_text("\n".join(body))
    print(f"wrote {out}: Legendre table verified; {2 * len(codes)} ranging codes and {len(overlay) + len(ext)} overlays cross-checked ({src})")


if __name__ == "__main__":
    main()
