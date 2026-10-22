#!/usr/bin/env python3
"""The Last of Us Remastered (CUSA00552): prepare the executable and start it in the runtime.

Without --boot it only lists the PS4 imports the runtime does not provide (--check-imports).
The update (a folder next to the game named like it plus -patch) is laid over the game: its
eboot.bin, sce_module and sce_sys are prepared, and the runtime reads its files over the game's.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPDATE_SUFFIXES = ("-patch", "-update")


def find_update(game):
    chosen = os.environ.get("TLOU_UPDATE", "")
    if chosen == "0":
        return None
    candidates = [Path(chosen)] if chosen else [game.parent / (game.name + s) for s in UPDATE_SUFFIXES]
    for candidate in candidates:
        if (candidate / "eboot.bin").is_file() and (candidate / "sce_sys/param.sfo").is_file():
            return candidate.resolve()
    return None


def app_version(folder):
    """APP_VER from the folder's sce_sys/param.sfo, or None."""
    sys.path.insert(0, str(ROOT / "gow3_pc/scripts"))
    try:
        from prepare import sfo
        return sfo((folder / "sce_sys/param.sfo").read_bytes()).get("APP_VER")
    except (OSError, ValueError, ImportError):
        return None
    finally:
        sys.path.pop(0)


def boot_view(base, update):
    """Copies of what the prepare scripts read (eboot.bin, sce_module, sce_sys), the update's
    over the game's, in analysis/views (copied again only when a source changes)."""
    chosen = {}
    for layer in (base, update) if update else (base,):
        for entry in layer.iterdir():
            if entry.is_file() and entry.name.lower() == "eboot.bin":
                chosen["eboot.bin"] = ("eboot.bin", entry)
            elif entry.is_dir() and entry.name.lower() in ("sce_module", "sce_sys"):
                for path in entry.rglob("*"):
                    if path.is_file():
                        relative = path.relative_to(layer)
                        chosen[str(relative).lower()] = (str(relative), path)
    view = ROOT / "analysis/views" / ("boot-" + (update or base).name)
    for relative, source in chosen.values():
        dest = view / relative
        wanted = source.stat()
        try:
            current = dest.stat()
            if current.st_size == wanted.st_size and abs(current.st_mtime - wanted.st_mtime) <= 2:
                continue
        except OSError:
            pass
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        os.utime(dest, ns=(wanted.st_atime_ns, wanted.st_mtime_ns))
    return view


def convert_frames(capture):
    """The presented frames (output_NNN_WxH.raw, RGBA) as PNG files next to them."""
    import re
    try:
        from PIL import Image
    except ImportError:
        print("Pillow is not installed: frames stay as .raw files")
        return
    for raw in sorted(capture.glob("output*.raw")):
        size = re.search(r"_(\d+)x(\d+)\.raw$", raw.name)
        if not size:
            continue
        w, h = int(size.group(1)), int(size.group(2))
        data = raw.read_bytes()
        if len(data) < w * h * 4:
            continue
        image = Image.frombytes("RGBA", (w, h), data[:w * h * 4]).convert("RGB")
        image.thumbnail((1280, 720))
        image.save(raw.with_suffix(".png"))
    print(f"Frames: {capture}")


def game_executable():
    built = ROOT / "gow3_pc/out/gow3-probe.exe"
    if not built.is_file():
        raise SystemExit(f"Build the runtime first (gow3_pc/build.sh): {built} is missing")
    return built


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, default=ROOT.parent / "CUSA00552")
    parser.add_argument("--boot", action="store_true", help="Execute the game after preparation")
    parser.add_argument("--cpu-only", action="store_true")
    parser.add_argument("--seconds", type=int, default=60, help="Process time limit; 0 disables it")
    parser.add_argument("--capture", type=int, default=0, metavar="SECONDS",
                        help="Save the displayed frame every SECONDS (analysis/tlou/captures)")
    parser.add_argument("--saves", type=Path, default=None,
                        help="Saves and game settings folder (default analysis/tlou-user, the "
                             "player's): a test profile leaves the player's saves alone")
    args = parser.parse_args()
    game = args.game.resolve()
    update = find_update(game)
    if update:
        print(f"Game {game} (version {app_version(game)}) with its update {update} "
              f"(version {app_version(update)}): the update's executable and files are used", flush=True)
    else:
        print(f"Game {game} (version {app_version(game)}); no update found next to it "
              f"({game.name}-patch or {game.name}-update, or TLOU_UPDATE=<folder>)", flush=True)
    out = ROOT / "analysis/tlou"
    user = ROOT / "analysis/tlou-user"
    user.mkdir(parents=True, exist_ok=True)
    # Diagnostic switches (tlou_pad.py) last for one run: a new run starts with the defaults.
    for name in ("disabled-optimizations.txt", "skip.txt", "readback.trigger", "capture.trigger",
                 "probe-pad.txt"):
        (user / name).unlink(missing_ok=True)
    # The diagnostic files and the shader cache stay in analysis/tlou-user either way.
    saves = args.saves.resolve() if args.saves else user
    saves.mkdir(parents=True, exist_ok=True)
    view = boot_view(game, update)
    scripts = ROOT / "gow3_pc/scripts"
    for script in ("prepare.py", "link_modules.py", "content_profile.py"):
        subprocess.run([sys.executable, str(scripts / script), str(view), "--out", str(out)], check=True)

    env = dict(os.environ)
    msys = Path(os.environ.get("MSYS2_ROOT", "C:/msys64"))
    env["PATH"] = str(msys / "clang64/bin") + os.pathsep + env.get("PATH", "")
    env["GOW3_GPU_USER_DIR"] = str(user)
    env.setdefault("GOW3_CONFIG", str(user / "tlou.ini"))
    # A draw whose pipeline is still compiling in the background is skipped: the curtain on the
    # title screen and the characters' hair flashed white the first time they were drawn. New
    # pipelines are compiled at once instead (a short stall the first time; the pipeline cache
    # keeps them), unless the player chose otherwise in the in-game menu (async_shaders).
    try:
        chosen = "async_shaders=" in Path(env["GOW3_CONFIG"]).read_text(encoding="utf-8", errors="replace")
    except OSError:
        chosen = False
    if not chosen:
        env.setdefault("GOW3_ASYNC_SHADERS", "0")
    # The game compares sceKernelGetDirectMemorySize with a retail console's 4608 MiB; any other
    # size makes it reserve a development kit's 768 MiB debug area.
    env.setdefault("GOW3_DMEM_REPORT_MB", "4608")
    env.setdefault("GOW3_DIRECT_MEMORY_ACCESS", "1")
    env.setdefault("GOW3_PIPELINE_CACHE", "1")
    env.setdefault("GOW3_PIPELINE_BINARIES", "1")
    # Frame rate (Sarah's bedroom, GTX 1050 Ti Mobile: 20.6 FPS with none of these, 47 with all
    # and the priority below; 48-53 walking upstairs): multithreaded rendering (draw and Vulkan
    # recording threads), 28 FPS on its own with the DMA windows; the DMA shaders' guest
    # memory synchronized in 256 KiB windows at the addresses in their user data instead of every
    # CPU-dirty range; and one frame in flight, the game building the next frame while the GPU
    # command thread still decodes the last one, instead of both waiting for the other at each
    # sceGnmSubmitDone (liverpool.h, FramesInFlight).
    env.setdefault("GOW3_DRAW_PIPE", "1")
    env.setdefault("GOW3_VK_RECORD_THREAD", "1")
    env.setdefault("GOW3_DMA_SYNC", "pointers 256")
    env.setdefault("GOW3_FRAMES_IN_FLIGHT", "1")
    # At normal priority the GPU command thread and the draw and Vulkan recording threads shared
    # cores with the game's six busy job workers in some sessions, for the whole session: 33-34
    # instead of 46-47 FPS in 5 of 11 runs. Above normal: 47 FPS in 4 runs of 4.
    env.setdefault("GOW3_GPU_THREAD_PRIORITY", "above")
    # A game thread's write into memory the GPU is still writing waits for that GPU work itself,
    # not on the GPU command thread (which stopped drawing meanwhile): 32-36 -> 41-47 FPS in the
    # bedroom (4 alternating runs, 22 Oct 2026). Sarah's hair shakes with and without it.
    env.setdefault("GOW3_FETCH_NO_BLOCK", "1")
    # New pipelines the draw preparation workers see ahead are built on the compiler threads, in
    # parallel, before the GPU command thread reaches their draws (an empty cache: 573 -> 167 ms
    # of compiling on that thread). The first visit of an area hitches less.
    env.setdefault("GOW3_PREFETCH_PIPELINES", "1")
    env.setdefault("GOW3_NATIVE_TSC", "1")
    env.setdefault("GOW3_FRAME_STATS", "1")
    # Scripted controller input (tools/tlou_pad.py writes it).
    env.setdefault("GOW3_PAD_FILE", str(user / "probe-pad.txt"))
    # Diagnostics driven by tlou_pad.py: the frame analyzer (every pass, its shaders and textures,
    # written to <user>/captures) and shaders whose draws are skipped (hex hashes, re-read live).
    env.setdefault("GOW3_CAPTURE_TRIGGER", str(user / "capture.trigger"))
    # The game never draws into its display buffers, so the analyzer sees no frame boundary: it
    # records this many passes (a number in the trigger file overrides it).
    env.setdefault("GOW3_CAPTURE_PASSES", "400")
    env.setdefault("GOW3_SKIP_FILE", str(user / "skip.txt"))
    # "<lo> <hi>" (hex) in this file copies that GPU-written range back to guest memory once.
    env.setdefault("GOW3_READBACK_TRIGGER", str(user / "readback.trigger"))
    # Optimizations switched off while the game runs (a bit mask, src/runtime_memory.c).
    env.setdefault("GOW3_TOGGLE_FILE", str(user / "disabled-optimizations.txt"))
    if os.environ.get("TLOU_GPU_CHECKPOINTS") == "1":
        env.setdefault("GOW3_GPU_CHECKPOINTS", "1")

    command = [str(game_executable()), str(out / "boot-linked.bin"),
               "--no-game-hooks", "--low-image", "--content-profile", str(out / "content.bin"),
               "--app0", str(game), "--user", str(saves)]
    if update:
        command += ["--app0-overlay", str(update)]
    command += ["--guest-path", "/app0/eboot.bin"]
    if not args.boot:
        command.append("--check-imports")
    if args.cpu_only:
        command.append("--cpu-only")
    name = ("boot" if args.boot else "check-imports") + ("-cpu" if args.cpu_only else "")
    result = {"command": command, "update": str(update) if update else None, "timeout_seconds": args.seconds}
    capture = None
    if args.capture:
        # The presenter writes the displayed frame each time the trigger file appears.
        capture = out / "captures" / str(time.time_ns())
        capture.mkdir(parents=True)
        env["GOW3_FRAME_DUMP_TRIGGER"] = str(capture / "trigger")
        env["GOW3_DUMP_DIR"] = str(capture)
        result["capture_directory"] = str(capture)
    start = time.monotonic()
    with (out / (name + ".log")).open("wb") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        # Test scripts stop this instance by its PID, never a game the player started.
        (out / "probe.pid").write_text(str(process.pid), encoding="ascii")
        deadline = start + args.seconds if args.seconds else None
        result["timed_out"] = False
        while process.poll() is None:
            if deadline and time.monotonic() >= deadline:
                process.kill()
                result["timed_out"] = True
                break
            try:
                process.wait(timeout=args.capture or 1)
            except subprocess.TimeoutExpired:
                if capture:
                    (capture / "trigger").touch()
        result["exit_code"] = process.wait()
    if capture:
        convert_frames(capture)
    result["elapsed_seconds"] = round(time.monotonic() - start, 3)
    (out / (name + ".json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
    attempt = out / "attempts" / f"{name}-{time.time_ns()}"
    attempt.mkdir(parents=True)
    shutil.copy2(out / (name + ".log"), attempt / (name + ".log"))
    print(json.dumps(result, indent=2))
    print(f"Log: {out / (name + '.log')}")
    return 124 if result["timed_out"] else result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
