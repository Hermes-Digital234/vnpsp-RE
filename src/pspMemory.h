#pragma once
#include <cstddef>

enum class memRegion { images, audio, scripts, count };
constexpr int memRegionCount = static_cast<int>(memRegion::count);

class pspMemory {
public:
    bool init();

    void* alloc(memRegion region, size_t bytes);    // 16-byte aligned; nullptr if over budget or out of memory
    void release(void* p);

    size_t used(memRegion region) const     { return used_[static_cast<int>(region)]; }
    size_t budget(memRegion region) const   { return budget_[static_cast<int>(region)]; }
    size_t heapSize() const                 { return heapBytes_; }

private:
    pspMemory() = default;
    pspMemory(const pspMemory&) = delete;
    pspMemory& operator=(const pspMemory&) = delete;

    friend pspMemory& pspMem();
    size_t detectHeap() const;

    size_t heapBytes_ = 0;
    size_t budget_[memRegionCount] = {};
    size_t used_[memRegionCount] = {};
};