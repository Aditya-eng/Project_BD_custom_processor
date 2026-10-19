#include "bd/records.hpp"

namespace bd {

bool parse_record(const std::array<uint32_t, kRecordWords>& w, Record& out) {
    const uint32_t type = w[0] >> 28;
    const auto channel = static_cast<uint16_t>((w[0] >> 16) & 0xFFF);
    const auto epoch = static_cast<uint16_t>(w[0] & 0xFFFF);
    if (type == static_cast<uint32_t>(RecordType::Dump)) {
        out.type = RecordType::Dump;
        out.dump = Dump{channel, epoch,
                        static_cast<int32_t>(w[1]), static_cast<int32_t>(w[2]),
                        static_cast<int32_t>(w[3]), static_cast<int32_t>(w[4]),
                        static_cast<int32_t>(w[5]), static_cast<int32_t>(w[6])};
        return true;
    }
    if (type == static_cast<uint32_t>(RecordType::Meas)) {
        out.type = RecordType::Meas;
        out.meas = Meas{channel, epoch, w[1], static_cast<int32_t>(w[2]), w[3], w[4],
                        static_cast<uint64_t>(w[5]) | (static_cast<uint64_t>(w[6]) << 32)};
        return true;
    }
    return false;
}

std::vector<Record> parse_stream(const uint8_t* data, std::size_t len) {
    std::vector<Record> out;
    for (std::size_t off = 0; off + kRecordBytes <= len; off += kRecordBytes) {
        std::array<uint32_t, kRecordWords> w{};
        for (std::size_t i = 0; i < kRecordWords; ++i) {
            const uint8_t* p = data + off + 4 * i;
            w[i] = static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
                   (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
        }
        Record r{};
        if (parse_record(w, r)) out.push_back(r);
    }
    return out;
}

}  // namespace bd
