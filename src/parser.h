#pragma once
#include <string>
#include <unordered_map>
#include <vector>

class parser {
public:
    parser(const std::string& scriptPath);
    void parse();

private:
    void loadScript(const std::string& scriptPath);
    void parseLabels();

    std::string scriptPath_;
    std::string gameDir_;
    std::vector<std::string> lines_;
    std::unordered_map<std::string, size_t> labels_;

};
