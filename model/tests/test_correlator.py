"""The vectorized correlator must equal a literal per-sample reading of the
contract in bdmodel/correlator.py (the same reading the RTL implements)."""
import numpy as np
import pytest

from bdmodel.correlator import COS_LUT, M32, SIN_LUT, TrackChannel, wrap_s32
from bdmodel.gps_ca import ca_code


def scalar_reference(code, samples, carr_fcw, code_fcw, D, state, tics=()):
    L = len(code)
    sign = 1 - 2 * code.astype(int)
    cp, cyc, frac, chip, ep = state
    acc = [0] * 6
    dumps, meas = [], []
    for k, s in enumerate(samples):
        s = int(s)
        if k in tics:
            meas.append((k, cp, wrap_s32(cyc), frac, chip, ep))
        idx = cp >> 27
        i_v, q_v = s * int(COS_LUT[idx]), -s * int(SIN_LUT[idx])
        e = chip + ((frac + D) >> 32)
        e = 0 if e == L else e
        late_dec = 1 if frac < D else 0
        l = L - 1 if (late_dec and chip == 0) else chip - late_dec
        for j, tap in enumerate((e, chip, l)):
            acc[2 * j] += sign[tap] * i_v
            acc[2 * j + 1] += sign[tap] * q_v
        tot = cp + carr_fcw
        cyc += tot >> 32
        cp = tot & M32
        f2 = frac + code_fcw
        frac = f2 & M32
        if f2 >> 32:
            if chip == L - 1:
                chip = 0
                ep = (ep + 1) & 0xFFFF
                dumps.append((k, ep, *[wrap_s32(a) for a in acc]))
                acc = [0] * 6
            else:
                chip += 1
    return dumps, meas, acc


@pytest.mark.parametrize("seed", range(4))
def test_vectorized_matches_scalar(seed):
    rng = np.random.default_rng(seed)
    code = ca_code(int(rng.integers(1, 33)))
    n = 9000
    samples = rng.integers(-3, 4, n)
    carr_fcw = wrap_s32(int(rng.integers(-2**31, 2**31)))
    code_fcw = int(rng.integers(2**28, 2**30))
    D = int(rng.integers(0, 2**32))
    chip0 = int(rng.integers(0, 1023))
    cp0 = int(rng.integers(0, 2**32))
    frac0 = int(rng.integers(0, 2**32))
    tics = sorted(set(int(x) for x in rng.integers(0, n, 5)))

    ch = TrackChannel(code, carr_fcw=carr_fcw, code_fcw=code_fcw, half_spacing=D)
    ch.load(cp0, frac0, chip0)
    dumps, meas = [], []
    # Split into uneven blocks to exercise state carry-over.
    cuts = [0, 1, 777, 4000, 4001, n]
    for a, b in zip(cuts[:-1], cuts[1:]):
        dd, mm = ch.process(samples[a:b], [t - a for t in tics if a <= t < b])
        dumps += dd
        meas += mm

    ref_d, ref_m, ref_acc = scalar_reference(code, samples, carr_fcw, code_fcw, D,
                                             (cp0, 0, frac0, chip0, 0), tics)
    assert len(dumps) == len(ref_d) > 0
    for d, r in zip(dumps, ref_d):
        assert (d.sample_index, d.epoch, d.ie, d.qe, d.ip, d.qp, d.il, d.ql) == r
    assert [(m.sample_index, m.carr_phase, m.carr_cycles, m.code_frac, m.chip_idx, m.epoch)
            for m in meas] == ref_m
    assert list(ch.acc) == ref_acc


def test_samples_to_epoch_end_lands_on_dump():
    ch = TrackChannel(ca_code(3), carr_fcw=123456789, code_fcw=274_000_000)
    ch.load(0, 2**31, 1000)
    m = ch.samples_to_epoch_end()
    dumps, _ = ch.process(np.ones(m, dtype=np.int64))
    assert len(dumps) == 1 and dumps[0].sample_index == m - 1


def test_lut_is_symmetric_and_bounded():
    assert np.all(np.abs(COS_LUT) <= 15) and np.all(np.abs(SIN_LUT) <= 15)
    assert np.array_equal(COS_LUT, COS_LUT[::-1])
    assert np.array_equal(SIN_LUT[:16], -SIN_LUT[16:])
