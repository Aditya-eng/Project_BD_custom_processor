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
| T0.6 | Verilator `-Wall` lint clean (`bd_core` at NCH = 4 and 192); generated LUT include up to date | **pass** |
| T0.7 | `bd_core` registers, timebase, PPS waveform, event stamping | **pass** (`tb/test_core.py`) |
| T0.8 | `bd_core` 4-channel bit-exact vs model: paths, short and C/A codes, mid-stream retunes, 10% sample bubbles, 20% record back-pressure, tics → every DUMP/MEAS record identical; no overrun | **pass**; 3/3 injected bugs caught |
| T0.9 | LNAV: parity round trip and detection of every single-bit error; subframe structure; ephemeris round trip within ½ LSB; preamble search in an inverted stream | **pass** (`model/tests/test_lnav.py`); self-consistent only, field layout to be confirmed on live data |
| T0.10 | C++ host loop equals the Python loop **bit for bit** over 400 replayed epochs (0 and 1 epoch latency); C++ record parser known-answer test | **pass** (`sw/tests`) |
| T0.11 | GPS L5 codes against IS-GPS-705J: the XB-advance and XB-state columns agree for all 63 PRNs × I5/Q5 (two independent ICD statements); codes built from either column are identical; first 13 chips equal the complemented state (ICD footnote); NH10/NH20 as printed | **pass** (`model/tests/test_gps_l5.py`) |
| T0.13 | Galileo codes against the OS SIS ICD Issue 2.2: all 200 E5 codes generated from Tables 16–20 equal the electronic Annex C attachments (SHA-256 recorded at import, re-checked in CI); Table 107 hex convention; E1-B/E1-C 50+50 memory codes of 4092 chips, distinct, correlation sidelobes < 0.08; CS4/CS20/CS25 as printed; 100 distinct CS100 codes | **pass** (`model/tests/test_galileo_codes.py`). E1 memory codes have no second representation in the ICD; they share the parser that the E5 cross-check validates |
| T0.14 | GPS L1C codes against IS-GPS-800J: Legendre sequence = definition = Table 6.2-1; 126 L1CP/L1CD codes reproduce the printed first/last 24 chips; 63 L1CO overlays reproduce the printed final 11 bits; TMBOC pattern (t mod 33 ∈ {0,4,6,29}); overlay sync on synthetic prompts; PRN 38 typo handled | **pass** (`model/tests/test_gps_l1c.py`) |
| T0.12 | BOC(1,1) mode bit-exact: model vs scalar reference, `track_channel` random stimulus, and one BOC channel inside the 4-channel `bd_core` test; 2/2 injected subcarrier bugs caught | **pass** |
| T0.15 | GPS L2C codes against IS-GPS-200N: polynomial = Figure 3-13; all 115 PRNs (Tables 3-IIa, 3-IIb, 6-II) reach the printed CM end state after 10229 clocks; 6 PRNs re-checked for CL after 767249 clocks in CI (all 115 at import); CM correlation sidelobes < 0.05 | **pass** (`model/tests/test_gps_l2c.py`) |
| T0.17 | BeiDou B1I codes against BDS-SIS-ICD-B1I-3.0: all 63 codes balanced (1024 ones in 2047, ICD 4.3) and distinct; untruncated codes three-valued {−65, −1, 63} (G1/G2 a preferred pair); deliberate convention errors unbalance > 30 codes; NH20 as printed; GEO set {1–5, 59–63}. Broadcast (truncated) codes measured: autocorrelation sidelobes ≤ 182, cross-correlation ≤ 210 (−19.8 dB) over all pairs | **pass** (`model/tests/test_bds_b1i.py`) |
| T0.16 | TDM gate mode bit-exact: model vs scalar reference (slot 0, slot 1 combined with BOC), `track_channel` random stimulus for both, one TDM channel (slot 1) in the 4-channel `bd_core` test; 2/2 injected gate bugs caught (wrong tap phase, slot ignored) | **pass** |

## T1 — Receiver algorithms on simulated signals (CI)

| Test | Status |
|---|---|
| T1.1 Acquisition finds 2 satellites (45/42 dB-Hz) within ±250 Hz / ±0.5 chip; an absent PRN is not detected | **pass (simulated)** |
| T1.2 Tracking vs truth: code error, carrier error, Doppler, C/N0, bit sync, nav-bit recovery, with 0 and 1 epoch update latency | **pass (simulated)**: code σ 0.0025–0.006 chip, carrier σ ≈ 0.004 cycle, C/N0 0.8–0.9 dB below truth (2-bit + LUT loss) |
| T1.3 Acquisition false-alarm rate on 10,000 noise-only searches (REQ-ACQ-004) | to do |
| T1.4 C/N0 ramp to find the loss-of-lock threshold (REQ-TRK-003) | to do |
| T1.5 Every new signal type (BOC, secondary codes, FDMA): same T1.2 battery | **pass (simulated):**<br>• **GPS L5-Q:** code σ 0.003 chip; NH20 sync; 20 ms coherent wipe-off.<br>• **Galileo E1-C:** CBOC(6,1,1/11) as broadcast, tracked with the BOC(1,1) replica. Main-peak acquisition, then epoch-aligned Doppler refinement (≤ 15 Hz); code σ 0.0013 chip (about 0.4 m); carrier locked; C/N0 within the expected loss; CS25 sync.<br>• **Galileo E5a-Q:** code σ 0.006 chip; quadrature carrier; per-satellite CS100 sync, with the wrong satellite's CS100 rejected.<br>• **GPS L1CP:** TMBOC as broadcast, with L1CD data at 25% power. Aided acquisition (search centred on the C/A Doppler), main-peak lock, Doppler refined to < 10 Hz. Code σ 0.002 chip, carrier locked, C/N0 within the expected loss (1.1 dB TMBOC vs BOC(1,1) replica, plus the 2-bit ADC). The 18 s overlay is not synced in CI; it is tested on synthetic prompts instead.<br>• **GPS L2 CM:** CM + CL chip-multiplexed as broadcast, CNAV symbols on CM. CM-gated replica (TDM slot 0) rejects the CL half and the wrong slot by > 8×. Aided acquisition, Doppler refined to < 5 Hz, code σ < 0.02 CM chip, carrier locked, every symbol recovered (Costas sign), C/N0 = composite − 3 dB.<br>• **BeiDou B1I:** MEO (D1 50 bps + NH20, run starting mid-bit) and GEO (D2 500 bps) in one stream. Acquisition, code σ < 0.02 chip, carrier locked, C/N0 within 2 dB; NH sync with data present (secondary-code sync now scores each period separately), D2 bit phase found without NH; every data bit recovered (Costas sign).<br><br>Still to do: BDS B1C/B2a, GLONASS G1, L2 CL tracking (needs the LFSR source), CNAV and D1/D2 message decoding. |
| T1.6 IF → acquisition (32-PRN search) → tracking → LNAV TLM/HOW sync → single-epoch PVT, 10 satellites, static receiver | **pass (simulated)**: all visible PRNs detected, none false; transmit-time errors < 10 m; 3D error 3.7 m, time error 5 ns (thresholds 15 m / 50 ns). Ephemeris taken from the scenario; time from the decoded HOW |

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
| T3.10 L2C multiplex order | On live L2C, compare TDM slot 0 vs slot 1 prompt power for CM, and the L2 CM − L1 C/A code-phase difference (after the broadcast inter-signal correction) | live sky | CM found in slot 0 and pseudorange difference ≪ 293 m (one 1.023 MHz slot). Confirms the CM-first reading of IS-GPS-200N (RISKS R13) |

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
