#pragma once

#include <string>
#include <vector>

struct gameEntry {
    std::string name;
    std::string path;
};

class gameSelect {
public:
    void start();
private:
    std::vector<gameEntry> scan(const std::string& root);
    int display(const std::vector<gameEntry>& games);
};