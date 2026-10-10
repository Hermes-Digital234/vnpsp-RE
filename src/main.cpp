#include <pspmoduleinfo.h>
#include <pspkernel.h>
#include <pspthreadman.h>
#include <psppower.h>

#include "app.h"


PSP_MODULE_INFO("vnpsp:RE", PSP_MODULE_USER, 0, 1);

static int exitCallback(int, int, void*)
{
    sceKernelExitGame();
    return 0;
}

static int callbackThread(SceSize, void*)
{
    int cb = sceKernelCreateCallback("exit", exitCallback, NULL);
    sceKernelRegisterExitCallback(cb);
    sceKernelSleepThreadCB();
    return 0;
}

static void setupCallbacks()
{
    int thid = sceKernelCreateThread("callbacks", callbackThread, 0x11, 0xFA0, PSP_THREAD_ATTR_USER, NULL);
    if (thid >= 0) sceKernelStartThread(thid, 0, NULL);
}

int main() {
    setupCallbacks();
    scePowerSetClockFrequency(333,333,116);

}