// Host tracking loops: C++ twin of model/bdmodel/tracking.py (Tracker._update).
// Any change here must be mirrored there; sw/tests checks they agree.
#pragma once

#include <cstdint>
#include <deque>
#include <utility>

#include "bd/records.hpp"

namespace bd {

constexpr double kCaChipRate = 1.023e6;
constexpr double kL1Freq = 1575.42e6;

// Signed 32-bit carrier FCW = round(f / fs * 2^32), wrapped.
int32_t freq_to_fcw(double freq_hz, double fs_hz);
// Unsigned code FCW = round(rate / fs * 2^32); requires rate < fs / 2.
uint32_t rate_to_fcw(double rate_hz, double fs_hz);

struct LoopConfig {
    double pll_bw_hz = 15.0;
    double fll_bw_hz = 10.0;
    int fll_pullin_ms = 100;
    double dll_bw_hz = 2.0;
    double half_spacing_chips = 0.5;
    int update_delay_epochs = 0;
};

struct LoopOutput {
    double carr_freq_hz;
    double code_rate_hz;
    double pll_err_cyc;
    double dll_err_chips;
    bool apply;          // true when a command should be written this epoch
    int32_t carr_fcw;    // command to write (valid when apply)
    uint32_t code_fcw;
};

class TrackingLoop {
public:
    TrackingLoop(double fs_hz, double f_if_hz, double doppler_hz, LoopConfig cfg = {});

    // Initial command for the channel load.
    int32_t initial_carr_fcw() const { return freq_to_fcw(f_if_hz_ + init_doppler_, fs_hz_); }
    uint32_t initial_code_fcw() const {
        return rate_to_fcw(kCaChipRate * (1 + init_doppler_ / kL1Freq), fs_hz_);
    }

    // One code epoch (1 ms for GPS L1 C/A).
    LoopOutput update(const Dump& d);

private:
    double fs_hz_, f_if_hz_, init_doppler_;
    LoopConfig cfg_;
    double fll_int_;
    bool have_prev_ = false;
    double prev_i_ = 0, prev_q_ = 0;
    long epoch_n_ = 0;
    std::deque<std::pair<double, double>> pending_;
};

}  // namespace bd
