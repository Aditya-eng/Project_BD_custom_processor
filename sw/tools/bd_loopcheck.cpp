// Replays a file of dump records through bd::TrackingLoop and prints one CSV
// line per epoch. Used by sw/tests to compare against the Python loops.
//
// usage: bd_loopcheck <records.bin> <fs_hz> <f_if_hz> <doppler_hz> <update_delay_epochs>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <vector>

#include "bd/loops.hpp"
#include "bd/records.hpp"

int main(int argc, char** argv) {
    if (argc != 6) {
        std::fprintf(stderr, "usage: %s records.bin fs_hz f_if_hz doppler_hz delay\n", argv[0]);
        return 2;
    }
    std::ifstream f(argv[1], std::ios::binary);
    std::vector<uint8_t> buf((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    bd::LoopConfig cfg;
    cfg.update_delay_epochs = std::atoi(argv[5]);
    bd::TrackingLoop loop(std::atof(argv[2]), std::atof(argv[3]), std::atof(argv[4]), cfg);
    std::printf("%d,%u\n", loop.initial_carr_fcw(), loop.initial_code_fcw());
    for (const auto& r : bd::parse_stream(buf.data(), buf.size())) {
        if (r.type != bd::RecordType::Dump) continue;
        const auto o = loop.update(r.dump);
        std::printf("%.17g,%.17g,%.17g,%.17g,%d,%d,%u\n", o.carr_freq_hz, o.code_rate_hz,
                    o.pll_err_cyc, o.dll_err_chips, o.apply ? 1 : 0, o.carr_fcw, o.code_fcw);
    }
    return 0;
}
