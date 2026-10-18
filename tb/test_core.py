"""bd_core integration tests: register bus, timebase/PPS/events, and the full
channel bank + collector checked bit-exact against the Python model."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import ReadOnly, RisingEdge  # noqa: E402

from bdmodel.correlator import TrackChannel, freq_to_fcw, rate_to_fcw  # noqa: E402
from bdmodel.gps_ca import CA_CHIP_RATE, ca_code  # noqa: E402
from bdmodel.records import parse_record, RecordType  # noqa: E402
from bdmodel.signal_sim import FrontEnd, SatSignal, generate  # noqa: E402

M32 = (1 << 32) - 1
NCH = 4
CH_BASE = 0x1000
CH_STRIDE = 0x40
REG = dict(CARR=0x00, CODE=0x04, SPACING=0x08, CODE_LEN=0x0C, PATH=0x10, LD_CARR=0x14,
           LD_FRAC=0x18, LD_CHIP=0x1C, CMD=0x20, WADDR=0x24, WDATA=0x28)


class Core:
    def __init__(self, dut):
        self.dut = dut
        self.records = []
        self.cycle_log = []   # (sample_cnt, pps_out) per cycle, when logging
        self.log = False
        self.rng = np.random.default_rng(11)
        self.backpressure = 0.0

    async def start(self):
        d = self.dut
        cocotb.start_soon(Clock(d.clk, 10, unit="ns").start())
        for s in (d.live_valid, d.live_sign, d.live_mag, d.pb_valid, d.pb_data, d.bus_addr,
                  d.bus_we, d.bus_wdata, d.bus_re, d.event_in):
            s.value = 0
        d.rec_ready.value = 1
        d.rst.value = 1
        for _ in range(3):
            await RisingEdge(d.clk)
        d.rst.value = 0
        cocotb.start_soon(self._monitor())

    async def _monitor(self):
        d = self.dut
        while True:
            await RisingEdge(d.clk)
            await ReadOnly()
            if int(d.rec_valid.value) and int(d.rec_ready.value):
                self.records.append(parse_record(int(d.rec_data.value)))
            if self.log:
                self.cycle_log.append((int(d.u_tb.sample_cnt.value), int(d.pps_out.value)))

    async def write(self, addr, val):
        d = self.dut
        d.bus_addr.value = addr
        d.bus_wdata.value = val & M32
        d.bus_we.value = 1
        await RisingEdge(d.clk)
        d.bus_we.value = 0

    async def read(self, addr):
        d = self.dut
        d.bus_addr.value = addr
        d.bus_re.value = 1
        await RisingEdge(d.clk)
        d.bus_re.value = 0
        await RisingEdge(d.clk)
        await ReadOnly()
        v = int(d.bus_rdata.value)
        await RisingEdge(d.clk)
        return v

    async def write64(self, lo_addr, val):
        await self.write(lo_addr, val & M32)
        await self.write(lo_addr + 4, val >> 32)

    async def ch_write(self, ch, name, val):
        await self.write(CH_BASE + ch * CH_STRIDE + REG[name], val)

    async def load_code(self, ch, bits):
        await self.ch_write(ch, "WADDR", 0)
        for b in bits:
            await self.ch_write(ch, "WDATA", int(b))
        await self.ch_write(ch, "CODE_LEN", len(bits))

    async def idle(self, n):
        self.dut.pb_valid.value = 0
        for _ in range(n):
            await RisingEdge(self.dut.clk)

    async def play(self, paths, valid):
        """paths: 4 x n signed sample arrays; valid: n flags."""
        d = self.dut
        packed = np.zeros(len(valid), dtype=np.int64)
        for p in range(4):
            packed |= (np.asarray(paths[p], dtype=np.int64) & 0xF) << (4 * p)
        for w, v in zip(packed, valid):
            d.pb_data.value = int(w)
            d.pb_valid.value = int(v)
            if self.backpressure:
                d.rec_ready.value = int(self.rng.random() >= self.backpressure)
            await RisingEdge(d.clk)
        d.pb_valid.value = 0
        d.rec_ready.value = 1


@cocotb.test()
async def registers_and_timebase(dut):
    c = Core(dut)
    await c.start()
    assert await c.read(0x000) == 0x42443031
    assert await c.read(0x004) == 0x00010000
    assert await c.read(0x008) == NCH
    assert await c.read(0x010) == 0xDF31
    await c.write(0x00C, 1)
    assert await c.read(0x00C) == 1

    # PPS every 100 samples, 7 wide, first at sample 37.
    await c.write(0x020, 100)
    await c.write(0x024, 7)
    await c.write64(0x028, 37)
    c.log = True
    n = 400
    await c.play([np.zeros(n)] * 4, np.ones(n, dtype=int))
    await c.idle(2)   # drain the sample-mux register stage
    c.log = False
    for cnt, pps in c.cycle_log:
        # Registered output: high while (sample_cnt - 1 - 37) mod 100 < 7.
        k = cnt - 1 - 37
        assert pps == int(k >= 0 and k % 100 < 7), (cnt, pps)
    assert await c.read(0x030) == n
    assert await c.read(0x034) == 0

    # Event capture: stamped with the sample index two clocks after the input rises.
    dut.pb_valid.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    s_a = int(dut.u_tb.sample_cnt.value)
    await RisingEdge(dut.clk)
    dut.event_in.value = 1
    for _ in range(5):
        await RisingEdge(dut.clk)
    dut.event_in.value = 0
    dut.pb_valid.value = 0
    await RisingEdge(dut.clk)
    assert await c.read(0x040) == 1
    lo = await c.read(0x038)
    hi = await c.read(0x03C)
    assert (hi << 32 | lo) == s_a + 1 + 2


def model_run(chans, cfg_events, paths, valid, tic_next, tic_period):
    """Run the model in segments delimited by control-word events.

    cfg_events: list of (valid_sample_index, ch, carr_fcw, code_fcw).
    Returns {ch: (dumps, meas)} and the list of tic sample indices.
    """
    valid_idx = np.nonzero(valid)[0]
    n_valid = len(valid_idx)
    tics = []
    t = tic_next
    while t < n_valid:
        tics.append(t)
        t += tic_period
    out = {ch: ([], []) for ch in chans}
    bounds = sorted({0, n_valid, *[e[0] for e in cfg_events]})
    for a, b in zip(bounds[:-1], bounds[1:]):
        for e in cfg_events:
            if e[0] == a:
                chans[e[1]].carr_fcw, chans[e[1]].code_fcw = e[2], e[3]
        seg_tics = [x - a for x in tics if a <= x < b]
        for ch, m in chans.items():
            s = np.asarray(paths[m.path], dtype=np.int64)[valid_idx[a:b]]
            dd, mm = m.process(s, seg_tics)
            out[ch][0].extend(dd)
            out[ch][1].extend(mm)
    return out, tics


@cocotb.test()
async def channel_bank_bit_exact(dut):
    c = Core(dut)
    await c.start()
    c.backpressure = 0.2
    rng = np.random.default_rng(5)

    fe = FrontEnd(fs_hz=4.0e6, f_if_hz=1.1e6)
    n = 14000
    pathA = generate([SatSignal(7, 50.0, 2100.0, 100.25, 0.2), SatSignal(19, 46.0, -900.0, 700.0)],
                     fe, n / fe.fs_hz, seed=3)
    pathB = generate([SatSignal(19, 50.0, 1500.0, 20.5)], fe, n / fe.fs_hz, seed=4)
    paths = [pathA, pathB, rng.integers(-8, 8, n), rng.integers(-3, 4, n)]
    valid = (rng.random(n) < 0.9).astype(int)

    short = rng.integers(0, 2, 61).astype(np.uint8)
    setup = {  # ch: (path, code bits, carr Hz, code rate, spacing, chip0)
        0: (0, ca_code(7), fe.f_if_hz + 2100.0, CA_CHIP_RATE * (1 + 2100 / 1575.42e6), 1 << 31, 100),
        1: (1, ca_code(19), fe.f_if_hz + 1500.0, CA_CHIP_RATE * (1 + 1500 / 1575.42e6), 1 << 30, 20),
        2: (0, ca_code(19), fe.f_if_hz - 900.0, CA_CHIP_RATE, 3 << 29, 700),
        3: (3, short, 123456.0, 0.4e6, 12345, 5),
    }
    chans = {}
    for ch, (path, bits, fc, fr, sp, chip0) in setup.items():
        await c.load_code(ch, bits)
        cf, kf = freq_to_fcw(fc, fe.fs_hz), rate_to_fcw(fr, fe.fs_hz)
        await c.ch_write(ch, "PATH", path)
        await c.ch_write(ch, "SPACING", sp)
        await c.ch_write(ch, "CARR", cf)
        await c.ch_write(ch, "CODE", kf)
        await c.ch_write(ch, "LD_CARR", 0)
        await c.ch_write(ch, "LD_FRAC", 1 << 30)
        await c.ch_write(ch, "LD_CHIP", chip0)
        await c.ch_write(ch, "CMD", 2)
        m = TrackChannel(bits, carr_fcw=cf, code_fcw=kf, half_spacing=sp)
        m.load(0, 1 << 30, chip0)
        m.path = path
        chans[ch] = m

    tic_next, tic_period = 1000, 3000
    await c.write(0x014, tic_period)
    await c.write64(0x018, tic_next)
    await c.write(0x00C, 1)

    # Play in three segments; between them, retune channels 0 and 3 (commit only).
    cuts = [0, 5000, 9000, n]
    cfg_events = []
    vcount = np.concatenate([[0], np.cumsum(valid)])
    for i, (a, b) in enumerate(zip(cuts[:-1], cuts[1:])):
        if i > 0:
            await c.idle(4)
            for ch, dfc in ((0, 3.0), (3, -50.0)):
                p, bits, fc, fr, sp, chip0 = setup[ch]
                cf = freq_to_fcw(fc + i * dfc, fe.fs_hz)
                kf = rate_to_fcw(fr * (1 + i * 1e-7), fe.fs_hz)
                await c.ch_write(ch, "CARR", cf)
                await c.ch_write(ch, "CODE", kf)
                await c.ch_write(ch, "CMD", 1)
                cfg_events.append((int(vcount[a]), ch, cf, kf))
        await c.play([p_[a:b] for p_ in paths], valid[a:b])
    await c.idle(4 * NCH + 10)

    expected, tics = model_run(chans, cfg_events, paths, valid, tic_next, tic_period)
    got = {ch: ([], []) for ch in chans}
    for r in c.records:
        got[r["ch"]][0 if r["type"] == RecordType.DUMP else 1].append(r)
    for ch in chans:
        exp_d = [(d.epoch, d.ie, d.qe, d.ip, d.qp, d.il, d.ql) for d in expected[ch][0]]
        got_d = [(r["epoch"], r["ie"], r["qe"], r["ip"], r["qp"], r["il"], r["ql"]) for r in got[ch][0]]
        assert got_d == exp_d, f"ch{ch} dumps"
        exp_m = [(m.epoch, m.carr_phase, m.carr_cycles, m.code_frac, m.chip_idx, m.sample_index)
                 for m in expected[ch][1]]
        got_m = [(r["epoch"], r["carr_phase"], r["carr_cycles"], r["code_frac"], r["chip_idx"],
                  r["tic_cnt"]) for r in got[ch][1]]
        assert got_m == exp_m, f"ch{ch} meas"
        assert len(exp_d) >= 3 and len(exp_m) == len(tics)
    assert await c.read(0x04C) == 0   # no overrun
    assert await c.read(0x044) == tics[-1]


def test_bd_core():
    from cocotb_tools.runner import get_runner
    runner = get_runner("icarus")
    build = ROOT / "tb" / "sim_build" / "bd_core"
    srcs = ["bd_core.sv", "sample_mux.sv", "timebase.sv", "channel_bank.sv", "track_channel.sv"]
    runner.build(sources=[ROOT / "rtl" / s for s in srcs], hdl_toplevel="bd_core",
                 includes=[ROOT / "rtl"], build_dir=build, build_args=["-g2012"],
                 parameters={"NCH": NCH, "CODE_AW": 10}, timescale=("1ns", "1ps"), always=True)
    runner.test(hdl_toplevel="bd_core", test_module="test_core", build_dir=build,
                test_dir=ROOT / "tb")
