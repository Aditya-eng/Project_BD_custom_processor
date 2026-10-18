# Test plan v1

Every test states its evidence level. A result is never promoted: simulation does not prove hardware behaviour, and FPGA measurements say nothing about ASIC power.

## T0 — Unit and bit-exact (runs in CI, no hardware)

| Test | What | Status |
|---|---|---|
| T0.1 | C/A codes: first 10 chips of PRN 1–10 against IS-GPS-200 Table 3-Ia; balance and autocorrelation of all 32 PRNs | **pass** (`model/tests/test_gps_ca.py`) |
| T0.2 | Vectorized correlator model equals a literal per-sample reading of the contract (random state, split blocks, tics) | **pass** (`model/tests/test_correlator.py`) |
| T0.3 | `gps_ca_gen.sv` equals the model for all 32 PRNs | **pass** (`tb/test_rtl.py`) |
| T0.4 | `track_channel.sv` equals the model: random samples/FCWs/spacing, 15% sample bubbles, tics, a 37-chip memory code, two mid-stream reloads; plus a simulated GPS stream | **pass** for seeds 1–5 |
| T0.5 | Testbench sensitivity: injected RTL bugs (Q sign, late-tap wrap, epoch latch) must fail T0.4 | **pass** (all 3 mutations caught) |
| T0.6 | Verilator `-Wall` lint clean; generated LUT include up to date | **pass** |

## T1 — Receiver algorithms on simulated signals (CI)

| Test | Status |
|---|---|
| T1.1 Acquisition finds 2 satellites (45/42 dB-Hz) within ±250 Hz / ±0.5 chip; an absent PRN is not detected | **pass (simulated)** |
| T1.2 Tracking vs truth: code error, carrier error, Doppler, C/N0, bit sync, nav-bit recovery, with 0 and 1 epoch update latency | **pass (simulated)**: code σ 0.0025–0.006 chip, carrier σ ≈ 0.004 cycle, C/N0 0.8–0.9 dB below truth (2-bit + LUT loss) |
| T1.3 Acquisition false-alarm rate on 10,000 noise-only searches (REQ-ACQ-004) | to do |
| T1.4 C/N0 ramp to find the loss-of-lock threshold (REQ-TRK-003) | to do |
| T1.5 Every new signal type (BOC, secondary codes, FDMA): same T1.2 battery | to do |
| T1.6 PVT from simulated multi-satellite scenario with known position and clock | to do |

## T2 — FPGA on the VC709 without RF (playback)

| Test | Pass criterion |
|---|---|
| T2.1 Vivado build: timing met at fs with 192 channels; utilization report archived | WNS ≥ 0 |
| T2.2 PCIe link up, register read/write, scratch register | 10⁶ random R/W without error |
| T2.3 Playback loopback: host streams samples → FPGA raw packer → host | bit-identical for 60 s at full rate |
| T2.4 **Hardware bit-exactness:** synthetic and recorded files played into the FPGA; every dump and measurement equals the Python model | zero mismatches over 192 channels × 60 s |
| T2.5 Closed loop with the host daemon on playback data: same tracking results as the pure-software run | observables identical |
| T2.6 Sustained throughput: no FIFO overflow with 192 channels for 24 h | zero drops (counters) |

## T3 — RF front end (bench, conducted)

**Safety and legality.** GNSS-band signal generators and simulators are used **conducted only**: cabled, attenuated, inside a shielded enclosure where possible. Radiating GNSS-like signals is illegal in India (WPC) and most other countries. Always put a DC block between test equipment and any port carrying antenna bias.

| Test | Method | Equipment | Pass criterion |
|---|---|---|---|
| T3.1 ADC threshold / AGC | Histogram of the raw 2-bit stream, terminated input and live antenna | none beyond the receiver | magnitude-bit duty 30–36% (optimal for 2-bit ≈ 32%) on every path |
| T3.2 IF passband shape | Spectrum of the raw stream with a noise source (or a terminated, hot LNA) at the input | noise source or active antenna | passband covers the IF bands in ARCHITECTURE §3 within 1 dB ripple |
| T3.3 Image rejection | CW at signal frequency, then at image frequency (2·LO − f), same level | signal generator, attenuators | image suppressed ≥ 25 dB (adjust to datasheet) |
| T3.4 Noise figure | Y-factor with a calibrated noise source, power taken from raw-stream statistics before the ADC saturates; or via C/N0 at a known simulator power | noise source (ENR known) | ≤ datasheet + 1 dB |
| T3.5 Sensitivity | GNSS simulator at −130, −140, −145, −150 dBm; acquisition and tracking thresholds | GNSS simulator (optional; see below) | REQ-ACQ-003, REQ-TRK-003 |
| T3.6 CW interference tolerance | CW in-band at L1, L5, L2 swept J/S from 0 to 50 dB; record C/N0 degradation; check that the spectrum monitor detects and reports it | signal generator, combiner | REQ-INT-001/002; degradation curve archived |
| T3.7 Out-of-band blocking | Strong CW at likely nearby services (e.g. 1.8, 2.1, 2.3 GHz cellular bands; 1.5 GHz) at −30 dBm | signal generator, combiner | C/N0 drop ≤ 1 dB |
| T3.8 Inter-path coherence | Zero-baseline geometry-free carrier combination (L1−L5, L1−L2) drift over 24 h | live antenna + splitter | no unexplained drift > 0.1 cycle/h after temperature correction |
| T3.9 Reference oscillator | Receiver clock drift and Allan deviation from the PVT clock solution | live sky | within TCXO spec |

**If no GNSS simulator is available** (they are expensive), T3.5 is replaced by:
1. Recorded live-sky data with calibrated attenuation inserted after the antenna LNA (step attenuator), so C/N0 is lowered in known dB steps.
2. Synthetic signals in playback (T2.4) for exact truth.

This gives relative sensitivity, not absolute dBm. The report must say so.

## T4 — Receiver performance (live sky)

| Test | Setup | Requirement |
|---|---|---|
| T4.1 Standalone accuracy | 24 h static on a point surveyed to ≤ 5 mm | REQ-PVT-001 |
| T4.2 Zero baseline | One antenna → splitter → Project BD + reference receiver (E600/BD990 as black box) and/or a second channel set | REQ-MEAS-004; side-by-side C/N0 vs elevation |
| T4.3 Short baseline RTK | Two antennas, baseline known to ≤ 2 mm, or a public CORS station within 10 km as base | REQ-RTK-001 |
| T4.4 RTK initialization statistics | Scripted ≥ 300 ambiguity resets over several days and sky geometries | REQ-RTK-003 |
| T4.5 TTFF and re-acquisition | Scripted cold/warm resets (≥ 50 each); 10 s RF cut via an RF switch | REQ-TTFF-001/002 |
| T4.6 Comparison with the reference receiver | Same antenna, same time; position and fix statistics side by side | informative; BD990 numbers stay `reference` |
| T4.7 Long run | 7 days continuous; memory, FIFO counters, slips | no crash, no unexplained resets |

## Equipment list

| Item | Needed for | Priority |
|---|---|---|
| VC709 + host PC with a free PCIe x8 slot (Linux) | everything | required |
| Vivado licence covering XC7VX690T (Enterprise; the VC709 kit shipped with a device-locked voucher) | T2+ | required |
| NT1065/NT1068 evaluation board | T2.4 (recorded), T3, T4 | required |
| Triple-frequency geodetic antenna (L1/L2/L5), mount on a surveyed point | T3.8, T4 | required |
| Active GNSS splitter (DC pass on one port), DC blocks, bias-tee, SMA/N cables | T3, T4 | required |
| Step attenuator (0–70 dB, 1 dB steps) | T3.5 alternative | required |
| RF signal generator to ≥ 2.5 GHz, combiner | T3.3, T3.6, T3.7 | strongly recommended |
| Spectrum analyzer | debugging T3 | recommended (the raw-stream FFT covers most needs) |
| Calibrated noise source | T3.4 | optional |
| Multi-constellation GNSS simulator | T3.5 absolute sensitivity | optional (expensive) |
| Second geodetic antenna or access to a nearby CORS/IGS station | T4.3, T4.4 | required for RTK |
