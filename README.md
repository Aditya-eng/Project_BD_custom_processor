# Project BD

**An independent, multi-band, multi-constellation GNSS receiver aimed at survey-grade (RTK) performance.**

The target capability class is that of a high-end survey OEM board. The Trimble BD990 is used only as a published-specification performance reference: nothing here is copied or reverse-engineered from it ([`docs/CLEAN_ROOM.md`](docs/CLEAN_ROOM.md)). Everything is implemented from public signal specifications (ICDs), textbooks and papers, with a provenance record for every code table.

The first phase is an **FPGA prototype on a Xilinx VC709 board (Virtex-7 XC7VX690T)**: 192 correlator channels in the FPGA, with acquisition, tracking loops, navigation and RTK on a Linux host PC over PCIe. There is no ASIC work in this phase. The FPGA design is written so that it could later move to one (no vendor IP in the datapath).

> **Status, 2026-11-09 (milestone M2 in progress; M4 signals done in simulation).**
> - **No hardware has been built, programmed or measured yet.** Every result below is from simulation or from checks against the ICDs.
> - In simulation, the GPS L1 C/A chain goes from raw IF samples to a position fix (3.7 m, 5 ns on a synthetic sky).
> - Every v1 signal has a verified code generator and is acquired and tracked on simulated signals.
> - The FPGA correlator core and its PCIe host interface are bit-exact against the Python reference model, including across two unrelated clock domains.
> - The VC709 Vivado build, the PCIe bring-up tool and the hardware bit-exactness harness are written but **not yet run**. They need a Vivado licence that covers the 690T, plus the board.

---

## 1. What the receiver is meant to do

Frozen requirements: [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md). Tier **P** is what the VC709 prototype must demonstrate; tier **F** holds final-product targets.

| Area | Prototype target (P) |
|---|---|
| Signals | GPS L1 C/A, L1C, L2C, L5 · Galileo E1, E5a · BeiDou B1I, B1C, B2a · GLONASS G1 · QZSS, SBAS L1, NavIC L5 |
| Channels | ≥ 192 simultaneous; any channel on any RF path and any code up to 16,384 chips |
| Tracking | code noise ≤ 0.02 chip and carrier noise ≤ 0.01 cycle at 45 dB-Hz; lock down to 28 dB-Hz; loops tolerate one epoch of host latency |
| Positioning | standalone ≤ 2.5 m H (95 %); RTK short baseline 1 cm + 1 ppm H, 2 cm + 1 ppm V (1σ); ≥ 95 % correct fix within 60 s and **zero false fixes** over ≥ 300 initializations |
| Timing | 1PPS aligned to GPS time ≤ 50 ns; event timestamping at one sample (12.6 ns) |
| I/O | NMEA 0183, RTCM 3.3 MSM4/MSM7, RINEX 3.05; RTCM corrections over Ntrip; raw IF record/playback; spectrum monitor |

Deliberately excluded: L2 P(Y) semi-codeless tracking, Trimble RTX/CMR/OmniSTAR, and the BD990 form factor. Galileo E6 HAS is the planned free alternative to RTX in a later version.

## 2. System architecture

```text
 antenna (L1/L2/L5) ─ NT1068 RF front end: 2 LOs, 4 IF chains, 2-bit ADCs, 79.5 MS/s
        │ 4 paths × {sign, mag}
 ┌──────▼───────────────────────── VC709 (XC7VX690T) ──────────────────────────┐
 │ sample mux (live | PCIe playback) ─► 4-path sample bus ─► 192 tracking channels │
 │ timebase: 64-bit sample counter, measurement tic, PPS out, event stamping       │
 │ record collector (dumps + measurements) ─┐                                        │
 │ bd_host_if: AXI-Lite registers, H2C playback, C2H records, clock crossings ◄─┘   │
 │ XDMA PCIe Gen2 x8                                                               │
 └────────────────────────────────────┬────────────────────────────────────────────┘
                                      │ PCIe
 Host PC (Linux): acquisition (FFT) → channel manager → tracking loops (1 kHz/channel)
   → control words back · nav decoding → observables → PVT / RTK → NMEA, RTCM, RINEX
```

**Why the host does the loops.** The Virtex-7 has no hard CPU, and a soft CPU is too slow for 192 channels of loops plus RTK. The loops tolerate one epoch of latency (verified in simulation), so they can run on the host. All raw samples (about 80 MB/s) can also stream to the host, which gives acquisition, spectrum monitoring and record/playback without extra FPGA logic.

**RF front end and frequency plan** ([`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §3). NTLab NT1068, four channels on two LOs:

| Path | LO | Signals | IF |
|---|---|---|---|
| P1 | 1590 MHz, lower sideband | GPS L1 C/A + L1C, Galileo E1, BeiDou B1C + B1I, QZSS L1, SBAS L1 | 13–31 MHz |
| P2 | 1590 MHz, upper sideband | GLONASS G1 (k = −7…+6) | 7.5–16 MHz |
| P3 | 1200 MHz, lower sideband | GPS L5, Galileo E5a, BeiDou B2a, QZSS L5, NavIC L5 | 13–34 MHz |
| P4 | 1200 MHz, upper sideband | GPS/QZSS L2C | 27–29 MHz |

Galileo E5b and BeiDou B2I/B2b (1207.14 MHz) do not fit this plan without giving up L2C. They stay deferred, and the trade-off is documented in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §3.

## 3. Signal status

Every code generator is checked against the official ICD by an importer in [`tools/`](tools/), which writes nothing unless every printed value matches. The tracking tests run on simulated IF signals, including the as-broadcast modulation (CBOC, TMBOC, QMBOC, chip multiplexing, FDMA). Status as of now:

| Constellation | Signal | Codes vs ICD | Simulated acquisition + tracking | Data decoding |
|---|---|---|---|---|
| GPS | L1 C/A | IS-GPS-200 Table 3-Ia first chips (PRN 1–10); all 32 PRNs balanced, Gold correlation | yes, and end-to-end to a position fix | LNAV: full (parity, subframes, ephemeris) |
| GPS | L1C (pilot + data) | IS-GPS-800J: 126 codes, 63 overlays | yes (TMBOC as broadcast) | symbols only |
| GPS | L2C | IS-GPS-200N: 115 PRNs, CM and CL end states | CM yes (chip-multiplexed signal); CL needs a hardware LFSR source | symbols only |
| GPS | L5 (I5 + Q5) | IS-GPS-705J: two independent table columns agree | yes, with NH10/NH20 | symbols only |
| Galileo | E1-B/C | OS SIS ICD 2.2 Annex C | yes (CBOC as broadcast) | symbols only |
| Galileo | E5a-I/Q | 200 E5 codes = Annex C attachments chip for chip | yes, per-satellite CS100 | symbols only |
| Galileo | E5b-I/Q | as above | yes, but not receivable with the v1 frequency plan | symbols only |
| BeiDou | B1I (D1, D2) | BDS-SIS-ICD-B1I 3.0: all codes balanced, three-valued Gold correlation | yes, MEO and GEO | bits only |
| BeiDou | B1C (pilot + data) | BDS-SIS-ICD-B1C 1.0: 126 codes, 63 secondaries | yes (QMBOC as broadcast) | symbols only |
| BeiDou | B2a (pilot + data) | BDS-SIS-ICD-B2a 1.0: 126 codes, 63 secondaries | yes | symbols only |
| GLONASS | G1 (FDMA) | ICD 5.1: code, time mark, frequency table | yes, several FDMA channels in one stream | strings to the bit level |
| QZSS | L1 C/A, L1C, L2C, L5 (PRN 193–202) | the GPS ICDs' additional tables: IS-GPS-200N 6-I and 6-II, IS-GPS-800J 6.3-1/6.3-2, IS-GPS-705J 6-II (all 147 rows each, cross-checked) | L1 C/A yes; L1C overlay sync on synthetic prompts; L5/L2C as GPS | symbols only |
| SBAS | L1 (PRN 120–158) | IS-GPS-200N Table 6-I: G2 delay, initial G2 state and first chips agree for every row; Gold family with GPS | yes, GEO at 500 sps (2 ms symbols) | symbols only (no Viterbi or MOPS messages yet) |
| NavIC | L5 SPS | ISRO-IRNSS-ICD-SPS-1.1 Table 7: first 10 chips of all 14 PRNs (L5 and S). **The table is generated locally from your own copy of the ICD and is not in the repo** (ISRO's no-copy terms) | yes (skipped in CI, which has no table) | symbols only |

Two ICD inconsistencies were found and handled explicitly (see [`docs/LICENSES.md`](docs/LICENSES.md)):
- **IS-GPS-800J** prints PRN 38 as "3".
- **BDS-SIS-ICD-B2a** says data and pilot use the same register value, but its tables differ for PRN 61–63.

QZSS's use of PRN 193–202 is from its own specification (IS-QZSS-PNT), which has not been read yet: its download page asks the reader to accept a disclaimer first. The GPS ICDs define the codes but not which system uses them. QZSS-only signals (L1S, L5S, L6) are not covered.

## 4. FPGA design

The RTL is SystemVerilog in [`rtl/`](rtl/). The register map, PCIe stream formats and record layout are in [`docs/REGISTERS.md`](docs/REGISTERS.md).

- **Tracking channel** (`track_channel.sv`): 32-bit carrier NCO with cycle counter, 32-bit code NCO, Early/Prompt/Late complex correlators with programmable spacing (down to narrow correlator), and a 16,384-chip code memory. Modes:
  - BOC(1,1) replica: Galileo E1, GPS L1C, BeiDou B1C.
  - TDM half-chip gate: GPS L2C CM/CL.
  - FDMA: by carrier frequency word alone.
- **Measurement latch**: one global tic latches carrier phase, code phase and epoch count on the same sample in every channel. This is the raw material for pseudorange and carrier-phase observables.
- **Core** (`bd_core.sv`): sample source mux (live front end or PCIe playback), timebase (64-bit sample counter, tic, PPS, event capture), the channel bank and a record collector.
- **Host interface** (`bd_host_if.sv`, M2):
  - AXI-Lite register bridge with a timeout, so a missing sample clock cannot hang the PCIe bus.
  - Playback (host → FPGA) and record (FPGA → host) AXI-Stream channels.
  - Our own gray-code async FIFOs; record packets close after 64 records or after 100 µs idle.
- **Board** ([`fpga/vc709/`](fpga/vc709/)): XDMA PCIe Gen2 x8, an MMCM generating exactly 79.5 MHz from the 200 MHz oscillator, and pins from the Xilinx VC709 board definition.
- **Size** (Yosys estimates, not Vivado): about 910 LUT and 970 FF per channel. 192 channels come to roughly 41 % of the device's LUTs and 22 % of its flip-flops.

## 5. Host software

- **Python reference model** ([`model/bdmodel/`](model/bdmodel/)): every algorithm exists here first. That covers code generators, a bit-exact correlator model (the contract the RTL must match), signal simulators, FFT acquisition, tracking loops, LNAV, ephemeris, geometry scenarios and PVT.
- **C++17 host library** ([`sw/`](sw/)): record parser and tracking loop, bit-identical to the Python loop. `bd_xdma` reads and writes FPGA registers through the XDMA driver.
- **Planned** (M3–M5): the real-time receiver daemon, nav decoding for the modern signals, observables, RINEX/RTCM/NMEA output, and RTK through RTKLIB (licence check pending).

## 6. How correctness is established

- **Bit-exact contract.** The correlator behaviour is specified once, in `model/bdmodel/correlator.py`. The RTL must reproduce it exactly:
  - Every cocotb test compares every dump and measurement record with the model, under random stimulus, sample gaps and backpressure.
  - The PCIe interface test does the same across two unrelated clock domains.
  - Testbench sensitivity is checked by injecting bugs into the RTL. All real ones so far were caught.
- **ICD provenance.** Code tables enter the repo only through an importer that parses the official PDF and cross-checks every row before writing. Each generated file records the PDF's SHA-256. When an official site was unreachable, the PDF came from the Internet Archive and was verified byte-identical through its archived digest and the server's original size.
- **Evidence labels.** Every result in the docs says whether it is a reference figure, a target, an estimate, simulated, synthesized or measured. Simulation is never promoted to a hardware claim.
- **Same program, sim and hardware.** The hardware bit-exactness test (`tools/hw_bitexact.py`) runs exactly the scenario the simulation verifies (`model/bdmodel/hwcheck.py`).

## 7. Milestones

Full table: [`docs/SCHEDULE.md`](docs/SCHEDULE.md). The schedule estimates about 3 months to a first live fix and 9–12 months to a full RTK prototype.

| Milestone | Content | State |
|---|---|---|
| M0 | Requirements, architecture, GPS L1 C/A model, first channel RTL bit-exact | done |
| M1 | Multi-channel core, timebase/PPS, collector, register bus; C++ loop; LNAV + PVT in simulation | done |
| M2 | VC709 build: PCIe (XDMA), clock crossings, playback; hardware bit-exactness | **in progress**: host interface verified in simulation; Vivado build and board tests not yet run |
| M3 | Front-end recording and live interface; first live GPS L1 fix | not started |
| M4 | All v1 signals, observables, RINEX, RTCM | signals done in simulation (except QZSS, SBAS, NavIC); observables and outputs not started |
| M5 | RTK, Ntrip, RF bench campaign | not started |
| M6 | Statistics campaign, 192-channel full load, final report | not started |

Owner-side dependencies and engineering risks are tracked in [`docs/RISKS.md`](docs/RISKS.md). The main open ones:
- a Vivado licence for the 690T;
- the NT1068 evaluation board and its datasheet;
- a Linux host with a PCIe x8 slot;
- RF test equipment.

## 8. Repository layout

| Path | Contents |
|---|---|
| `docs/` | Requirements, architecture, register map, test plan, schedule, risks, licences, clean-room rules |
| `rtl/` | `track_channel`, `channel_bank`, `timebase`, `sample_mux`, `bd_core`; M2 host interface `bd_host_if`, `axil_bus_bridge`, `async_fifo`; `gps_ca_gen` |
| `fpga/vc709/` | VC709 top level, constraints, Vivado build script, bring-up guide ([`fpga/vc709/README.md`](fpga/vc709/README.md)) |
| `model/bdmodel/` | Python reference model; `tables/` holds the generated code tables (do not edit) |
| `model/tests/` | Code-vs-ICD tests, simulated tracking per signal, LNAV/PVT, end-to-end fix, hardware-harness checks |
| `tb/` | cocotb testbenches: `test_rtl.py` (blocks), `test_core.py` (core), `test_host_if.py` (PCIe side, two clocks) |
| `sw/` | C++ host library, `bd_loopcheck`, `bd_xdma`, tests against Python |
| `tools/` | ICD importers and checkers, carrier LUT generator, `hw_bitexact.py` (T2.4) |

## 9. Running the tests

```sh
sudo apt-get install iverilog verilator cmake g++   # Icarus >= 12, Verilator >= 5
pip install -r requirements-dev.txt
make test        # LUT check, Verilator lint, model tests, RTL-vs-model (cocotb), C++ build + C++-vs-Python
make estimate    # optional: Yosys 7-series resource estimate (needs yosys)
```

CI runs `make test` on every push and pull request.

NavIC: the ISRO ICD may not be copied, so its code table is not in the repo. To enable NavIC locally, run `python3 tools/import_navic.py <your copy of ISRO-IRNSS-ICD-SPS-1.1.pdf>` (needs `pdftotext`). It writes a git-ignored table, and the NavIC tests then run instead of being skipped.

## 10. Building for the VC709

```sh
make vc709 NCH=192    # needs Vivado with a licence covering the XC7VX690T
```

Bring-up steps are in [`fpga/vc709/README.md`](fpga/vc709/README.md): programming, the XDMA driver, `bd_xdma info`, `bd_xdma regtest` (T2.2) and `tools/hw_bitexact.py` (T2.4). This flow has not been run yet.

## 11. Licence and clean room

All rights are reserved by the project owner until a licence is chosen.
- [`docs/LICENSES.md`](docs/LICENSES.md) sets the third-party rules: permissive licences only in shipped code, GPL tools used only as external tools, and Galileo code tables under the EU Annex H authorisation.
- It also holds the ICD provenance records.
- [`docs/CLEAN_ROOM.md`](docs/CLEAN_ROOM.md) sets the independent-development rules.
