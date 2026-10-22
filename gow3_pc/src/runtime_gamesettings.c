/* The game's draw and shadow distances (see runtime_gamesettings.h): no settings block is known
 * for The Last of Us Remastered yet, so nothing is found and nothing is written. */
#include "runtime_gamesettings.h"

void runtime_gamesettings_set_image(unsigned char *base, uint64_t size) {
    (void)base;
    (void)size;
}

void runtime_gamesettings_tick(void) {}

int runtime_gamesettings_active(void) { return 0; }
