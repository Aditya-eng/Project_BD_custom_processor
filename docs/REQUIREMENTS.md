# Project BD — Frozen Requirements v1

**Status:** Frozen v1, 2026-10-18. Changes need a new version with a change log entry.
**Scope:** FPGA prototype on Xilinx VC709 (XC7VX690T) plus host PC software. No ASIC in this phase.

## How to read this document

- **Tier P** — prototype acceptance criteria. The VC709 build is "done" when every P requirement passes its test.
- **Tier F** — final-product targets carried from the BD990-class reference. They are not acceptance criteria for this phase. They exist so prototype decisions do not block them later.
- **Evidence labels** used throughout the project: `reference` (manufacturer claim), `target`, `assumption`, `estimate`, `simulated`, `synthesized`, `measured`.
- "Channel" = one correlator channel tracking **one signal component** (e.g. GPS L5-I *or* L5-Q) of one satellite, with Early/Prompt/Late complex correlators.

## 1. Signals

| ID | Requirement | Tier | Rationale / deviation from BD990 |
|---|---|---|---|
| REQ-SIG-001 | Track GPS L1 C/A, L2C (CL pilot + CM data), L5 (I5 + Q5) | P | Modern GPS triple-frequency. **Drops L2 P(Y) semi-codeless (BD990 "L2E").** It is only needed for legacy satellites without L2C. |
| REQ-SIG-002 | Track Galileo E1 B/C (BOC(1,1) replica), E5a I/Q | P | E1/E5a pair is what RTK engines use. E5b, AltBOC and E6 are deferred (REQ-SIG-010). |
| REQ-SIG-003 | Track BeiDou B1I, B1C (data + pilot), B2a (data + pilot) | P | India sees a large BeiDou constellation. B2b/B3 are deferred. |
| REQ-SIG-004 | Track QZSS L1 C/A, L1C, L2C, L5; SBAS (GAGAN/others) L1 | P | These come at near-zero cost, since they use the same bands and code families. |
| REQ-SIG-005 | Track NavIC L5 SPS (BPSK(1), 1176.45 MHz) | P | Regional system, useful in India; same RF path as L5. |
| REQ-SIG-006 | Track GLONASS G1 C/A (FDMA) | P | Adds availability; G2 is deferred because the chosen front-end frequency plan cannot hold L5, L2 and G2 on one LO (see ARCHITECTURE §3). |
| REQ-SIG-010 | GLONASS G2/L3, Galileo E5b/AltBOC/E6 (HAS), BeiDou B2b/B3, QZSS L6, SBAS L5 | F | Deferred to v2. Galileo E6 HAS is the planned **free substitute for Trimble RTX** PPP. |
| REQ-SIG-011 | Trimble RTX, OmniSTAR, CMR/CMR+ | — | **Excluded.** Proprietary/subscription services; see LICENSES.md and CLEAN_ROOM.md. |

## 2. Capacity and acquisition

| ID | Requirement | Tier | Acceptance |
|---|---|---|---|
| REQ-CH-001 | ≥ 192 simultaneous channels in the FPGA | P | Synthesized and timing-closed in Vivado on XC7VX690T. Estimate: ~44% LUT (Yosys estimate, ARCHITECTURE §6). |
| REQ-CH-002 | Any channel can be attached to any of the 4 RF paths and any code (memory code up to 16384 chips) | P | Register test + RTL simulation. |
| REQ-CH-003 | ≥ 336 channels | F | Needs a time-multiplexed correlator engine (ARCHITECTURE §8). |
| REQ-ACQ-001 | Acquire all GPS L1 C/A satellites at ≥ 38 dB-Hz within 2 s of sample streaming, given a warm almanac/time | P | Recorded-sky playback + live sky. |
| REQ-ACQ-002 | Cold-sky search (no almanac, ±5 kHz) of all 32 GPS PRNs within 10 s | P | Host benchmark on recorded data. |
| REQ-ACQ-003 | Acquisition sensitivity 35 dB-Hz (P), 32 dB-Hz (F) | P/F | Simulated + playback. |
| REQ-ACQ-004 | False acquisition probability < 1e-3 per PRN/search | P | ≥ 10,000 noise-only searches (simulated). |

## 3. Tracking and raw measurements

| ID | Requirement | Tier | Acceptance |
|---|---|---|---|
| REQ-TRK-001 | GPS L1 C/A code tracking noise ≤ 0.02 chip (1σ) at 45 dB-Hz, DLL Bn = 2 Hz, E-L = 1 chip | P | **Simulated: 0.0025–0.003 chip** (model/tests/test_acq_track.py). Hardware: playback test. |
| REQ-TRK-002 | Carrier phase noise ≤ 0.01 cycle (1σ) at 45 dB-Hz, PLL Bn = 15 Hz | P | **Simulated: 0.0036 cycle.** |
| REQ-TRK-003 | Maintain carrier lock down to 28 dB-Hz (P) / 25 dB-Hz (F) | P/F | Simulated C/N0 ramp; playback. |
| REQ-TRK-004 | Tracking loops tolerate one epoch of host update latency without degradation | P | **Simulated: passes** (update_delay_epochs = 1). |
| REQ-TRK-005 | Cycle-slip detection; loss-of-lock indicator per RINEX LLI semantics | P | Injected-slip simulation. |
| REQ-MEAS-001 | Pseudorange, carrier phase, Doppler, C/N0, LLI for every tracked component | P | RINEX 3.05 output checked with an independent RINEX QC tool. |
| REQ-MEAS-002 | Measurement epochs aligned to receiver time from one global tic; all channels latched on the same sample | P | RTL: shared `tic` (implemented, verified bit-exact). |
| REQ-MEAS-003 | Measurement rate 1, 5, 10, 20 Hz (P); 50 Hz with < 20 ms latency (F) | P/F | Host timing logs. |
| REQ-MEAS-004 | Zero-baseline double-difference noise: code ≤ 0.25 m, carrier ≤ 2 mm (1σ, GPS L1, elevation > 30°) | P | Zero-baseline test, TEST_PLAN T4.2. |

## 4. Positioning

The statistical definitions below apply to every positioning requirement.
- Accuracy: horizontal = 2D error; stated as 1σ (68%) and 95% over ≥ 24 h of 1 Hz epochs, open sky, geodetic-grade antenna on a point known to ≤ 5 mm.
- RTK **correct fix**: fixed solution within 5 cm (3D) of truth. **False fix**: fixed solution outside 5 cm. **Initialization**: a full reset of ambiguities followed by a run until the first fix.

| ID | Requirement | Tier | Acceptance |
|---|---|---|---|
| REQ-PVT-001 | Standalone position ≤ 2.5 m H, ≤ 5 m V (95%) | P | 24 h static log. |
| REQ-PVT-002 | Standalone 1 m H / 1.5 m V (1σ) — BD990 `reference` | F | — |
| REQ-DGNSS-001 | Code-differential 0.5 m + 1 ppm H (1σ) with RTCM 3 corrections | P | Short-baseline test. |
| REQ-RTK-001 | Short baseline (< 10 km): 1 cm + 1 ppm H, 2 cm + 1 ppm V (1σ) | P | Short-baseline campaign. |
| REQ-RTK-002 | BD990 `reference` 8 mm + 1 ppm H, 15 mm + 1 ppm V, baselines < 30 km | F | — |
| REQ-RTK-003 | Initialization: ≥ 95% correct fix within 60 s, **zero false fixes**, over ≥ 300 initializations | P | With zero failures in 300 trials, the false-fix rate is < 1% at 95% confidence. |
| REQ-RTK-004 | Initialization: typically < 8 s; false-fix rate < 0.1% demonstrated over ≥ 3,000 initializations | F | The handoff's ">99%" vs ">99.9%" BD990 wording is replaced by this explicit definition. |
| REQ-RTK-005 | RTK engine runs on the host from RTCM 3.x MSM input (Ntrip client) | P | — |

## 5. Timing, start-up, outages

| ID | Requirement | Tier |
|---|---|---|
| REQ-TIME-001 | 1PPS output aligned to GPS time ≤ 50 ns (1σ) (P), ≤ 20 ns (F); output on a VC709 user SMA | P/F |
| REQ-TIME-002 | Event input timestamping with ≤ 1 sample period resolution (12.6 ns at 79.5 MHz) | P |
| REQ-TTFF-001 | Cold start < 60 s (P) / 45 s (F); warm < 35 s (P) / 30 s (F) | P/F |
| REQ-TTFF-002 | Re-acquisition < 2 s after a 10 s full signal outage | P |
| REQ-TTFF-003 | RTK: keep fixed solution through 5 s correction outage (prediction), flag age of corrections | P |

## 6. Interfaces and outputs

| ID | Requirement | Tier |
|---|---|---|
| REQ-IO-001 | Outputs: NMEA 0183 (GGA, RMC, GSA, GSV, GST), RTCM 3.3 MSM4 + MSM7, RINEX 3.05 files | P |
| REQ-IO-002 | Inputs: RTCM 3.x MSM corrections over Ntrip or TCP | P |
| REQ-IO-003 | Raw IF sample recording and playback of all 4 RF paths (lossless 2-bit) | P |
| REQ-IO-004 | Host link: PCIe (VC709 edge connector) | P |
| REQ-IO-005 | BD990 44-pin header, 3.3 V module form factor | — (excluded) |

## 7. Robustness and monitoring

| ID | Requirement | Tier |
|---|---|---|
| REQ-INT-001 | Spectrum monitor: per-RF-path spectrum (≥ 10 kHz resolution) from the raw sample stream, ≥ 1 update/s | P |
| REQ-INT-002 | Detect a CW interferer ≥ 10 dB above the noise floor and report its frequency within 1 s | P |
| REQ-INT-003 | Adaptive notch filtering before the correlators; higher-resolution ADC path | F |
| REQ-MP-001 | Narrow correlator (E-L spacing down to 0.1 chip, programmable) | P (implemented: `half_spacing` register) |
| REQ-MP-002 | Multipath estimation (multi-correlator / MEDLL-class) | F |

## 8. Power, environment, mechanical

| ID | Requirement | Tier |
|---|---|---|
| REQ-PWR-001 | Measure and report FPGA rail power with all channels active (VC709 power monitoring) | P (measure only) |
| REQ-PWR-002 | Receiver board ≤ 2.5 W in BD990's broad-mix configuration | F |
| REQ-ENV-001 | Lab conditions, 15–35 °C | P |
| REQ-ENV-002 | −40 to +75 °C | F |

## 9. Explicit exclusions for this phase

ASIC; pin/footprint compatibility with BD990; INS and dual-antenna heading; 100 Hz output; Trimble RTX/OmniSTAR/CMR; L2 P(Y) semi-codeless tracking; power optimisation.

## 10. Change log

- v1 (2026-10-18): first freeze. Choices delegated by the project owner; rationale in ARCHITECTURE.md.
