#pragma once

enum class appState { gameSelect, playing, paused };

class graphics;

class app {
public:
    explicit app(graphics& gfx) : gfx_(gfx) {}
    int run();
    void quit();

private:
    bool init();
    void shutdown();
    void update();
    void setState(appState next);

    void updateGameSelect();
    void updatePlaying();
    void updatePaused();

    graphics& gfx_;
    appState state_ = appState::gameSelect;
    volatile bool running_ = false;
};