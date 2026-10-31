/* Windows red-zone protection, the loader side. From HayatoG/tlou_pc 2bba8a6 (src/isa_rewrite.c,
 * GPL-2.0-or-later; the design is shadPS4's, src/core/cpu_patches.cpp), without its ISA emulation.
 * scripts/red_zone_table.py writes the table: HEADER, then the G3RZONE1 section (red_zone.py). */
#include "red_zone.h"
#include <stdlib.h>
#include <string.h>

enum { HEADER_BYTES = 56 };
/* Red-zone section (scripts/red_zone.py): SECTION (the last u32, a source CRC, is the script's
 * cache key), STATS, code, then the groups. */
enum { RZ_SECTION_BYTES = 36, RZ_STATS_BYTES = 4 * RED_ZONE_STATS, RZ_GROUP_BYTES = 20, RZ_PATCH_BYTES = 10,
       RZ_VERSION = 1, RZ_MAX_PATCH = 64 };
#define RZ_MAX_SECTION (256ull << 20)

/* ---- SHA-256 (FIPS 180-4), for isa_table_matches ---- */

static uint32_t ror32(uint32_t x, int n) { return x >> n | x << (32 - n); }

static void sha256_block(uint32_t h[8], const unsigned char *block) {
    static const uint32_t k[64] = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
    uint32_t w[64], v[8];
    for (int i = 0; i < 16; i++)
        w[i] = (uint32_t)block[4 * i] << 24 | (uint32_t)block[4 * i + 1] << 16 | (uint32_t)block[4 * i + 2] << 8 |
               block[4 * i + 3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = ror32(w[i - 15], 7) ^ ror32(w[i - 15], 18) ^ w[i - 15] >> 3;
        uint32_t s1 = ror32(w[i - 2], 17) ^ ror32(w[i - 2], 19) ^ w[i - 2] >> 10;
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    memcpy(v, h, sizeof v);
    for (int i = 0; i < 64; i++) {
        uint32_t t1 = v[7] + (ror32(v[4], 6) ^ ror32(v[4], 11) ^ ror32(v[4], 25)) + ((v[4] & v[5]) ^ (~v[4] & v[6])) +
                      k[i] + w[i];
        uint32_t t2 = (ror32(v[0], 2) ^ ror32(v[0], 13) ^ ror32(v[0], 22)) + ((v[0] & v[1]) ^ (v[0] & v[2]) ^ (v[1] & v[2]));
        memmove(v + 1, v, 7 * sizeof *v);
        v[4] += t1;
        v[0] = t1 + t2;
    }
    for (int i = 0; i < 8; i++) h[i] += v[i];
}

static void sha256(const unsigned char *data, uint64_t size, uint8_t out[32]) {
    uint32_t h[8] = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    uint64_t done = 0;
    for (; size - done >= 64; done += 64) sha256_block(h, data + done);
    unsigned char tail[128] = {0};
    size_t rest = (size_t)(size - done), tail_size = rest < 56 ? 64 : 128;
    memcpy(tail, data + done, rest);
    tail[rest] = 0x80;
    for (int i = 0; i < 8; i++) tail[tail_size - 1 - i] = (unsigned char)(size * 8 >> 8 * i);
    for (size_t at = 0; at < tail_size; at += 64) sha256_block(h, tail + at);
    for (int i = 0; i < 32; i++) out[i] = (uint8_t)(h[i / 4] >> (24 - 8 * (i % 4)));
}

/* ---- table ---- */

static uint64_t read_u64(const unsigned char *p) {
    uint64_t v = 0;
    for (int i = 7; i >= 0; i--) v = v << 8 | p[i];
    return v;
}

static uint32_t read_u32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint16_t read_u16(const unsigned char *p) { return (uint16_t)(p[0] | p[1] << 8); }

/* Checks the red-zone section's layout: every group, patch and stub inside its bounds. */
static int section_valid(RedZoneTable *t) {
    const unsigned char *p = t->rz;
    if (t->rz_size < RZ_SECTION_BYTES + RZ_STATS_BYTES || memcmp(p, "G3RZONE1", 8) != 0) return 0;
    t->rz_code_offset = read_u64(p + 8);
    t->rz_code_bytes = read_u32(p + 16);
    t->rz_groups = read_u32(p + 20);
    t->rz_group_bytes = read_u32(p + 24);
    if (read_u32(p + 28) != RZ_VERSION) return 0;
    for (int i = 0; i < RED_ZONE_STATS; i++) t->rz_stats[i] = read_u32(p + RZ_SECTION_BYTES + 4 * i);
    if ((uint64_t)RZ_SECTION_BYTES + RZ_STATS_BYTES + t->rz_code_bytes + t->rz_group_bytes != t->rz_size) return 0;
    if (t->rz_code_offset < t->image_size || t->rz_code_offset > (1ull << 31)) return 0;
    const unsigned char *g = p + RZ_SECTION_BYTES + RZ_STATS_BYTES + t->rz_code_bytes, *end = g + t->rz_group_bytes;
    for (uint32_t i = 0; i < t->rz_groups; i++) {
        if (end - g < RZ_GROUP_BYTES) return 0;
        uint32_t stub = read_u32(g + 8), bytes = read_u32(g + 12), patches = read_u16(g + 18);
        if (!patches || stub > t->rz_code_bytes || bytes > t->rz_code_bytes - stub) return 0;
        g += RZ_GROUP_BYTES;
        for (uint32_t k = 0; k < patches; k++) {
            if (end - g < RZ_PATCH_BYTES) return 0;
            uint64_t offset = read_u64(g);
            uint16_t length = read_u16(g + 8);
            if (!length || length > RZ_MAX_PATCH || offset > t->image_size || length > t->image_size - offset ||
                end - g < RZ_PATCH_BYTES + 2 * length)
                return 0;
            g += RZ_PATCH_BYTES + 2 * length;
        }
    }
    return g == end;
}

RedZoneTable *red_zone_load(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    unsigned char header[HEADER_BYTES];
    RedZoneTable *t = calloc(1, sizeof *t);
    if (!t || fread(header, 1, HEADER_BYTES, f) != HEADER_BYTES || memcmp(header, "G3RZTAB1", 8) != 0) goto invalid;
    t->image_size = read_u64(header + 8);
    memcpy(t->sha256, header + 16, 32);
    t->rz_size = read_u64(header + 48);
    if (t->rz_size > RZ_MAX_SECTION || !(t->rz = malloc(t->rz_size)) ||
        fread(t->rz, 1, t->rz_size, f) != t->rz_size || fgetc(f) != EOF || !section_valid(t))
        goto invalid;
    fclose(f);
    return t;
invalid:
    fclose(f);
    fprintf(stderr, "Red zone: invalid table %s\n", path);
    if (t) free(t->rz);
    free(t);
    return NULL;
}

int red_zone_matches(const RedZoneTable *t, const unsigned char *image, uint64_t size) {
    uint8_t digest[32];
    if (size != t->image_size) return 0;
    sha256(image, size, digest);
    return memcmp(digest, t->sha256, 32) == 0;
}

size_t red_zone_code_size(const RedZoneTable *t) { return t->rz_code_bytes; }

RedZoneReport red_zone_apply(RedZoneTable *t, unsigned char *image, unsigned char *area) {
    RedZoneReport report = {0};
    if (!t || !t->rz) return report;
    if (area != image + t->rz_code_offset) {
        fprintf(stderr, "Red zone: stub area not where the table expects it, protection off\n");
        report.skipped = t->rz_groups;
        return report;
    }
    free(t->rz_applied);
    t->rz_applied = calloc(t->rz_groups ? t->rz_groups : 1, sizeof *t->rz_applied);
    t->rz_applied_count = 0;
    if (!t->rz_applied) {
        report.skipped = t->rz_groups;
        return report;
    }
    const unsigned char *code = t->rz + RZ_SECTION_BYTES + RZ_STATS_BYTES, *g = code + t->rz_code_bytes;
    memcpy(area, code, t->rz_code_bytes);
    t->rz_area = area;
    for (uint32_t i = 0; i < t->rz_groups; i++) {
        uint64_t site = read_u64(g);
        uint32_t stub = read_u32(g + 8), bytes = read_u32(g + 12), protected_count = read_u16(g + 16),
                 patches = read_u16(g + 18);
        const unsigned char *first = g + RZ_GROUP_BYTES, *q = first;
        int matches = 1;
        for (uint32_t k = 0; k < patches; k++) {
            uint16_t length = read_u16(q + 8);
            if (memcmp(image + read_u64(q), q + RZ_PATCH_BYTES, length) != 0) matches = 0;
            q += RZ_PATCH_BYTES + 2 * length;
        }
        if (!matches) {
            fprintf(stderr, "Red zone: site 0x%llx skipped: bytes changed\n", (unsigned long long)site);
            report.skipped++;
        } else {
            for (const unsigned char *r = first; r < q;) {
                uint16_t length = read_u16(r + 8);
                memcpy(image + read_u64(r), r + RZ_PATCH_BYTES + length, length);
                r += RZ_PATCH_BYTES + 2 * length;
            }
            t->rz_applied[t->rz_applied_count++] = (RedZoneStub){site, stub, bytes};
            report.groups++;
            report.protected_instructions += protected_count;
            report.short_relays += patches > 1;
        }
        g = q;
    }
    return report;
}

int red_zone_site_of_stub(const RedZoneTable *t, uintptr_t rip, uint64_t *site) {
    if (!t || !t->rz_area || rip < (uintptr_t)t->rz_area || rip - (uintptr_t)t->rz_area >= t->rz_code_bytes) return 0;
    uint32_t at = (uint32_t)(rip - (uintptr_t)t->rz_area), lo = 0, hi = t->rz_applied_count;
    while (lo < hi) {   /* stubs are laid out in group order: ascending offsets */
        uint32_t mid = lo + (hi - lo) / 2;
        if (t->rz_applied[mid].stub + t->rz_applied[mid].stub_bytes <= at) lo = mid + 1;
        else hi = mid;
    }
    if (lo == t->rz_applied_count || at < t->rz_applied[lo].stub) return 0;
    *site = t->rz_applied[lo].site;
    return 1;
}
