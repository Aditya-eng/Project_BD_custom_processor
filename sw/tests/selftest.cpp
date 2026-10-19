// Small known-answer checks for the host library (run by ctest).
#include <array>
#include <cstdio>
#include <cstdlib>

#include "bd/loops.hpp"
#include "bd/records.hpp"

#define CHECK(c)                                                         \
    do {                                                                 \
        if (!(c)) {                                                      \
            std::fprintf(stderr, "%s:%d: CHECK(%s) failed\n", __FILE__, __LINE__, #c); \
            std::exit(1);                                                \
        }                                                                \
    } while (0)

int main() {
    bd::Record r{};
    // Dump on channel 191, epoch 0xBEEF, values with sign bits set.
    std::array<uint32_t, 8> w{(1u << 28) | (191u << 16) | 0xBEEFu, 0xFFFFFFFFu, 2, 0x80000000u,
                              4, 5, 0x7FFFFFFFu, 0};
    CHECK(bd::parse_record(w, r));
    CHECK(r.type == bd::RecordType::Dump && r.dump.channel == 191 && r.dump.epoch == 0xBEEF);
    CHECK(r.dump.ie == -1 && r.dump.ip == INT32_MIN && r.dump.ql == INT32_MAX);

    std::array<uint32_t, 8> m{(2u << 28) | (7u << 16) | 3u, 0xDEADBEEFu, 0xFFFFFFFEu, 123, 1022,
                              0x89ABCDEFu, 0x01234567u, 0};
    CHECK(bd::parse_record(m, r));
    CHECK(r.type == bd::RecordType::Meas && r.meas.channel == 7 && r.meas.carr_cycles == -2);
    CHECK(r.meas.tic_cnt == 0x0123456789ABCDEFull && r.meas.chip_idx == 1022);

    std::array<uint32_t, 8> bad{(9u << 28), 0, 0, 0, 0, 0, 0, 0};
    CHECK(!bd::parse_record(bad, r));

    // FCW conversions: fs/4 -> 2^30; negative wraps; code rate at 1.023 MHz / 4 MHz.
    CHECK(bd::freq_to_fcw(1e6, 4e6) == (1 << 30));
    CHECK(bd::freq_to_fcw(-1e6, 4e6) == -(1 << 30));
    CHECK(bd::rate_to_fcw(1.023e6, 4e6) == 1098437886u);
    std::puts("selftest ok");
    return 0;
}
