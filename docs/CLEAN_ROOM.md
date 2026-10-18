# Clean-room rules

Project BD is an **independent** design that targets BD990-class capability. It does not copy or reverse-engineer Trimble or eSurvey products. These rules keep that claim provable.

## Allowed sources

- Public signal ICDs, RTCM/NMEA/RINEX standards, textbooks, peer-reviewed papers, permissively licensed open source (see LICENSES.md).
- **Published** product specifications (datasheets, product pages, user manuals), used only to set performance targets.

## The reference receiver (E600 / BD990) is a black box

| Allowed | Not allowed |
|---|---|
| Connect an antenna (or the same antenna through a splitter) and log its documented outputs: NMEA, RTCM, RINEX, web UI | Opening the module to identify or photograph ICs for design purposes |
| Compare position, observables, C/N0, TTFF and fix statistics against ours | Dumping, disassembling or decompiling firmware; probing internal buses; running the REA/Ghidra/IDA workflow on its binaries |
| Read its published manuals for test conditions | Copying configuration semantics, message layouts or algorithms from non-public material |

If anyone on the project has already looked at internal firmware or die images, they must write that down in `docs/provenance/` and should not write the matching subsystem.

## Provenance record

- Every algorithm in `model/` and `rtl/` cites its source (an ICD section, a paper, a textbook) in its module docstring or header.
- Commits are signed off by a named author; generated code says which tool generated it and from what.
- Third-party code enters only through the register in LICENSES.md.

## Background material

The original handoff's reverse-engineering research (die extraction, firmware analysis, E600 identification) is project history. It is **not** a design input. It is kept out of this repository.
