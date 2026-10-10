#pragma once
#include "graphics.h"

constexpr int menuMaxItems = 32;
constexpr int menuLabelLen = 48;

struct MenuItem {
    char label[menuLabelLen] = {};
    imageHandle image = invalidImage;   // optional, invalidImage means none. i put images here for the gameSelect menu as vn's are packed with little icons.
};

struct MenuData {
    MenuItem items[menuMaxItems];
    int count  = 0;
    int cursor = 0;
    int scroll = 0;     // this is used when there are more games than fit on the screen. 0 so it starts on the first entry
};

void menuClear(MenuData& m);
bool menuAdd(MenuData& m, const char* label, imageHandle img = invalidImage);
void menuMove(MenuData& m, int delta, int visibleRows);   // wraps and adjusts scroll