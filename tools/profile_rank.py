"""Ranks the sampling profiler's call stacks (GOW3_PROFILE=<seconds>) by function.

    python tools/profile_rank.py <capture dir> "<thread label>" [last N reports]

The labels are the profiler's: "GPU command thread", "draw recording thread", "Vulkan recording
thread", "game flip thread". Exclusive time is the innermost frame of a sample (a system DLL frame
names a wait); inclusive time counts every sample whose stack holds the function. Runtime frames
are symbolized with llvm-symbolizer against gow3_pc/out/gow3-probe.exe (image base 0x140000000),
so profile and symbolize the same build.
"""
import collections
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "gow3_pc/out/gow3-probe.exe"
SYMBOLIZER = Path(os.environ.get("MSYS2_ROOT", "C:/msys64")) / "clang64/bin/llvm-symbolizer.exe"


def main():
    folder = Path(sys.argv[1])
    label = sys.argv[2].replace(" ", "-")
    last = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    files = sorted(folder.glob(f"profile_{label}_*_stacks.txt"), key=lambda p: int(p.stem.split("_")[-2]))[-last:]
    stacks = collections.Counter()
    for f in files:
        for line in f.read_text(errors="replace").splitlines()[1:]:
            count, _, frames = line.partition(" ")
            if count.isdigit():
                stacks[frames] += int(count)
    total = sum(stacks.values())
    if not total:
        print(f"no samples for {label} in {folder}")
        return 1
    offsets = sorted({int(m.group(1), 16) for frames in stacks
                      for m in re.finditer(r"gow3-probe\.exe\+(0x[0-9a-f]+)", frames)})
    names = {}
    if offsets:
        query = "\n".join(hex(0x140000000 + o) for o in offsets) + "\n"
        out = subprocess.run([str(SYMBOLIZER), f"--obj={EXE}", "--functions=short", "--inlining=false"],
                             input=query, capture_output=True, text=True).stdout
        blocks = [b for b in out.split("\n\n") if b.strip()]
        for o, block in zip(offsets, blocks):
            lines = block.strip().splitlines()
            fn = lines[0] if lines else "??"
            where = lines[1].rsplit("/", 1)[-1].split(":")[0] if len(lines) > 1 else ""
            names[o] = f"{fn} ({where})" if fn != "??" else f"?? +{o:#x}"

    def frame_name(frame):
        m = re.match(r"gow3-probe\.exe\+(0x[0-9a-f]+)", frame)
        return names.get(int(m.group(1), 16), frame) if m else frame.split("+")[0]

    exclusive, inclusive = collections.Counter(), collections.Counter()
    for frames, n in stacks.items():
        chain = [frame_name(f) for f in frames.split(";") if f]
        if chain:
            exclusive[chain[0]] += n
            for name in set(chain):
                inclusive[name] += n
    print(f"{label}: {total} samples in {len(files)} reports")
    print("-- exclusive (innermost frame)")
    for name, n in exclusive.most_common(25):
        print(f"{100 * n / total:5.1f}%  {name}")
    print("-- inclusive")
    for name, n in inclusive.most_common(45):
        print(f"{100 * n / total:5.1f}%  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
