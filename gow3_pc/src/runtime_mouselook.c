/* Mouse look handlers (see runtime_mouselook.h): hooks in the game's camera input function that
 * turn the camera by the mouse movement since the last frame, on the game's thread, once per
 * frame. The Last of Us Remastered's camera input function is not located yet, so there are no
 * sites: the loader installs nothing and the mouse acts as the right stick (runtime_pad.c). A
 * site's handler runs in the game's job fibers (64 KiB stacks): keep its frame small. */
#include "runtime_mouselook.h"
#include <stdlib.h>

void runtime_mouselook_set_image(unsigned char *base) { (void)base; }

int runtime_mouselook_enabled(void) {
    static int enabled = -1;
    if (enabled < 0) {
        /* Also with the mouse off: the hooks give the controller camera speed too. Without a
         * captured mouse (off, or no focus) they take no mouse movement. */
        const char *look = getenv("GOW3_MOUSE_LOOK");
        enabled = !(look && look[0] == '0');
    }
    return enabled;
}

const MouseLookSite *runtime_mouselook_sites(unsigned *count) {
    *count = 0;
    return NULL;
}

/* The right stick's x and y clamps, each followed by its store (vmovss [rdi + 0x18 / 0x1c], xmm4). */
static const StickBoostSite boost_sites[] = {
    {"The Last of Us Remastered (right stick x)", 0xa4d48d,
     {0xc4, 0xc1, 0x58, 0x5d, 0xe0, 0xc5, 0xd8, 0x5f, 0xe0, 0xc5, 0xfa, 0x11, 0x67, 0x18}},
    {"The Last of Us Remastered (right stick y)", 0xa4d4d6,
     {0xc4, 0xc1, 0x58, 0x5d, 0xe0, 0xc5, 0xd8, 0x5f, 0xe0, 0xc5, 0xfa, 0x11, 0x67, 0x1c}},
};
static float *boost_slot;

const StickBoostSite *runtime_mouselook_boost_sites(unsigned *count) {
    const char *env = getenv("GOW3_STICK_BOOST");
    *count = env && env[0] == '0' ? 0 : sizeof(boost_sites) / sizeof(boost_sites[0]);
    return boost_sites;
}

void runtime_mouselook_set_boost_slot(float *slot) { __atomic_store_n(&boost_slot, slot, __ATOMIC_RELEASE); }

void runtime_mouselook_set_stick_boost(float boost) {
    float *slot = __atomic_load_n(&boost_slot, __ATOMIC_ACQUIRE);
    if (slot) __atomic_store(slot, &boost, __ATOMIC_RELAXED);
}
