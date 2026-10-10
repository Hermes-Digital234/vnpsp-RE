#pragma once

#include <cstddef>
#include <cstdint>

// Decoder for the .bpp format written by convert_assets.py. It only validates the
// header and hands back the bytes in the layout the GE already wants: a 256-entry
// RGBA8888 palette followed by swizzled T8 indices, in one pspMemory block. No
// per-pixel work; the swizzle is the file's, not ours.
//
// Layout (little-endian) is defined here and nowhere else:
//   0   u32  magic "BPP8"
//   4   u16  width     6 u16 height          real image size
//   8   u16  texWidth  10 u16 texHeight      pow2, 16..512, >= real size
//   12  u32  reserved (0)
//   16       palette: 256 x (R,G,B,A)
//   1040     texWidth*texHeight indices, swizzled in 16x8 blocks

enum class bppStatus { ok, openFailed, badMagic, badDimensions, truncated, outOfMemory };

struct bppImage {
    bppImage() = default;
    bppImage(bppImage&&) noexcept;
    bppImage& operator=(bppImage&&) noexcept;
    bppImage(const bppImage&) = delete;
    bppImage& operator=(const bppImage&) = delete;
    ~bppImage();                                  // returns block_ to pspMemory

    int width = 0, height = 0;
    int texWidth = 0, texHeight = 0;
    uint32_t* clut = nullptr;                     // 256 entries, GU_PSM_8888
    uint8_t*  pixels = nullptr;                   // swizzled texWidth*texHeight
private:
    void* block_ = nullptr;
};

bppStatus bppDecode(const uint8_t* data, size_t size, bppImage& out); // core, host-testable
bppStatus bppLoad(const char* path, bppImage& out);                   // read file -> decode
bool bppLinearize(const bppImage& image, uint8_t* rgbaOut);           // tools/tests only