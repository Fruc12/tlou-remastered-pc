/* Windows red-zone protection, the loader side: red_zone.c. */
#ifndef GOW3_RED_ZONE_H
#define GOW3_RED_ZONE_H
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

/* One applied patch group: its first protected instruction and its stub (crash reports). */
typedef struct { uint64_t site; uint32_t stub, stub_bytes; } RedZoneStub;
enum { RED_ZONE_STATS = 11 };            /* scripts/red_zone.py STATS_FIELDS */
typedef struct {
    uint64_t image_size; uint8_t sha256[32];
    /* The G3RZONE1 section: stub code for image + rz_code_offset and patch groups. */
    unsigned char *rz; uint64_t rz_size, rz_code_offset;
    uint32_t rz_code_bytes, rz_groups, rz_group_bytes, rz_stats[RED_ZONE_STATS];
    RedZoneStub *rz_applied; uint32_t rz_applied_count;
    unsigned char *rz_area;              /* set by red_zone_apply */
} RedZoneTable;
typedef struct { uint32_t groups, protected_instructions, short_relays, skipped; } RedZoneReport;

/* Parses a table. NULL when the file is missing, or invalid (one stderr line). */
RedZoneTable *red_zone_load(const char *path);
/* 1 when size and sha256 match the image (as read, before anything patches it). */
int red_zone_matches(const RedZoneTable *t, const unsigned char *image, uint64_t size);
/* Bytes of stub code; the loader maps them at image + rz_code_offset. */
size_t red_zone_code_size(const RedZoneTable *t);
/* Copies the stub code to `area` (which must be image + rz_code_offset, RW) and writes each patch
 * group whose original bytes all still match the image; a changed group (game patch, hook) is
 * skipped whole, with one stderr line. Returns {0} with skipped = groups when area is misplaced. */
RedZoneReport red_zone_apply(RedZoneTable *t, unsigned char *image, unsigned char *area);
/* 1 and *site (image offset of the protected instruction) when rip is inside an applied stub. */
int red_zone_site_of_stub(const RedZoneTable *t, uintptr_t rip, uint64_t *site);

#endif
