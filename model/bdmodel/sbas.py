"""SBAS L1 (WAAS, EGNOS, MSAS, GAGAN, ...): GPS-family C/A codes on 1575.42 MHz.

- PRN 120-158 are reserved for SBAS (IS-GPS-200N 6.3.6.1); their C/A codes are the
  G2-delay codes of Table 6-I (model/bdmodel/gps_ca.py, tools/import_is200_ca.py).
- Navigation data: 250 bits per second (EGNOS Open Service SDD issue 3.0, 4.1.1),
  convolutionally encoded at rate 1/2 (constraint length 7) to 500 symbols per second,
  i.e. one symbol per 2 C/A epochs, with no secondary code. The rate 1/2 encoding is
  specified in ICAO Annex 10 Vol. I Appendix B, which is not freely available and has not
  been read for this project; the 2-epoch symbol is what the tracking chain depends on.
- The Viterbi decoder and the message layer (MOPS) are not implemented yet.
"""
SBAS_PRNS = range(120, 159)
DATA_RATE_BPS = 250
SYMBOL_RATE_SPS = 500
EPOCHS_PER_SYMBOL = 2      # 2 ms symbols on 1 ms C/A epochs


def symbol_phase(prompt_i, start: int = 0) -> int:
    """Epoch offset of the 2 ms symbol boundaries (energy-based, sign-ambiguous)."""
    from .tracking import symbol_phase as sp     # tracking imports signals, which imports this
    return sp(prompt_i, EPOCHS_PER_SYMBOL, start=start)
