#include "app.h"
#include "graphics.h"
#include "parser.h"

int app::run() {
    if (!init()) return 1;

    running_ = true;
    while (running_) {
        update();
        gfx_.draw();
    }

    shutdown();
    return 0;
}

void app::update() {
    switch (state_) {
        case appState::gameSelect:  updateGameSelect(); break;
        case appState::playing:     updatePlaying(); break;
        case appState::paused:      updatePaused(); break;
    }
}

void app::setState(appState next) {
    //enter/exit work (load game, tell graphics which screen to show)
    state_ = next;
}


void app::updateGameSelect() {}
void app::updatePlaying() {}
void app::updatePaused() {}

void app::quit() { running_ = false; }