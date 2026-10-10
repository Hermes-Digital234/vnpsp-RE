#pragma once

#if defined(__GNUC__)
#define VNPSP_PRINTF_FORMAT(fmtIdx, argIdx) __attribute__((format(printf, fmtIdx, argIdx)))
#else
#define VNPSP_PRINTF_FORMAT(fmtIdx, argIdx)
#endif

enum class debugLevel { error, warn, info, trace };

class debug {
public:
    static void log(debugLevel level, const char* fmt, ...) VNPSP_PRINTF_FORMAT(2, 3);
    static void setLevel(debugLevel level) { level_ = level; }

private:
    static debugLevel level_;
};