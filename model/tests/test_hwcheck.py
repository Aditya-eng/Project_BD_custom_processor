"""The shared T2.4 scenario (bdmodel.hwcheck) and its comparison, without a simulator."""
import subprocess
import sys
from pathlib import Path

import numpy as np

from bdmodel import hwcheck
from bdmodel.records import RecordType

ROOT = Path(__file__).resolve().parents[2]


def _encode(sc) -> bytes:
    """The C2H stream a correct core would send (records only, any interleaving)."""
    out = bytearray()
    for ch, (dumps, meas) in sc.expected.items():
        for d in dumps:
            w = [(RecordType.DUMP << 28) | (ch << 16) | d[0]] + [v & 0xFFFFFFFF for v in d[1:]] + [0]
            out += np.array(w, dtype="<u4").tobytes()
        for m in meas:
            w = [(RecordType.MEAS << 28) | (ch << 16) | m[0], m[1], m[2] & 0xFFFFFFFF, m[3],
                 m[4], m[5] & 0xFFFFFFFF, m[5] >> 32, 0]
            out += np.array(w, dtype="<u4").tobytes()
    return bytes(out)


def test_samples_le16_layout():
    sc = hwcheck.Scenario([[1, -1], [-8, 7], [0, 3], [2, -2]])
    assert sc.samples_le16() == bytes([0x81, 0x20, 0x7F, 0xE3])


def test_compare_accepts_exact_and_rejects_corruption():
    sc = hwcheck.build(n=6000, cuts=(2000, 4000))
    good = _encode(sc)
    assert hwcheck.compare(sc, good) == []
    assert hwcheck.compare(sc, good + bytes(32)) == []          # a pad record is ignored
    bad = bytearray(good)
    bad[4] ^= 1                                                  # one bit of the first record
    assert hwcheck.compare(sc, bytes(bad)) != []
    assert hwcheck.compare(sc, good[:-32]) != []                  # a record missing


def test_build_is_deterministic_and_scales():
    a, b = hwcheck.build(n=4000, cuts=(1600, 3200)), hwcheck.build(n=4000, cuts=(1600, 3200))
    assert a.ops == b.ops and a.expected == b.expected
    big = hwcheck.build(n=4000, cuts=(1600, 3200), nch=12)
    assert sorted(big.expected) == list(range(12))


def test_harness_dry_run():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "hw_bitexact.py"), "--dry-run",
                        "--samples", "4000"], capture_output=True, text=True, check=True)
    assert "4 channels, 4000 samples" in r.stdout
