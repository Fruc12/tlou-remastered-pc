"""Captures every thread's stack of the running game when its log reports a GPU stall:
"Frame wait over 1 s" or "Frame wait: released the guest" (src: Liverpool::WaitFramesRetired).

    python tools/stall_watch.py [--log analysis/tlou/boot.log] [--out analysis/tlou/stall-stacks.txt]

Waits for analysis/tlou/probe.pid (the game a test script started), then polls the log; the
first stall line gets a stack report (tools/hang_report.py), symbolized against
gow3_pc/out/gow3-probe.exe. Ends when the game exits or after one report.
"""
import argparse
import ctypes
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import hang_report  # noqa: E402

SYMBOLIZER = Path(os.environ.get("MSYS2_ROOT", "C:/msys64")) / "clang64/bin/llvm-symbolizer.exe"
EXE = ROOT / "gow3_pc/out/gow3-probe.exe"
STALL = re.compile(r"Frame wait over 1 s|Frame wait: released the guest")


class Process:
    def __init__(self, pid):
        access = 0x1F0FFF  # PROCESS_ALL_ACCESS
        self.pid = pid
        self._handle = ctypes.windll.kernel32.OpenProcess(access, False, pid)
        if not self._handle:
            raise OSError(f"cannot open process {pid}")


def symbolize(lines):
    offsets = sorted({int(m.group(1), 16) for line in lines for m in re.finditer(r"gow3-probe\.exe\+(0x[0-9a-f]+)", line)})
    if not offsets:
        return lines
    query = "\n".join(hex(0x140000000 + o) for o in offsets) + "\n"
    out = subprocess.run([str(SYMBOLIZER), f"--obj={EXE}", "--functions=short", "--inlining=false"],
                         input=query, capture_output=True, text=True).stdout
    names = {}
    for o, block in zip(offsets, [b for b in out.split("\n\n") if b.strip()]):
        parts = block.strip().splitlines()
        where = parts[1].rsplit("/", 1)[-1] if len(parts) > 1 else ""
        names[o] = f"{parts[0]} ({where})"
    return [re.sub(r"gow3-probe\.exe\+(0x[0-9a-f]+)",
                   lambda m: f"{m.group(0)} {names.get(int(m.group(1), 16), '')}", line) for line in lines]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", type=Path, default=ROOT / "analysis/tlou/boot.log")
    parser.add_argument("--out", type=Path, default=ROOT / "analysis/tlou/stall-stacks.txt")
    parser.add_argument("--pid-file", type=Path, default=ROOT / "analysis/tlou/probe.pid")
    args = parser.parse_args()
    pid = 0
    started = time.time()
    for _ in range(3000):
        # A probe.pid from before this watcher started names an earlier run's game.
        if args.pid_file.exists() and args.pid_file.stat().st_mtime >= started - 1 \
                and args.pid_file.read_text().strip().isdigit():
            pid = int(args.pid_file.read_text().strip())
            break
        time.sleep(0.1)
    if not pid:
        print("no game started")
        return 1
    process = Process(pid)
    seen = 0
    while ctypes.windll.kernel32.WaitForSingleObject(process._handle, 0) != 0:
        try:
            text = args.log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        match = STALL.search(text, seen)
        if match:
            line = text[match.start():text.find("\n", match.start())]
            # Samples 0.4 s apart: a thread that waits stays in place, one that works moves.
            report = [line]
            for sample in range(8):
                report += ["", f"sample {sample + 1}:"] + symbolize(hang_report.thread_report(process))
                time.sleep(0.4)
            args.out.write_text("\n".join(report) + "\n", encoding="utf-8")
            print(f"stall: {line}\nstacks written to {args.out}")
            return 0
        seen = max(0, len(text) - 200)
        time.sleep(0.05)
    print("the game exited without a stall")
    return 0


if __name__ == "__main__":
    sys.exit(main())
