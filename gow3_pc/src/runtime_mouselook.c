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
