# Schedule estimate (FPGA prototype)

**Estimate, not a commitment.** Assumptions:
- One person (the owner) works on it full time, with Claude writing RTL, model and host code.
- The owner does all hardware, lab and procurement work.
- The VC709, a host PC and a Vivado licence are available from week 1.
- Uncertainty is ±50%. The critical path is RF hardware, lab access and statistics gathering, not RTL.

| Milestone | Content | Exit evidence | Weeks from start |
|---|---|---|---|
| **M0** ✅ | Requirements v1, architecture, licence and clean-room policy; GPS L1 C/A reference model; first RTL slice (code generator, tracking channel) bit-exact | T0, T1.1–T1.2 pass | done (week 0) |
| **M1** ✅ | Multi-channel RTL (channel bank, sample mux, timebase/tic/PPS, record collector, register bus); C++ host skeleton (record parser, tracking loop bit-identical to Python); LNAV + PVT on simulated data | T0.7–T0.10, T1.6 pass | done (week 0) |
| M2 | Vivado project on the VC709: XDMA, CDC, playback path; hardware bit-exactness | T2.1–T2.4 | 8 |
| M3 | Evaluation board recording; live front-end interface via FMC breakout; **first live GPS L1 fix** | T2.5, T3.1–T3.2, first T4.1 data | **12 (≈ 3 months)** |
| M4 | All v1 signals: BOC(1,1), L5/E5a/B2a with secondary codes, L2C, B1I, G1 FDMA, NavIC L5; observables, RINEX, RTCM out | T1.5 for every signal, T4.2 zero baseline | 24 |
| M5 | RTK (RTKLIB-based) + Ntrip; RF bench campaign | T3.3–T3.9, T4.3 | 32 |
| M6 | Statistics campaign (≥ 300 RTK initializations, TTFF, 7-day run), 192-channel full load, hardening, final report against REQUIREMENTS P-tier | T4 complete | **40–52 (≈ 9–12 months)** |

**Short answer:**
- First live satellite fix on the VC709: about 3 months.
- Full multi-band, multi-constellation RTK prototype with the P-tier requirements demonstrated: about 9–12 months.

Things that move these dates:
- Front-end evaluation board lead time and its digital interface (RISKS R2/R3): ±1–2 months on M3.
- No Vivado licence for the 690T (RISKS R1): blocks M2 completely.
- Part-time effort: multiply by 1 / (fraction of time).
- No access to a surveyed point or second antenna: M5/M6 accuracy claims cannot be made.
