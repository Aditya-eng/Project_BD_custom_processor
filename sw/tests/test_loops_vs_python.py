"""The C++ tracking loop must reproduce the Python reference loop exactly when
both see the same correlator dumps (replayed open-loop from a Python run)."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "model"))

from bdmodel.acquisition import acquire  # noqa: E402
from bdmodel.records import pack_dump  # noqa: E402
from bdmodel.signal_sim import FrontEnd, SatSignal, generate  # noqa: E402
from bdmodel.tracking import LoopConfig, Tracker  # noqa: E402

BIN = ROOT / "sw" / "build" / "bd_loopcheck"
FE = FrontEnd(fs_hz=16.0e6, f_if_hz=4.0e6)


@pytest.fixture(scope="module")
def samples():
    rng = np.random.default_rng(2)
    return generate([SatSignal(9, 44.0, -1777.0, 512.3, 0.4, 0.0, rng.choice([-1, 1], 30))], FE, 0.4)


@pytest.mark.parametrize("delay", [0, 1])
def test_cpp_loop_matches_python(samples, tmp_path, delay):
    if not BIN.exists():
        pytest.skip("build sw/ first (make test-sw)")
    a = acquire(samples, 9, FE.fs_hz, FE.f_if_hz)
    tr = Tracker(9, FE.fs_hz, FE.f_if_hz, a.doppler_hz, a.code_phase_chips,
                 LoopConfig(update_delay_epochs=delay))
    initial = (tr.ch.carr_fcw, tr.ch.code_fcw)    # set by the constructor
    applied = []                                   # every command the loop issues afterwards
    orig = tr._apply
    tr._apply = lambda c, k: (applied.append(_fcws((c, k), FE)), orig(c, k))
    tr.run(samples)
    dumps = [type("D", (), {"epoch": i + 1, "ie": r.ie, "qe": r.qe, "ip": r.ip, "qp": r.qp,
                            "il": r.il, "ql": r.ql}) for i, r in enumerate(tr.records)]
    f = tmp_path / "dumps.bin"
    f.write_bytes(b"".join(pack_dump(0, d) for d in dumps))
    out = subprocess.run([str(BIN), str(f), repr(FE.fs_hz), repr(FE.f_if_hz), repr(a.doppler_hz),
                          str(delay)], check=True, capture_output=True, text=True).stdout.splitlines()
    init = out[0].split(",")
    assert (int(init[0]), int(init[1])) == initial
    rows = [line.split(",") for line in out[1:]]
    assert len(rows) == len(tr.records) > 300
    cpp_applied = []
    for row, rec in zip(rows, tr.records):
        assert float(row[0]) == rec.carr_freq_hz
        assert float(row[1]) == rec.code_rate_hz
        assert float(row[2]) == rec.pll_err_cyc
        assert float(row[3]) == rec.dll_err_chips
        if row[4] == "1":
            cpp_applied.append((int(row[5]), int(row[6])))
    assert cpp_applied == applied and len(applied) == len(rows) - delay


def _fcws(cmd, fe):
    from bdmodel.correlator import freq_to_fcw, rate_to_fcw
    return freq_to_fcw(cmd[0], fe.fs_hz), rate_to_fcw(cmd[1], fe.fs_hz)
