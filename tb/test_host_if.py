"""bd_host_if (M2 host interface) in two unrelated clock domains: AXI-Lite registers
through the clock crossing, the bus timeout with the sample clock stopped, and the full
H2C playback -> channels -> C2H record path checked bit-exact against the Python model
with random DMA backpressure on both streams."""
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import FallingEdge, RisingEdge  # noqa: E402

from bdmodel import hwcheck  # noqa: E402
from bdmodel.records import parse_stream  # noqa: E402

M32 = (1 << 32) - 1
NCH, W, PKT_RECS, FLUSH, TIMEOUT = 4, 128, 3, 200, 400
SPB, BPR = W // 16, 256 // W
ACLK_PS, FECLK_PS = 4000, 12578          # 250 MHz and an unrelated ~79.5 MHz (6289:2000)


class Host:
    """XDMA stand-in: AXI-Lite master, H2C stream source, C2H stream sink."""

    def __init__(self, dut, seed=1):
        self.dut = dut
        self.rng = np.random.default_rng(seed)
        self.c2h = bytearray()
        self.beats_in_pkt = 0
        self.packets = []                # records per packet
        self.c2h_ready_p = 1.0
        self.h2c_valid_p = 1.0

    async def start(self):
        d = self.dut
        self.aclk = Clock(d.aclk, ACLK_PS, unit="ps")
        self.feclk = Clock(d.fe_clk, FECLK_PS, unit="ps")
        self.aclk.start()
        self.feclk.start()
        for s in (d.s_axil_awvalid, d.s_axil_wvalid, d.s_axil_arvalid, d.s_axis_h2c_tvalid,
                  d.s_axis_h2c_tdata, d.s_axil_awaddr, d.s_axil_wdata, d.s_axil_araddr,
                  d.live_valid, d.live_sign, d.live_mag, d.event_in):
            s.value = 0
        d.s_axil_bready.value = 1
        d.s_axil_rready.value = 1
        d.m_axis_c2h_tready.value = 1
        d.aresetn.value = 0
        for _ in range(10):
            await RisingEdge(d.aclk)
        d.aresetn.value = 1
        for _ in range(10):
            await RisingEdge(d.fe_clk)
        cocotb.start_soon(self._c2h_sink())

    async def _c2h_sink(self):
        d = self.dut
        while True:
            await FallingEdge(d.aclk)
            d.m_axis_c2h_tready.value = int(self.rng.random() < self.c2h_ready_p)
            await RisingEdge(d.aclk)
            # Read right at the edge, before its register updates: these are the values
            # the DUT sampled (same convention as the AXI-Lite and H2C helpers).
            if int(d.m_axis_c2h_tvalid.value) and int(d.m_axis_c2h_tready.value):
                assert int(d.m_axis_c2h_tkeep.value) == (1 << (W // 8)) - 1
                self.c2h += int(d.m_axis_c2h_tdata.value).to_bytes(W // 8, "little")
                self.beats_in_pkt += 1
                if int(d.m_axis_c2h_tlast.value):
                    assert self.beats_in_pkt % BPR == 0, "tlast inside a record"
                    self.packets.append(self.beats_in_pkt // BPR)
                    self.beats_in_pkt = 0

    async def write(self, addr, val, expect=0):
        d = self.dut
        d.s_axil_awaddr.value = addr
        d.s_axil_wdata.value = val & M32
        d.s_axil_awvalid.value = 1
        d.s_axil_wvalid.value = 1
        while True:
            await RisingEdge(d.aclk)
            if int(d.s_axil_awready.value):
                # AXI: the response must follow the address/data handshake.
                assert int(d.s_axil_wready.value) and not int(d.s_axil_bvalid.value)
                break
        d.s_axil_awvalid.value = 0
        d.s_axil_wvalid.value = 0
        while True:
            await RisingEdge(d.aclk)
            if int(d.s_axil_bvalid.value):
                break
        assert int(d.s_axil_bresp.value) == expect, (hex(addr), int(d.s_axil_bresp.value))

    async def read(self, addr, expect=0):
        d = self.dut
        d.s_axil_araddr.value = addr
        d.s_axil_arvalid.value = 1
        while True:
            await RisingEdge(d.aclk)
            if int(d.s_axil_arready.value):
                assert not int(d.s_axil_rvalid.value)          # AXI: R follows the AR handshake
                break
        d.s_axil_arvalid.value = 0
        while True:
            await RisingEdge(d.aclk)
            if int(d.s_axil_rvalid.value):
                break
        assert int(d.s_axil_rresp.value) == expect, (hex(addr), int(d.s_axil_rresp.value))
        return int(d.s_axil_rdata.value)

    async def sample_count(self):
        lo = await self.read(0x030)
        return (await self.read(0x034)) << 32 | lo

    async def play(self, paths):
        """Stream samples (4 paths x n, n a multiple of W/16) as H2C beats."""
        d = self.dut
        n = len(paths[0])
        assert n % SPB == 0
        words = np.zeros(n, dtype=np.int64)
        for p in range(4):
            words |= (np.asarray(paths[p], dtype=np.int64) & 0xF) << (4 * p)
        for b in range(n // SPB):
            beat = 0
            for i, w in enumerate(words[b * SPB:(b + 1) * SPB]):
                beat |= int(w) << (16 * i)
            while self.rng.random() >= self.h2c_valid_p:       # random source gaps
                d.s_axis_h2c_tvalid.value = 0
                await RisingEdge(d.aclk)
            d.s_axis_h2c_tdata.value = beat
            d.s_axis_h2c_tvalid.value = 1
            while True:
                await RisingEdge(d.aclk)
                if int(d.s_axis_h2c_tready.value):
                    break
        d.s_axis_h2c_tvalid.value = 0

    async def drain(self, n_expected):
        """Wait until the core has consumed every streamed sample."""
        while await self.sample_count() != n_expected:
            for _ in range(20):
                await RisingEdge(self.dut.aclk)


@cocotb.test()
async def registers_through_cdc(dut):
    h = Host(dut)
    await h.start()
    assert await h.read(0x000) == 0x42443031
    assert await h.read(0x004) == 0x00020000
    assert await h.read(0x008) == NCH
    rng = np.random.default_rng(7)
    for _ in range(300):                                  # T2.2 in simulation
        v = int(rng.integers(0, 1 << 32))
        await h.write(0x050, v)
        assert await h.read(0x050) == v
    assert await h.read(0x100) == 0xDEADBEEF               # unmapped global register


@cocotb.test()
async def bus_timeout_without_sample_clock(dut):
    h = Host(dut)
    await h.start()
    await h.write(0x050, 0x1234)
    h.feclk.stop()
    assert await h.read(0x050, expect=2) == 0xDEADBEEF     # SLVERR after the timeout
    await h.write(0x050, 0x5678, expect=2)                # earlier access still pending
    h.feclk.start()
    for _ in range(20):
        await RisingEdge(dut.fe_clk)
    assert await h.read(0x050) == 0x1234                  # the stale read did no harm
    await h.write(0x050, 0x9ABC)
    assert await h.read(0x050) == 0x9ABC


@cocotb.test()
async def playback_to_records_bit_exact(dut):
    """Runs the shared T2.4 scenario (bdmodel.hwcheck) with random H2C gaps and C2H
    backpressure; tools/hw_bitexact.py runs the same program on the VC709."""
    h = Host(dut, seed=int(os.environ.get("TB_SEED", "3")))
    await h.start()
    sc = hwcheck.build(nch=NCH)
    for op in sc.ops:
        if op[0] == "w":
            await h.write(op[1], op[2])
        elif op[0] == "drain":
            h.h2c_valid_p, h.c2h_ready_p = 1.0, 0.6
            await h.drain(op[1])
        else:                                              # ("play", a, b)
            h.h2c_valid_p, h.c2h_ready_p = 0.7, 0.6
            await h.play([p_[op[1]:op[2]] for p_ in sc.paths])
    for _ in range(FLUSH + 600):                           # let the pad flush close the packet
        await RisingEdge(dut.aclk)

    assert hwcheck.compare(sc, bytes(h.c2h)) == []
    assert all(len(sc.expected[ch][0]) >= 3 and len(sc.expected[ch][1]) == sc.n_tics
               for ch in sc.expected)

    # Packet framing: every record delivered, packets <= PKT_RECS records, every packet
    # closed (the last one by a pad record), pads only as the final record of a packet.
    recs = parse_stream(bytes(h.c2h))
    total = len(h.c2h) // 32
    pads = total - len(recs)
    assert h.beats_in_pkt == 0 and sum(h.packets) == total
    assert max(h.packets) == PKT_RECS and pads >= 1          # full packets do occur
    words = np.frombuffer(bytes(h.c2h), dtype="<u4").reshape(-1, 8)
    ends = np.cumsum(h.packets) - 1
    pad_idx = [i for i, row in enumerate(words) if (int(row[0]) >> 28) == 0]
    assert all(np.all(words[i] == 0) for i in pad_idx) and set(pad_idx) <= set(ends.tolist())
    assert await h.read(0x04C) == 0                        # no collector overrun


def test_host_if():
    from cocotb_tools.runner import get_runner
    runner = get_runner("icarus")
    build = ROOT / "tb" / "sim_build" / "bd_host_if"
    srcs = ["bd_host_if.sv", "axil_bus_bridge.sv", "async_fifo.sv", "bd_core.sv",
            "sample_mux.sv", "timebase.sv", "channel_bank.sv", "track_channel.sv"]
    runner.build(sources=[ROOT / "rtl" / s for s in srcs], hdl_toplevel="bd_host_if",
                 includes=[ROOT / "rtl"], build_dir=build, build_args=["-g2012"],
                 parameters={"NCH": NCH, "CODE_AW": 10, "W": W, "H2C_AW": 4, "C2H_AW": 2,
                             "PKT_RECS": PKT_RECS, "FLUSH_CYCLES": FLUSH,
                             "BUS_TIMEOUT": TIMEOUT},
                 timescale=("1ns", "1ps"), always=True)
    runner.test(hdl_toplevel="bd_host_if", test_module="test_host_if", build_dir=build,
                test_dir=ROOT / "tb")
