// Collector record format (docs/REGISTERS.md section 3): 8 little-endian
// 32-bit words per record; word 0 = [31:28] type, [27:16] channel, [15:0] epoch.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace bd {

constexpr std::size_t kRecordWords = 8;
constexpr std::size_t kRecordBytes = kRecordWords * 4;

enum class RecordType : uint8_t { Dump = 1, Meas = 2 };

struct Dump {
    uint16_t channel;
    uint16_t epoch;
    int32_t ie, qe, ip, qp, il, ql;
};

struct Meas {
    uint16_t channel;
    uint16_t epoch;
    uint32_t carr_phase;
    int32_t carr_cycles;
    uint32_t code_frac;
    uint32_t chip_idx;
    uint64_t tic_cnt;
};

struct Record {
    RecordType type;
    Dump dump;   // valid when type == Dump
    Meas meas;   // valid when type == Meas
};

// Parses one record. Returns false for an unknown type.
bool parse_record(const std::array<uint32_t, kRecordWords>& w, Record& out);

// Parses a DMA buffer of back-to-back records; trailing partial bytes are ignored.
std::vector<Record> parse_stream(const uint8_t* data, std::size_t len);

}  // namespace bd
