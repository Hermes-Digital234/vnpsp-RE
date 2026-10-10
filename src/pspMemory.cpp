#include "pspMemory.h"
#include <malloc.h>
#include <cstdio>

namespace {
    constexpr size_t kb = 1024;
    constexpr size_t mb = 1024 * 1024;
    constexpr size_t margin = 512 * kb;       // always left free, tune this when shit hits the fan

    // placeholder numbers, measure and adjust while testing
    constexpr size_t smallLimit = 28 * mb;    // heap below this = PSP-1000 class
    constexpr size_t imagesSmall = 6 * mb,  scriptsSmall = 2 * mb, audioCapSmall = 30 * mb;
    constexpr size_t imagesLarge = 16 * mb, scriptsLarge = 4 * mb, audioCapLarge = 30 * mb;

    struct alignas(16) allocHeader {
        size_t bytes;
        int region;
    };
}

size_t pspMemory::detectHeap() const {
    size_t lo = 0, hi = 64 * mb;
    while (hi - lo > 64 * kb) {
        size_t mid = lo + (hi - lo) / 2;
        void* p = malloc(mid);
        if (p) { free(p); lo = mid; } else { hi = mid; }
    }
    return lo;
}

bool pspMemory::init() {
    heapBytes_ = detectHeap();
    bool small = heapBytes_ < smallLimit;

    budget_[(int)memRegion::images]  = small ? imagesSmall  : imagesLarge;
    budget_[(int)memRegion::scripts] = small ? scriptsSmall : scriptsLarge;

    size_t fixed = budget_[(int)memRegion::images] + budget_[(int)memRegion::scripts] + margin;
    size_t left  = heapBytes_ > fixed ? heapBytes_ - fixed : 0;
    size_t cap   = small ? audioCapSmall : audioCapLarge;
    budget_[(int)memRegion::audio] = left < cap ? left : cap;   // audio gets what's left, makes sure it doesnt crash on psp 1000

    printf("heap %u KB, audio budget %u KB\n", (unsigned)(heapBytes_ / kb),
           (unsigned)(budget_[(int)memRegion::audio] / kb));    // shows in PSPLink / PPSSPP log
    return heapBytes_ > 0;
}

void* pspMemory::alloc(memRegion region, size_t bytes) {
    int r = (int)region;
    if (used_[r] + bytes > budget_[r]) return nullptr;

    void* raw = memalign(16, bytes + sizeof(allocHeader));
    if (!raw) return nullptr;

    auto* h = (allocHeader*)raw;
    h->bytes = bytes;
    h->region = r;
    used_[r] += bytes;
    return (char*)raw + sizeof(allocHeader);
}

void pspMemory::release(void* p) {
    if (!p) return;
    auto* h = (allocHeader*)((char*)p - sizeof(allocHeader));
    used_[h->region] -= h->bytes;
    free(h);
}