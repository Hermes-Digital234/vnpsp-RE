#include "debug.h"
#include <cstdio>
#include <cstdarg>

debugLevel debug::level_ = debugLevel::info;

void debug::log(debugLevel level, const char* fmt, ...) {
#ifdef VNPSP_DEBUG
    if (level > level_) return;

    static const char* const names[] = { "E", "W", "I", "T" };
    char buf[256];                         // fixed buffer, logging shouldn't allocate when memory is tight
    va_list args;
    va_start(args, fmt);
    vsnprintf(buf, sizeof buf, fmt, args);
    va_end(args);

    printf("[%s] %s\n", names[static_cast<int>(level)], buf);
    fflush(stdout);
#else
    (void)level; (void)fmt;                // in release builds the call does nothing
#endif
}