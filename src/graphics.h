#pragma once
#include <cstdint>

using imageHandle = int32_t;
constexpr imageHandle invalidImage = -1;

class graphics {
public:
    virtual ~graphics() = default;

    //lifetime
    virtual bool init() = 0;
    virtual bool shutdown() = 0;

    //assets
    virtual imageHandle loadImage(const char* path) = 0;
    virtual void freeImage(imageHandle image) = 0;

    //drawing
    virtual void draw();
    virtual void clear() = 0;
    virtual void drawBackground(imageHandle image) = 0;
    virtual void drawSprite(imageHandle image, int x, int y) = 0;
    virtual void drawText(const char* text, int x, int y) = 0;
    virtual void present() = 0; // end of frame

    virtual int screenWidth() const = 0;
    virtual int screenHeight() const = 0;
};