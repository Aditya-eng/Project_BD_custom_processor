# bd_core register map and record format (M2)

The source of truth is `rtl/bd_core.sv` and `rtl/channel_bank.sv`. Host-side parsers are `model/bdmodel/records.py` (Python) and `sw/include/bd/records.hpp` (C++). The integration test `tb/test_core.py` exercises all of them together.

## 1. Bus

- 16-bit byte address, 32-bit data.
- A write takes effect on the clock edge.
- Read data comes back one cycle after `bus_re` (`bus_rvalid`).
- The bus runs in the sample clock domain. On the FPGA, the host reaches it through the XDMA user BAR (64 KB AXI-Lite window, byte address = register address) and `rtl/axil_bus_bridge.sv`, which hands one transaction at a time across to the sample clock on a toggle handshake. Order is preserved, so latching reads (`_LO` then `_HI`) and CMD commits keep their meaning. A register access takes a few cycles of each clock.
- If the sample clock is absent, an access would never complete. After `BUS_TIMEOUT` PCIe clocks (65,536 ≈ 262 µs at 250 MHz) the bridge answers SLVERR, and reads return `0xDEADBEEF`. The timed-out transaction is still performed when the sample clock returns; until then, new accesses are refused with SLVERR at once.
- Reading an unmapped global address returns `0xDEADBEEF`.
- Channel registers are write-only in M1.

## 2. Global registers (0x0000–0x0FFF)

| Addr | Name | Access | Reset | Description |
|---|---|---|---|---|
| 0x000 | ID | RO | `0x42443031` | "BD01" |
| 0x004 | VERSION | RO | `0x00020000` | M2 |
| 0x008 | NCH | RO | param | Number of channels |
| 0x00C | CTRL | RW | 0 | bit 0: sample source (0 = live front end, 1 = PCIe playback) |
| 0x010 | FE_MAP | RW | `0xDF31` | Live ADC code → signed 4-bit value. Entry c = {sign, mag} occupies bits [4c+3:4c]. Default maps 00 → +1, 01 → +3, 10 → −1, 11 → −3 |
| 0x014 | TIC_PERIOD | RW | 0 | Samples between measurement tics; 0 = single shot |
| 0x018 / 0x01C | TIC_NEXT_LO / _HI | WO | — | Sample index of the next tic. **Writing _HI arms it.** |
| 0x020 | PPS_PERIOD | RW | 0 | Samples between PPS pulses; 0 = single shot |
| 0x024 | PPS_WIDTH | RW | 0 | PPS high time in samples |
| 0x028 / 0x02C | PPS_NEXT_LO / _HI | WO | — | Sample index that triggers the next PPS. **Writing _HI arms it.** |
| 0x030 / 0x034 | SAMPLE_CNT_LO / _HI | RO | 0 | Current sample index. Reading _LO latches _HI. |
| 0x038 / 0x03C | EVENT_CNT_LO / _HI | RO | 0 | Sample index stamped on the last event-input rising edge. Reading _LO latches _HI. |
| 0x040 | EVENT_COUNT | RO | 0 | Number of event edges seen |
| 0x044 / 0x048 | LAST_TIC_LO / _HI | RO | 0 | Sample index of the last tic |
| 0x04C | STATUS | RO / W1C | 0 | bit 0: collector overrun (sticky; write 1 to clear) |
| 0x050 | SCRATCH | RW | 0 | Free for host use; T2.2 register test |

### Timing semantics

| Signal | Exact behaviour |
|---|---|
| Sample index | Counts valid samples on the bus after the source mux. The sample with index k is the (k+1)-th accepted sample. |
| Tic | Every channel latches its measurement on the **same** sample: the one with index `TIC_NEXT`. Then `TIC_NEXT += TIC_PERIOD`. |
| PPS | `pps_out` rises one clock after the sample with index `PPS_NEXT` and stays high for `PPS_WIDTH` samples. The next trigger is that index + `PPS_PERIOD`. To steer the PPS onto GPS time, the host writes `PPS_NEXT` each second. Resolution is one sample (12.6 ns at 79.5 MHz). The fixed one-clock output delay is compensated by the host. |
| Event | A rising edge is stamped with the sample index current two clocks after the edge is first registered (2-FF synchronizer). The host subtracts this; the edge itself is uncertain by ±1 clock. |

## 3. Channel registers (channel c at 0x1000 + 0x40·c, c < 192)

| Off | Name | Description |
|---|---|---|
| 0x00 | CARR_FCW | Shadow: signed carrier FCW = round(f / fs · 2³²) |
| 0x04 | CODE_FCW | Shadow: code FCW = round(rate / fs · 2³²), < 2³¹ |
| 0x08 | SPACING | D = half E–L spacing, chips·2³². Reset 0.5 chip |
| 0x0C | CODE_LEN | Code length in chips (≤ 2^CODE_AW). Reset 1023 |
| 0x10 | PATH | RF path 0–3 feeding this channel |
| 0x14 | LD_CARR | Carrier phase loaded by CMD.load |
| 0x18 | LD_FRAC | Code fractional chip loaded by CMD.load |
| 0x1C | LD_CHIP | Chip index loaded by CMD.load |
| 0x20 | CMD | bit 0 commit: shadow FCWs become active together. bit 1 load: commit, plus load phases, clear accumulators and the epoch counter |
| 0x24 | CODE_WADDR | Code memory write address |
| 0x28 | CODE_WDATA | bit 0 is written at CODE_WADDR, then CODE_WADDR increments (logic 0 → +1) |
| 0x2C | MODE | bit 0: BOC(1,1). Each tap is XORed with bit 31 of its own fractional chip phase (frac+D, frac, frac−D), i.e. a sine-phased BOC(1,1) replica (Galileo E1, BeiDou B1C, GPS L1C).<br>bit 1: TDM gate. A tap adds 0 unless bit 31 of its own fractional phase equals bit 2, so the replica occupies one half of each chip (chip-multiplexed codes: GPS L2 CM in the first half, L2 CL in the second).<br>bit 2: TDM slot (0 = first half, 1 = second half).<br>Reset 0 |

Control words take effect on the first sample after the write. In operation the exact sample does not matter, because the NCOs are continuous. The bit-exact tests write them while samples are paused.

## 4. PCIe streams (`rtl/bd_host_if.sv`)

**H2C playback** (`/dev/xdma0_h2c_0`). A byte stream of 16-bit little-endian sample words, one per sample: path p in bits [4p+3:4p], signed 4-bit. The AXI-Stream is 128 bits wide (8 samples per beat); send whole beats (a multiple of 16 bytes). The stream passes through an async FIFO and is consumed at up to one sample per sample clock. Backpressure reaches the host, so playback never drops samples. Set CTRL bit 0 to select playback.

**C2H records** (`/dev/xdma0_c2h_0`). The records of §5, back to back, 32 bytes each. A DMA read returns at a packet end (`tlast`). A packet closes after 64 records. If records stop arriving with a packet partly filled, the interface waits 25,000 PCIe clocks (100 µs) and then sends one **pad record**, all zero (type 0), with `tlast`. So a lone record reaches the host within about 100 µs, while bursts still travel in large packets. Parsers skip type 0.

## 5. Record stream

The collector emits one 256-bit record per item, as 8 little-endian 32-bit words. Type 0 is the PCIe pad record (§4), never sent by the collector itself. Records from different channels interleave. Records from one channel keep their order within each type.

| Word | DUMP (type 1) | MEAS (type 2) |
|---|---|---|
| 0 | `[31:28]` = 1, `[27:16]` channel, `[15:0]` epoch count after the dump | `[31:28]` = 2, `[27:16]` channel, `[15:0]` epoch count at the tic |
| 1 | IE | carrier phase (unsigned 32) |
| 2 | QE | carrier cycles (signed 32) |
| 3 | IP | code fraction (chips·2³²) |
| 4 | QP | chip index |
| 5 | IL | tic sample index [31:0] |
| 6 | QL | tic sample index [63:32] |
| 7 | 0 | 0 |

Correlator values are signed 32-bit. Full replica carrier phase = cycles + phase/2³².

**Throughput rule.** One record per clock. After a tic, every channel has a MEAS pending, so a full drain takes ≤ 2·NCH clocks (384 for 192 channels ≈ 4.8 µs at 79.5 MHz). `TIC_PERIOD` must be larger than that; it is ≥ 1 ms in practice. A channel that produces a new dump or measurement before its previous one left sets `STATUS.overrun`.

## 6. How the host turns a MEAS record into a transmit time

`model/bdmodel/navproc.py`:
- `epoch` counts code-period wraps since the channel load.
- Subframe sync identifies the wrap `w_sf` at which a subframe starts, with SV time `t_sf` from the HOW.
- SV transmit time = `t_sf + ((epoch − w_sf) mod 2¹⁶ · 1023 + chip_idx + code_frac/2³²) / 1.023 MHz`.
- The receive time is the tic sample index on the receiver's own time scale; the position solution supplies its offset from GPS time.
