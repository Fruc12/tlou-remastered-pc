#!/usr/bin/env python3
"""Drive a running probe_tlou.py game: press buttons and save the displayed frame.

Steps run in order, e.g.:  tlou_pad.py cross wait=3 down cross shot
  <tokens>       buttons held together for --milliseconds, joined with + (cross, up+l1, lx=0)
  wait=<s>       pause
  hold=<s>:<t>   hold tokens <t> (joined with +) for <s> seconds
  shot           save the next displayed frame (needs probe_tlou.py --capture) and wait for it
  analyze        record the next frame's passes (frame analyzer, analysis/tlou-user/captures)
  skip=<hashes>  skip draws with these shaders (comma separated hex; skip= clears)
  readback=<lo>,<hi>  copy a GPU-written guest range (hex) back to guest memory once
  toggle=<mask>  switch optimizations off (decimal bit mask, src/runtime_memory.c; toggle=0 restores)
"""
import argparse
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAD = ROOT / "analysis/tlou-user/probe-pad.txt"


def press(tokens, seconds):
    try:
        PAD.write_text(" ".join(tokens), encoding="ascii")
        time.sleep(seconds)
    finally:
        PAD.write_text("", encoding="ascii")
    time.sleep(0.15)


def shot():
    captures = ROOT / "analysis/tlou/captures"
    folder = max(captures.iterdir(), key=lambda p: p.stat().st_mtime)
    before = set(folder.glob("output*.raw"))
    (folder / "trigger").touch()
    for _ in range(100):
        time.sleep(0.1)
        new = set(folder.glob("output*.raw")) - before
        if new:
            time.sleep(0.5)
            raw = sorted(new)[-1]
            try:
                import re
                from PIL import Image
                w, h = map(int, re.search(r"_(\d+)x(\d+)\.raw$", raw.name).groups())
                image = Image.frombytes("RGBA", (w, h), raw.read_bytes()[:w * h * 4]).convert("RGB")
                image.thumbnail((960, 540))
                image.save(raw.with_suffix(".png"))
                image.save(folder / "last.png")
                # Brightness: the mean and the darkest tenth (a veil lifts the dark parts).
                levels = sorted(image.convert("L").getdata())
                brightness = f" (mean {sum(levels) / len(levels):.1f}, dark 10% {levels[len(levels) // 10]})"
            except (ImportError, AttributeError, ValueError) as error:
                print(f"shot: no PNG ({error})")
                brightness = ""
            print(f"shot: {raw}{brightness}")
            return
    print("shot: no frame (is the game running with --capture?)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("steps", nargs="+")
    parser.add_argument("--milliseconds", type=int, default=120)
    args = parser.parse_args()
    for step in args.steps:
        if step.startswith("wait="):
            time.sleep(float(step[5:]))
        elif step.startswith("hold="):
            seconds, tokens = step[5:].split(":", 1)
            press(tokens.split("+"), float(seconds))
        elif step == "shot":
            shot()
        elif step.startswith("analyze"):
            captures = ROOT / "analysis/tlou-user/captures"
            before = set(captures.glob("frame_*.txt")) if captures.is_dir() else set()
            # The game never draws into its display buffers, so frames have no boundary the
            # analyzer sees: it records a number of passes instead (analyze=<passes>, 300).
            passes = step.split("=", 1)[1] if "=" in step else "300"
            (ROOT / "analysis/tlou-user/capture.trigger").write_text(passes, encoding="ascii")
            for _ in range(150):
                time.sleep(0.1)
                new = set(captures.glob("frame_*.txt")) - before if captures.is_dir() else set()
                if new:
                    time.sleep(0.5)
                    print(f"analyze: {sorted(new)[-1]}")
                    break
            else:
                print("analyze: no capture written")
        elif step.startswith("toggle="):
            (ROOT / "analysis/tlou-user/disabled-optimizations.txt").write_text(step[7:], encoding="ascii")
            time.sleep(1.0)  # re-read every 250 ms
        elif step.startswith("readback="):
            lo, hi = step[9:].split(",")
            (ROOT / "analysis/tlou-user/readback.trigger").write_text(f"{lo} {hi}\n", encoding="ascii")
            time.sleep(1.0)
        elif step.startswith("skip="):
            hashes = [h for h in step[5:].split(",") if h]
            (ROOT / "analysis/tlou-user/skip.txt").write_text(" ".join(hashes), encoding="ascii")
            time.sleep(1.0)  # the renderer re-reads the file every 500 ms
        else:
            press(step.split("+"), args.milliseconds / 1000)


if __name__ == "__main__":
    main()
