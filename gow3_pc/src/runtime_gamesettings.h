/* The game's own draw and shadow distances, scaled from the in-game menu (Image tab), once the
 * settings block that holds them is found in the image (recognised by the game's defaults before
 * anything is written). Not located in The Last of Us Remastered yet: nothing is found, and the
 * menu keeps its distance sliders disabled. */
#pragma once
#include <stdint.h>

void runtime_gamesettings_set_image(unsigned char *image, uint64_t size);
/* Called often (the pad's sampling, on the game's thread): applies the menu's values, at most
 * twice a second. */
void runtime_gamesettings_tick(void);
/* 1 once this game's settings were found. */
int runtime_gamesettings_active(void);
