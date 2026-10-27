# Project BD — Architecture v1 (VC709 FPGA prototype)

Evidence labels: `verified` (checked against a primary source or a test in this repo), `likely` (secondary source / strong inference), `assumption`, `estimate`, `simulated`, `synthesized`.

## 1. Decisions at a glance

| Decision | Choice | Label |
|---|---|---|
| FPGA platform | Xilinx VC709, XC7VX690T-2FFG1761C | verified (board docs) |
| Processor | **Host PC over PCIe** (no hard CPU on Virtex-7; MicroBlaze too slow for 192-channel loops + RTK) | design choice |
| RF front end | NTLab **NT1068** 4-channel L1/L2/L3/L5 front end (pin-compatible successor of the end-of-life NT1065), 2-bit ADC per channel | likely (vendor page and trade press; datasheet not yet read, see RISKS R2) |
| RF paths | 4 simultaneous: P1 = L1/E1/B1C/B1I (upper), P2 = GLONASS G1, P3 = L5/E5a/B2a/NavIC L5, P4 = L2C | design choice |
| Sampling | Real IF, 2-bit sign/magnitude, **fs = 79.5 MHz** provisional (see §3) | assumption until the NT1068 clock plan is verified |
| Baseband | 192 × `track_channel` in parallel, one sample per clock in the `fe_clk` domain | estimate fits (§6) |
| Acquisition | Host FFT on the continuous raw sample stream (FPGA sends all samples to the host) | design choice |
| Tracking loops, nav decode, observables | Host C++ (Python reference in `model/`) | design choice |
| RTK / PPP engine | RTKLIB 2.4.3 (BSD-2-Clause) linked as a library for v1; own engine later | see LICENSES.md |
| HDL tools | Vivado (Enterprise edition needed for XC7VX690T), Icarus + cocotb + Verilator for verification, Yosys for early estimates | verified (tests run in this repo) |

## 2. System block diagram

```text
 Geodetic antenna (active, L1/L2/L5) ── bias-tee ── splitter (for zero-baseline tests)
        │
 NT1068 front end (2 PLLs, 4 IF chains, 2-bit ADCs, 10 MHz TCXO)
        │  4 × {sign, mag} @ fs, source-synchronous clock
 ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ VC709 / XC7VX690T ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
        ▼
 fe_if (IDDR/IDELAY capture) ─┐
                              ├─► sample_mux ─► 4-path sample bus (fe_clk) ─┬─► 192 × track_channel ─► dump/meas collector ─┐
 playback FIFO (from host) ───┘   (live | playback)                         │          ▲ control words (CDC)             │
                                                                            ├─► raw sample packer ───────────────────────────┤
 timebase: 64-bit sample counter, tic generator, PPS out, event capture ─────┘                                              │
                                                                                                                            ▼
                                            XDMA PCIe (C2H streams: samples, dumps; H2C: playback; AXI-Lite: registers)
 ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─
 Host PC (Linux): XDMA driver ─► bd-receiver daemon
     acquisition (FFT) ─► channel manager ─► tracking loops (1 kHz/channel) ─► control words back
     nav decode ─► ephemeris ─► observables ─► PVT / RTK (RTKLIB) ─► NMEA, RTCM out, RINEX files
     spectrum monitor (FFT of raw stream), recorder/player, Ntrip client
```

**Why stream all raw samples to the host.** 4 paths × 2 bit × 79.5 MS/s = 636 Mbit/s ≈ 80 MB/s (estimate). That is under 2% of PCIe Gen3 x8 (≈ 7.9 GB/s raw) and only a few percent of Gen2 x8. Streaming the whole stream gives acquisition, spectrum monitoring and record/playback with no extra FPGA logic. It also lets every FPGA test run on recorded or synthetic data before any RF hardware exists.

## 3. RF front end and frequency plan

### Why the NT1068 and not the alternatives

| Option | For | Against | Verdict |
|---|---|---|---|
| NT1068 (NT1065 successor) | Built for GNSS; 4 coherent channels from 2 synthesizers; L1 + L2/L5 at once; 2-bit ADC already in the chip; shared TCXO keeps inter-band phase coherent | 2-bit only (weaker interference robustness); needs an FMC adapter; IO voltage vs VC709 FMC VADJ (1.8 V) unverified | **Selected** |
| ADI AD9361 FMC (FMCOMMS2/3) | FMC-native; 12-bit; 56 MHz bandwidth | One receive LO per chip, so it cannot capture L1 and L5 at the same time; general-purpose noise figure; needs GNSS filtering and an LNA anyway | Alternate, for later interference studies (single band) |
| Discrete RF (LNA, mixers, ADC) | Full control | Months of RF design; out of scope for v1 | Rejected for v1 |

### Proposed frequency plan (verify against the NT1068 datasheet — RISKS R2)

The NT1065 pairs channels 1–2 on PLL A and 3–4 on PLL B (likely, vendor material). Its IF filter bandwidth is up to ~31 MHz.

| Path | NT ch | LO | Sideband | Signals | IF (main lobes) |
|---|---|---|---|---|---|
| P1 | 1 | A = 1590.0 MHz | lower (IF = LO − f) | GPS L1 C/A, L1C, Galileo E1, BDS B1C, QZSS L1, SBAS L1, BDS B1I | L1: 13.4–15.6 MHz; B1I: 26.9–31.0 MHz |
| P2 | 2 | A | upper (IF = f − LO) | GLONASS G1 (k = −7…+6) | 7.5–16.0 MHz |
| P3 | 3 | B = 1200.0 MHz | lower | GPS L5, Galileo E5a, BDS B2a, QZSS L5, NavIC L5 | 13.3–33.8 MHz (2.8 MHz of upper sidelobe edge cut by a 31 MHz filter, small loss — estimate) |
| P4 | 4 | B | upper | GPS/QZSS L2C | 26.6–28.6 MHz |

- Lower-sideband paths are spectrally inverted. Host software applies `carr_fcw = IF − Doppler` for them.
- **fs = 79.5 MHz = 1590 MHz / 20** (provisional). It must exceed 2 × 33.8 MHz = 67.6 MHz, the top of the highest IF band. It is also non-commensurate with 1.023 and 10.23 Mcps (77.71 and 7.771 samples per chip), which avoids code-phase dead zones. The final value is whatever the NT1068 clock dividers can produce near 80 MHz. The RTL works for any fs ≤ ~125 MHz unchanged.
- GLONASS G2 (1242–1249 MHz) does not fit with LO B = 1200 MHz alongside L5. That is why REQ-SIG-006 keeps G1 only.

### Connection to the VC709

The VC709 has one HPC FMC (J35) at a fixed 1.8 V VADJ (likely, board listings), 10 GTH transceivers to that FMC, 4 SFP+ cages, a CP2103 USB-UART and 2 × 4 GB DDR3 SODIMMs. Staged plan:
1. **No RF:** synthetic and recorded samples through PCIe playback (works today in simulation).
2. **Record:** NT1065/NT1068 evaluation board over USB3 → files → playback into the FPGA.
3. **Live via breakout:** evaluation board digital outputs → FMC breakout card (XM105-class) → FPGA, with level translation if the NT1068 IO is not 1.8 V.
4. **Custom FMC card "BD-RF1":** NT1068, TCXO, SAW filters, antenna bias-tee, 1.8 V IO. Optional; only if stage 3 shows signal-integrity problems.

## 4. Tracking channel contract (implemented)

`rtl/track_channel.sv` ⇔ `model/bdmodel/correlator.py`, verified bit-exact (TEST_PLAN T0). Per accepted sample, with the state before the update:

| Item | Definition |
|---|---|
| Carrier NCO | 32-bit phase, signed 32-bit FCW = round(f_IF_total / fs · 2³²); a signed 32-bit wrap counter of whole cycles (full carrier phase = cycles + phase/2³²) |
| Carrier LUT | 32 entries, index = phase[31:27], value = round(15·cos/sin(2π(k+½)/32)); I = s·cos, Q = −s·sin |
| Code NCO | 32-bit fractional chip phase, unsigned FCW < 2³¹ (code rate < fs/2), chip index modulo `code_len` (≤ 16384) |
| Taps | E = chip + carry(frac + D), L = chip − (frac < D), P = chip; D = `half_spacing` in chips·2³² (E−L spacing = 2D) |
| Code memory | 1 bit per chip, written by the host or `gps_ca_gen`, logic 0 → +1 |
| BOC(1,1) mode | Per channel (MODE register): each tap's code bit is XORed with bit 31 of that tap's fractional phase (frac+D, frac, frac−D). CBOC(6,1,1/11) signals (Galileo E1) are tracked with this BOC(1,1) replica. The loss is 20·log10(√(10/11)) ≈ 0.4 dB (analytical), consistent with the simulated E1-C C/N0 (T1.5). GPS L1CP (TMBOC(6,1,4/33)) tracked with the same replica loses about 1.1 dB (29/33 of the chips correlate), also confirmed in simulation |
| TDM mode | Per channel (MODE bits 1–2): a tap contributes 0 unless bit 31 of its own fractional phase equals the slot bit. GPS L2C chip-multiplexes CM and CL at 1.023 MHz; a channel tracks CM (10230 chips in code memory, 511.5 kHz code NCO) with slot 0. Correlation is a triangle of half-width ½ chip, so the DLL gain is (½ − D) per unit (E−L)/(E+L) (D < ½). CM carries half the L2C power (−3 dB, confirmed in simulation, T1.5) |
| Dump | On the chip wrap code_len−1 → 0, the six 32-bit accumulators (including this sample) are output and cleared; `epoch_cnt` increments |
| Measurement latch | On `tic` with a valid sample: carrier phase, cycle count, code fraction, chip index, epoch count — the raw material for pseudorange and carrier-phase observables, latched in the same sample on every channel |
| Load | Sets NCO state and clears accumulators; an epoch that ended just before the load is still dumped |
| Pipeline | 3 stages (taps → products → accumulate) |

Secondary (overlay) codes are wiped off on the host, which receives one dump per primary epoch (`signals.secondary_sync`; GPS L5, Galileo E1-C/E5a, GPS L1CO, BeiDou B1I D1). Sync scores each secondary period separately, so data bits aligned with the period do not defeat it.

BeiDou B1I (P1, 2.046 Mcps, 2046 chips) uses the plain BPSK channel; no RTL change. Its broadcast codes are Gold codes truncated by one chip, which raises the worst cross-correlation to −19.8 dB (measured, T0.17) from −30 dB. A strong B1I satellite can therefore produce false peaks for a satellite ~20 dB weaker; acquisition must cancel or check detections against strong satellites already tracked. Data + pilot pairs use two channels commanded in lockstep by the host.

Still to add to the channel, each with its own bit-exact test:
- an LFSR code-generator source for codes too long for the 16384-chip memory: GPS L2 CL (767250 chips, 27-stage modular SRG, `bdmodel/gps_l2c.py`) and, later, P(Y)-length codes. Until then L2C is tracked on CM only (CL is a pilot with 3 dB more power and allows long coherent integration);
- programmable integration length (1–20 ms) for weak signals, which will then need secondary-code wipe-off in hardware;
- very-early/very-late taps for multipath monitoring.

## 5. Clock and reset domains

| Domain | Source | Contents |
|---|---|---|
| `fe_clk` (fs, 79.5 MHz) | NT1068 ADC clock (live) or a VC709 MMCM (playback) | sample bus, all channels, timebase |
| `pcie_clk` (250 MHz) | XDMA user clock | DMA streams, AXI-Lite register file |
| `ref_clk` | VC709 200 MHz system clock | MMCMs, IDELAYCTRL |

Crossings: async FIFOs for sample, dump and playback streams. Control words are double-buffered in the AXI domain and moved into `fe_clk` on a toggle handshake, so `carr_fcw` and `code_fcw` change on the same sample. Reset is synchronous per domain.

## 6. Budgets

### FPGA resources (synthesized with Yosys 0.33 `synth_xilinx -family xc7`, not Vivado; ±30% estimate)

| Item | LUT | FF | BRAM18 | Note |
|---|---|---|---|---|
| 1 channel, codes ≤ 1024 chips | ~1,000 (incl. 16 RAM64M) | ~680 | 0 | |
| 1 channel, codes ≤ 16384 chips | ~1,000 | ~685 | 3 | |
| 192 channels (all long-code capable) | ~192k (44%) | ~132k (15%) | 576 (20%) | XC7VX690T: 433,200 LUT, 866,400 FF, 2,940 BRAM18 (likely, Xilinx DS180) |
| XDMA, FIFOs, timebase, collector, raw packer | ~30k (est.) | ~40k (est.) | ~100 (est.) | assumption |
| **Total** | **~51%** | **~20%** | **~23%** | Leaves room for BOC, secondary codes and VE/VL taps (+~25%/channel, estimate) |

**Update (M1, full `bd_core` incl. register files, collector, timebase; Yosys):** 8 → 16 channels adds ~910 LUT and ~970 FF per channel (16 channels: 16.2k LUT, 16.6k FF). Extrapolated to 192: **~176k LUT (41%), ~187k FF (22%)**. FFs are above the per-channel estimate because each channel carries its own shadow/load register file.

Per-channel savings available if needed: share dump output registers across channels through the collector (~30% of channel FFs), and replace triple-ported code memory with a 3-chip sliding window over one BRAM port.

### Throughput

| Path | Rate | Label |
|---|---|---|
| Raw samples to host | 636 Mbit/s (80 MB/s) | estimate |
| Correlator dumps to host | 192 ch × 1 kHz × 32 B = 6.1 MB/s | estimate |
| Control words to FPGA | 192 ch × 1 kHz × 16 B = 3.1 MB/s | estimate |
| Correlator work in fabric | 192 ch × 6 accumulations × 79.5 MS/s = 91.6 G accumulations/s | estimate (replaces the handoff's 33.6 G illustration) |
| Host tracking loops | 192k loop updates/s, ~1 µs each → ~20% of one core | estimate |
| Host acquisition | 32 PRN × 41 Doppler bins × 8 ms, FFT size 79,500, on a modern 8-core CPU: ~1–2 s | estimate; model code measures ~0.2 s per PRN at 16 MS/s in NumPy |

### Timing

The channel datapath has at most a 34-bit add and one LUT-RAM or BRAM read per stage. At 79.5 MHz (12.6 ns) on a -2 speed grade this is expected to close easily (estimate). The real check is Vivado post-route timing with 192 channels, where routing congestion of the 4-path sample bus fan-out is the most likely problem. Mitigation: register the sample bus once per clock region.

## 7. Host software

- Language: C++17 for the real-time daemon; Python for tools, the reference model and analysis.
- Process: one acquisition thread pool, one tracking thread per 64 channels, one PVT/RTK thread.
- Interfaces: XDMA character devices (`/dev/xdma0_c2h_0` samples, `_c2h_1` dumps, `_h2c_0` playback, `_user` registers).
- Every algorithm in C++ has a Python twin in `model/`, and the two are cross-checked on the same inputs.
  - M1 status: the record parser and the tracking loop exist in C++ (`sw/`), and the loop is bit-identical to Python.
  - Bit-identity rules: scalar libm math only, `sqrt(i²+q²)` instead of `hypot`, `-ffp-contract=off`.
- Register map and record format: `docs/REGISTERS.md`.

## 8. Path to ≥ 336 channels and the ASIC (not this phase)

- Time-multiplex each correlator datapath over K channels at fabric clock = K·fs, with channel state in BRAM. Example: K = 4 at 318 MHz is aggressive on Virtex-7; K = 2 at 159 MHz is realistic, giving 384 channels in ~similar area (estimate).
- Replace Xilinx IP (XDMA, MIG, FIFO generators) with our own RTL before any ASIC work. Xilinx IP is licensed for Xilinx devices only.
- Move the tracking loops from the host to an embedded RISC-V with a correlator DMA. The loops already tolerate one epoch of latency (REQ-TRK-004).
