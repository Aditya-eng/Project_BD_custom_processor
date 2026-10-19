#include "bd/loops.hpp"

#include <cmath>

namespace bd {

namespace {
constexpr double kTwoPi = 6.283185307179586;
constexpr double kTwo32 = 4294967296.0;

// sqrt(i*i + q*q) with every step correctly rounded: bit-identical to the
// Python twin (built with -ffp-contract=off so no FMA is fused in).
double mag(int32_t i, int32_t q) {
    const double fi = i, fq = q;
    return std::sqrt(fi * fi + fq * fq);
}
}  // namespace

int32_t freq_to_fcw(double freq_hz, double fs_hz) {
    const long long v = std::llround(freq_hz / fs_hz * kTwo32);
    return static_cast<int32_t>(static_cast<uint32_t>(v & 0xFFFFFFFFLL));
}

uint32_t rate_to_fcw(double rate_hz, double fs_hz) {
    return static_cast<uint32_t>(std::llround(rate_hz / fs_hz * kTwo32));
}

TrackingLoop::TrackingLoop(double fs_hz, double f_if_hz, double doppler_hz, LoopConfig cfg)
    : fs_hz_(fs_hz), f_if_hz_(f_if_hz), init_doppler_(doppler_hz), cfg_(cfg),
      fll_int_(doppler_hz) {}

LoopOutput TrackingLoop::update(const Dump& d) {
    const double T = 1e-3;
    const double ip = d.ip, qp = d.qp;
    const double pll_err = ip != 0 ? std::atan(qp / ip) / kTwoPi : 0.0;  // Costas, cycles

    double fll_err = 0.0;
    if (have_prev_ && epoch_n_ < cfg_.fll_pullin_ms) {
        const double dot = prev_i_ * ip + prev_q_ * qp;
        const double cross = prev_i_ * qp - prev_q_ * ip;
        if (dot != 0) fll_err = std::atan(cross / dot) / (kTwoPi * T);
    }
    have_prev_ = true;
    prev_i_ = ip;
    prev_q_ = qp;

    const double w0p = cfg_.pll_bw_hz / 0.53;
    const double w0f = epoch_n_ < cfg_.fll_pullin_ms ? cfg_.fll_bw_hz / 0.25 : 0.0;
    fll_int_ += T * (w0p * w0p * pll_err + w0f * fll_err);
    const double doppler = fll_int_ + 1.414 * w0p * pll_err;
    const double carr_hz = f_if_hz_ + doppler;

    const double e_mag = mag(d.ie, d.qe);
    const double l_mag = mag(d.il, d.ql);
    const double D = cfg_.half_spacing_chips;
    const double dll_err = e_mag + l_mag != 0 ? (1 - D) * (e_mag - l_mag) / (e_mag + l_mag) : 0.0;
    const double code_hz = kCaChipRate * (1 + doppler / kL1Freq) + 4 * cfg_.dll_bw_hz * dll_err;

    LoopOutput out{carr_hz, code_hz, pll_err, dll_err, false, 0, 0};
    pending_.emplace_back(carr_hz, code_hz);
    if (static_cast<int>(pending_.size()) > cfg_.update_delay_epochs) {
        const auto cmd = pending_.front();
        pending_.pop_front();
        out.apply = true;
        out.carr_fcw = freq_to_fcw(cmd.first, fs_hz_);
        out.code_fcw = rate_to_fcw(cmd.second, fs_hz_);
    }
    ++epoch_n_;
    return out;
}

}  // namespace bd
