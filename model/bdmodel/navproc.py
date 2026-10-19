"""Receiver chain from tracked prompts to transmit time: bit sync, LNAV
subframe sync (TLM/HOW parity), and SV time at a measurement latch.

Epoch bookkeeping (see correlator.py): after a channel load, epoch_cnt = w
while the replica is in the code period that starts at wrap w. Tracker
record r is the dump of that period (r = 0 is the partial first period).
"""
from dataclasses import dataclass

import numpy as np

from .gps_ca import CA_CHIP_RATE, CA_LEN
from .lnav import find_subframe_start
from .tracking import bit_sync


@dataclass
class NavSync:
    bit_offset: int     # record index of the first full data bit used
    sf_wrap: int        # code-period wrap index at which a subframe starts
    sf_tow: float       # GPS SV time (TOW, s) at that wrap
    inverted: bool      # Costas polarity
    sf_id: int


def nav_sync(ip_history, min_transitions=10, settle_epochs=100):
    """Bit sync, then subframe sync. Returns NavSync or None.

    Epochs before `settle_epochs` (FLL/PLL pull-in) are not used for bit sync.
    """
    ip = np.asarray(ip_history, dtype=np.float64)
    bs = bit_sync(ip, min_transitions, start=settle_epochs)
    if bs is None:
        return None
    first = bs if bs >= 1 else bs + 20
    n_bits = (len(ip) - first) // 20
    sums = ip[first:first + 20 * n_bits].reshape(n_bits, 20).sum(axis=1)
    bits = (sums < 0).astype(np.int64)      # +1 -> logic 0 (same convention as the simulator)
    hit = find_subframe_start(bits)
    if hit is None:
        return None
    idx, inv, tow_count, sf_id = hit
    # HOW carries the TOW of the next subframe start.
    return NavSync(first, first + 20 * idx, tow_count * 6.0 - 6.0, inv, sf_id)


def sv_time_at(meas, sync: NavSync):
    """SV transmit time (TOW, s) of the replica at a measurement latch.

    Returned as float64 TOW, which resolves ~6e-11 s (~2 cm of range); enough
    for code positioning, not for carrier phase (M4 switches to split time).
    """
    periods = (meas.epoch - sync.sf_wrap) % 65536
    chips = periods * CA_LEN + meas.chip_idx + meas.code_frac / 2 ** 32
    return sync.sf_tow + chips / CA_CHIP_RATE
