// Register access to a Project BD bitstream through the Xilinx XDMA driver's user BAR
// (AXI-Lite window, docs/REGISTERS.md).
//
//   bd_xdma [--dev /dev/xdma0] info              ID, version, channel count, sample count
//   bd_xdma [--dev /dev/xdma0] rd ADDR           read one register (hex or decimal address)
//   bd_xdma [--dev /dev/xdma0] wr ADDR VALUE     write one register
//   bd_xdma [--dev /dev/xdma0] regtest [N]       T2.2: N random SCRATCH write/read pairs
//
// Sample playback and record capture use the DMA character devices directly
// (<dev>_h2c_0, <dev>_c2h_0); tools/hw_bitexact.py drives both for T2.4.
// Not yet run on hardware.
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <string>

namespace {

constexpr std::size_t kBarBytes = 64 * 1024;
constexpr uint32_t kId = 0x000, kVersion = 0x004, kNch = 0x008, kSampleLo = 0x030,
                   kSampleHi = 0x034, kStatus = 0x04C, kScratch = 0x050;

class UserBar {
public:
    explicit UserBar(const std::string& dev) {
        const std::string path = dev + "_user";
        fd_ = ::open(path.c_str(), O_RDWR | O_SYNC);
        if (fd_ < 0) {
            std::perror(path.c_str());
            std::exit(2);
        }
        void* p = ::mmap(nullptr, kBarBytes, PROT_READ | PROT_WRITE, MAP_SHARED, fd_, 0);
        if (p == MAP_FAILED) {
            std::perror("mmap");
            std::exit(2);
        }
        base_ = static_cast<volatile uint32_t*>(p);
    }
    ~UserBar() {
        ::munmap(const_cast<uint32_t*>(base_), kBarBytes);
        ::close(fd_);
    }
    UserBar(const UserBar&) = delete;
    UserBar& operator=(const UserBar&) = delete;

    uint32_t rd(uint32_t addr) const { return base_[addr / 4]; }
    void wr(uint32_t addr, uint32_t v) { base_[addr / 4] = v; }

private:
    int fd_ = -1;
    volatile uint32_t* base_ = nullptr;
};

uint32_t parse_u32(const char* s) {
    char* end = nullptr;
    const unsigned long v = std::strtoul(s, &end, 0);
    if (*end != '\0' || v > 0xFFFFFFFFul) {
        std::fprintf(stderr, "bad number: %s\n", s);
        std::exit(2);
    }
    return static_cast<uint32_t>(v);
}

int usage() {
    std::fputs("usage: bd_xdma [--dev /dev/xdma0] info | rd ADDR | wr ADDR VALUE | regtest [N]\n",
               stderr);
    return 2;
}

}  // namespace

int main(int argc, char** argv) {
    std::string dev = "/dev/xdma0";
    int i = 1;
    if (i + 1 < argc && std::strcmp(argv[i], "--dev") == 0) {
        dev = argv[i + 1];
        i += 2;
    }
    if (i >= argc) return usage();
    const std::string cmd = argv[i];
    UserBar bar(dev);

    if (cmd == "info") {
        const uint32_t id = bar.rd(kId);
        const uint32_t lo = bar.rd(kSampleLo);                     // latches _HI
        const uint64_t samples = (static_cast<uint64_t>(bar.rd(kSampleHi)) << 32) | lo;
        std::printf("id 0x%08x (%s)  version 0x%08x  channels %u  samples %llu  overrun %u\n",
                    id, id == 0x42443031 ? "BD01" : "unexpected", bar.rd(kVersion),
                    bar.rd(kNch), static_cast<unsigned long long>(samples),
                    bar.rd(kStatus) & 1u);
        return id == 0x42443031 ? 0 : 1;
    }
    if (cmd == "rd" && i + 1 < argc) {
        std::printf("0x%08x\n", bar.rd(parse_u32(argv[i + 1])));
        return 0;
    }
    if (cmd == "wr" && i + 2 < argc) {
        bar.wr(parse_u32(argv[i + 1]), parse_u32(argv[i + 2]));
        return 0;
    }
    if (cmd == "regtest") {
        const long n = i + 1 < argc ? std::strtol(argv[i + 1], nullptr, 0) : 1000000;
        std::mt19937 rng(12345);
        long errors = 0;
        for (long k = 0; k < n; ++k) {
            const uint32_t v = rng();
            bar.wr(kScratch, v);
            const uint32_t r = bar.rd(kScratch);
            if (r != v && errors++ < 10)
                std::fprintf(stderr, "#%ld wrote 0x%08x read 0x%08x\n", k, v, r);
        }
        std::printf("regtest: %ld pairs, %ld errors\n", n, errors);
        return errors ? 1 : 0;
    }
    return usage();
}
