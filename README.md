# The Last of Us Remastered — PC port

Runs the PS4 **The Last of Us Remastered** (CUSA00552, with its update 1.11) natively on Windows.
The game's own x86-64 code runs directly on the PC; a runtime supplies the PS4 system libraries,
and a Vulkan renderer (the shadPS4 video core) executes the PS4 GPU work.

> **No game files are in this repository.** You need your own copy of the game (the dumped
> CUSA00552 folder, and its update). This project is not affiliated with Sony Interactive
> Entertainment or Naughty Dog.

## Status

Work in progress. The game boots through the logos, the menus and the opening cinematic into the
prologue in Sarah's house, which renders correctly (lighting, skinned characters, bloom).

- **Frame rate:** about 47 FPS in Sarah's bedroom and 48-53 FPS walking upstairs on a laptop with
  a GTX 1050 Ti Mobile (4 GB), where the GPU is the limit; 30-34 FPS in the Quarantine Zone's
  heavy streets, where the game's own threads are. Frames are shown as soon as they are done (a
  480 Hz vblank, capped at the display's rate; `GOW3_VBLANK_HZ=60` for the old 60 Hz pacing).
  `Start-TLOU-Profile.cmd` starts the game with the sampling profiler (reports in
  `analysis\tlou\profile-user`, read with `tools/profile_rank.py`).
- **Known issues:** the HUD of the item inspection screen does not show; with the 60 Hz vblank
  the characters' hair (Sarah's, Joel's) sometimes stretched (not seen with the default 480 Hz
  one). A frame that compiles many new shaders can pause the game for
  a few seconds: the game's own frame watchdog stopped it after 2 s, and is now patched to 20 s
  (`TLOU_FIXES=none` leaves the game unpatched). If a load ever hangs, start with
  `GOW3_FRAMES_IN_FLIGHT=0` (slower).
- **Not available for this game yet:** mouse camera (the mouse drives the right stick instead),
  the draw distance sliders and keyboard button prompts, which need the game's own camera code,
  settings block and prompt textures to be located.

## Requirements

- Windows 10 or 11 (64-bit).
- A CPU from Intel's 4th-generation Core (Haswell) or newer, or any AMD Ryzen: the game needs
  AVX, F16C, BMI1, MOVBE and LZCNT.
- A graphics card or integrated GPU with Vulkan 1.3 and a current driver.
- Python 3.10 or newer (the preparation scripts and the start script).
- About 6 GB of free RAM for the game.

## Playing

1. Put the game folder `CUSA00552` next to this repository's folder, and the update next to it as
   `CUSA00552-patch` (or name another update folder with `TLOU_UPDATE=<folder>`). An update you
   only have as a PKG unpacks there with `python tools/install_update.py <update.pkg> <game folder>`.
2. Build the runtime (below), then start the game with `Start-TLOU.cmd`, or
   `python tools/probe_tlou.py --boot --seconds 0 [--game <game folder>]`.
3. Saves and settings stay in `analysis/tlou-user`; the log is `analysis/tlou/boot.log`. Each
   session also records your controller input (`analysis/tlou/pad-record-*.txt`, the newest 5),
   so a crash can be replayed on the same route; `TLOU_RECORD_PAD=0` turns that off.
4. With this repository on a hard disk, put the shader cache (`analysis/tlou-user/cache`, about
   700 MB) on an SSD: each new area loads hundreds of its files, and on a hard disk that pauses
   the game for seconds. With the game closed, move the folder, then link it back:
   `mklink /J analysis\tlou-user\cache <folder on the SSD>` (in `cmd`).

The in-game menu (Insert, or R3+L2 on a controller) holds the graphics, controls and frame rate
settings.

**Without a DualShock 4:** the touchpad (backpack, crafting) is Tab / Backspace on the keyboard
or Back/View on an Xbox-style controller. Shaking the controller is G on the keyboard or the
Share/Capture button (`GOW3_KEY_MAP` / `GOW3_PAD_MAP` `shake=...` rebind it). The flashlight
never flickers out by default, so it needs no shake: Celogamez's GoldHEN cheat "Flashlight Does
Not Turn Off" (`TLOU_CHEATS=none` turns it off).

## Building

From an MSYS2 **CLANG64** shell:

```bash
pacman -S --needed git patch \
  mingw-w64-clang-x86_64-{toolchain,cmake,ninja,pkgconf,python} \
  mingw-w64-clang-x86_64-{vulkan-headers,vulkan-loader,vulkan-memory-allocator,glslang} \
  mingw-w64-clang-x86_64-{sdl3,fmt,boost,robin-map,xxhash,ffmpeg,zydis} \
  mingw-w64-clang-x86_64-{spirv-tools,spirv-headers,spirv-cross}
git submodule update --init --recursive
gow3_pc/build.sh                 # the runtime: gow3_pc/out/gow3-probe.exe
```

Clone with `core.autocrlf=false`: line-ending conversion breaks the FSR-Vulkan patches.

## Repository layout

| Path | Contents |
|---|---|
| `gow3_pc/` | The runtime: C runtime (`src/`), GPU library (`gpu/`: shadPS4 video core and shims), preparation scripts (`scripts/`). Diagnostics settings: [gow3_pc/README.md](gow3_pc/README.md). |
| `tools/probe_tlou.py` | Prepares the game's executable (with its update) and starts the runtime with this game's settings. |
| `tools/tlou_pad.py`, `tools/tlou_bench.py` | Scripted controller input, frame captures and analysis; a repeatable frame rate measurement on a test profile. |
| `tools/decode_dump.py`, other `tools/` | Image dump decoding and other diagnostics. |
| `tools/install_update.py` | Unpacks an update PKG next to the game folder (PkgTool, `tools/pkgtool`). |

## Credits and license

- The runtime comes from BilalReloaded's PS4 port runtime
  ([GitHub](https://github.com/bc160201983)), which started from FelipePrado0's
  [SpartanPort](https://github.com/FelipePrado0/SpartanPort) (gow3_pc; whose internal names, such as
  `GOW3_*` settings, it keeps), and the [shadPS4](https://github.com/shadps4-emu/shadPS4) video core.
- The camera motion for temporal anti-aliasing (`CameraMotion::OnVelocityConstants` and the motion
  vector mode) comes from SuperMedo's PS4 port ([GitHub](https://github.com/Supermedo), GPL v2).
- **NVIDIA DLSS:** DLAA uses NVIDIA DLSS technology through the DLSS bridge adapted from
  [IFreemz/shadPS4-Bloodborne-DLSS-FSR](https://github.com/IFreemz/shadPS4-Bloodborne-DLSS-FSR)
  (MIT). NVIDIA, RTX and DLSS are trademarks of NVIDIA Corporation.
- AMD FSR 4: the v07 INT8 model as built by [Q2RTX](https://github.com/FireBurn/Q2RTX) from AMD's
  MIT-licensed FidelityFX SDK source.
- Third-party code: FSR (AMD), imgui, magic_enum, miniz, xbyak, LibAtrac9, FFmpeg, SDL3, PkgTool
  (LibOrbisPkg, LGPL-3.0).
- Licensed under the GNU GPL v2 or later (see `gow3_pc/LICENSE`).
