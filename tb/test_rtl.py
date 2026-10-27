"""cocotb testbenches: RTL must match model/bdmodel bit for bit.

Run with `pytest tb/` (builds with Icarus Verilog via the cocotb runner).
"""
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import ReadOnly, RisingEdge  # noqa: E402

from bdmodel.correlator import TrackChannel, freq_to_fcw, rate_to_fcw  # noqa: E402
from bdmodel.gps_ca import CA_CHIP_RATE, G2_TAPS, ca_code  # noqa: E402
from bdmodel.signal_sim import FrontEnd, SatSignal, generate  # noqa: E402

M32 = (1 << 32) - 1


# --------------------------------------------------------------------------
# gps_ca_gen
# --------------------------------------------------------------------------
@cocotb.test()
async def ca_gen_matches_model(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst.value = 1
    dut.init.value = 0
    dut.step.value = 0
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    for prn in range(1, 33):
        t1, t2 = G2_TAPS[prn]
        dut.tap1.value = t1
        dut.tap2.value = t2
        dut.init.value = 1
        await RisingEdge(dut.clk)
        dut.init.value = 0
        dut.step.value = 1
        got = []
        for _ in range(1023):
            await ReadOnly()
            got.append(int(dut.chip.value))
            await RisingEdge(dut.clk)
        dut.step.value = 0
        assert np.array_equal(np.array(got, dtype=np.uint8), ca_code(prn)), f"PRN {prn}"


# --------------------------------------------------------------------------
# track_channel
# --------------------------------------------------------------------------
class Harness:
    def __init__(self, dut):
        self.dut = dut
        self.dumps = []
        self.meas = []

    async def start(self):
        d = self.dut
        cocotb.start_soon(Clock(d.clk, 10, unit="ns").start())
        for sig in (d.sample, d.sample_valid, d.tic, d.load, d.code_we, d.carr_fcw, d.code_fcw, d.boc,
                    d.tdm, d.tdm_slot,
                    d.half_spacing, d.load_carr_phase, d.load_code_frac, d.load_chip_idx,
                    d.code_waddr, d.code_wdata):
            sig.value = 0
        d.rst.value = 1
        await RisingEdge(d.clk)
        await RisingEdge(d.clk)
        d.rst.value = 0
        cocotb.start_soon(self._monitor())

    async def _monitor(self):
        d = self.dut
        while True:
            await RisingEdge(d.clk)
            await ReadOnly()
            if int(d.dump_valid.value):
                self.dumps.append((int(d.dump_epoch.value),
                                   *[getattr(d, n).value.to_signed() for n in ("ie", "qe", "ip", "qp", "il", "ql")]))
            if int(d.meas_valid.value):
                self.meas.append((int(d.meas_carr_phase.value), d.meas_carr_cycles.value.to_signed(),
                                  int(d.meas_code_frac.value), int(d.meas_chip_idx.value),
                                  int(d.meas_epoch.value)))

    async def load_code(self, bits):
        d = self.dut
        d.code_len.value = len(bits)
        d.code_we.value = 1
        for a, b in enumerate(bits):
            d.code_waddr.value = a
            d.code_wdata.value = int(b)
            await RisingEdge(d.clk)
        d.code_we.value = 0

    async def load_state(self, cp, frac, chip):
        d = self.dut
        d.load_carr_phase.value = cp
        d.load_code_frac.value = frac
        d.load_chip_idx.value = chip
        d.load.value = 1
        await RisingEdge(d.clk)
        d.load.value = 0

    async def drive(self, samples, valid, tics, carr_fcw, code_fcw, D):
        d = self.dut
        d.carr_fcw.value = carr_fcw & M32
        d.code_fcw.value = code_fcw
        d.half_spacing.value = D
        for s, v, t in zip(samples, valid, tics):
            d.sample.value = int(s) & 0xF
            d.sample_valid.value = int(v)
            d.tic.value = int(t)
            await RisingEdge(d.clk)
        d.sample_valid.value = 0
        d.tic.value = 0


def model_meas(m):
    return (m.carr_phase, m.carr_cycles, m.code_frac, m.chip_idx, m.epoch)


def model_dump(x):
    return (x.epoch, x.ie, x.qe, x.ip, x.qp, x.il, x.ql)


async def run_segments(h, ch, segments):
    """Drive segments through RTL and model; collect expected outputs."""
    exp_d, exp_m = [], []
    for seg in segments:
        if seg[0] == "load":
            _, cp, frac, chip = seg
            await h.load_state(cp, frac, chip)
            ch.load(cp, frac, chip)
            continue
        _, samples, valid, tics, cfcw, kfcw, D = seg
        await h.drive(samples, valid, tics, cfcw, kfcw, D)
        ch.carr_fcw, ch.code_fcw, ch.half_spacing = cfcw, kfcw, D
        vs = samples[valid.astype(bool)]
        vt = np.cumsum(valid)[(tics & valid).astype(bool)] - 1
        dd, mm = ch.process(vs, list(vt))
        exp_d += [model_dump(x) for x in dd]
        exp_m += [model_meas(x) for x in mm]
    for _ in range(4):
        await RisingEdge(h.dut.clk)
    return exp_d, exp_m


async def _random_stimulus(dut, boc, tdm=False, slot=0):
    """Random samples, control words, bubbles, tics, a short memory code and reloads."""
    rng = np.random.default_rng(int(os.environ.get("TB_SEED", "1")) + 1000 * boc + 2000 * tdm
                                + 4000 * slot)
    h = Harness(dut)
    await h.start()
    dut.boc.value = int(boc)
    dut.tdm.value = int(tdm)
    dut.tdm_slot.value = slot
    code = rng.integers(0, 2, 37).astype(np.uint8)      # short code -> many epochs
    await h.load_code(code)
    ch = TrackChannel(code, boc=boc, tdm=tdm, tdm_slot=slot)
    segs = [("load", int(rng.integers(0, 2**32)), int(rng.integers(0, 2**32)), 11)]
    for k in range(10):
        n = int(rng.integers(1500, 3000))
        segs.append(("run", rng.integers(-8, 8, n), (rng.random(n) < 0.85).astype(np.int64),
                     (rng.random(n) < 0.01).astype(np.int64),
                     int(rng.integers(-2**31, 2**31)), int(rng.integers(2**27, 2**31)),
                     int(rng.integers(0, 2**32))))
        if k in (3, 7):
            segs.append(("load", int(rng.integers(0, 2**32)), int(rng.integers(0, 2**32)),
                         int(rng.integers(0, 37))))
    exp_d, exp_m = await run_segments(h, ch, segs)
    assert len(exp_d) > 20 and len(exp_m) > 5
    assert h.dumps == exp_d
    assert h.meas == exp_m


@cocotb.test()
async def track_channel_random_stimulus(dut):
    await _random_stimulus(dut, boc=False)


@cocotb.test()
async def track_channel_random_stimulus_boc(dut):
    await _random_stimulus(dut, boc=True)


@cocotb.test()
async def track_channel_random_stimulus_tdm(dut):
    await _random_stimulus(dut, boc=False, tdm=True, slot=0)


@cocotb.test()
async def track_channel_random_stimulus_tdm_slot1_boc(dut):
    await _random_stimulus(dut, boc=True, tdm=True, slot=1)


@cocotb.test()
async def track_channel_gps_signal(dut):
    """Simulated 2-bit GPS L1 C/A IF stream with loop-like control-word updates."""
    fe = FrontEnd(fs_hz=4.0e6, f_if_hz=1.1e6)
    sat = SatSignal(7, 50.0, 2100.0, 100.25, 0.2)
    x = generate([sat], fe, 0.004, seed=3).astype(np.int64)
    h = Harness(dut)
    await h.start()
    code = ca_code(7)
    await h.load_code(code)
    ch = TrackChannel(code)
    segs = [("load", 0, int(0.25 * 2**32), 100)]
    D = 1 << 31
    pos = 0
    for k, n in enumerate([4000, 4000, 4000, len(x) - 12000]):
        fd = 2100.0 + 3.0 * k
        segs.append(("run", x[pos:pos + n], np.ones(n, dtype=np.int64),
                     (np.arange(n) % 1000 == 0).astype(np.int64),
                     freq_to_fcw(fe.f_if_hz + fd, fe.fs_hz),
                     rate_to_fcw(CA_CHIP_RATE * (1 + fd / 1575.42e6), fe.fs_hz), D))
        pos += n
    exp_d, exp_m = await run_segments(h, ch, segs)
    assert len(exp_d) >= 3
    assert h.dumps == exp_d
    assert h.meas == exp_m
    # Sanity: the prompt correlator holds the signal (strong |P| vs E/L).
    _, ie, qe, ip, qp, il, ql = exp_d[-1]
    assert np.hypot(ip, qp) > 1.2 * max(np.hypot(ie, qe), np.hypot(il, ql))


# --------------------------------------------------------------------------
# pytest entry points
# --------------------------------------------------------------------------
def _run(toplevel, sources, testcase=None):
    from cocotb_tools.runner import get_runner
    runner = get_runner("icarus")
    build = ROOT / "tb" / "sim_build" / toplevel
    runner.build(sources=[ROOT / "rtl" / s for s in sources], hdl_toplevel=toplevel,
                 includes=[ROOT / "rtl"], build_dir=build, build_args=["-g2012"], timescale=("1ns", "1ps"), always=True)
    runner.test(hdl_toplevel=toplevel, test_module="test_rtl", build_dir=build,
                test_dir=ROOT / "tb", testcase=testcase)


def test_gps_ca_gen():
    _run("gps_ca_gen", ["gps_ca_gen.sv"], "ca_gen_matches_model")


def test_track_channel():
    _run("track_channel", ["track_channel.sv"],
         ["track_channel_random_stimulus", "track_channel_random_stimulus_boc",
          "track_channel_random_stimulus_tdm", "track_channel_random_stimulus_tdm_slot1_boc",
          "track_channel_gps_signal"])
