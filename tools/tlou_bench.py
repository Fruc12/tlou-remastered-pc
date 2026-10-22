#!/usr/bin/env python3
"""Repeatable performance measurement: starts the game on the test profile (analysis/tlou-test-saves),
continues its checkpoint (Sarah's bedroom), waits, then samples for --seconds: the game's frame
statistics (FPS, GPU command thread) and the GPU's load (nvidia-smi). Extra environment variables
for the run are given as NAME=value arguments; the game is stopped afterwards (by its own PID).

usage: tlou_bench.py [--label text] [--seconds 30] [NAME=value ...]
"""
import argparse
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "analysis/tlou/boot.log"


def pad(*steps):
    subprocess.run([sys.executable, "-W", "ignore", str(ROOT / "tools/tlou_pad.py"), *steps],
                   check=True, stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", default="")
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--turn", action="store_true", help="Turn the camera during the measurement")
    parser.add_argument("--threads", action="store_true", help="Also sample the busiest threads' CPU load")
    parser.add_argument("--saves", type=Path, default=ROOT / "analysis/tlou-test-saves",
                        help="Saves folder whose checkpoint is continued (a copy of the player's, never theirs)")
    parser.add_argument("vars", nargs="*")
    args = parser.parse_args()
    env = dict(os.environ)
    for item in args.vars:
        name, _, value = item.partition("=")
        env[name] = value
    pid_file = ROOT / "analysis/tlou/probe.pid"
    pid_file.unlink(missing_ok=True)
    probe = subprocess.Popen([sys.executable, str(ROOT / "tools/probe_tlou.py"), "--boot", "--seconds", "900",
                              "--capture", "800", "--saves", str(args.saves)],
                             env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # This run's game, read once: a later run rewrites probe.pid, and stopping by that file at the
    # end once stopped another run's game.
    game_pid = ""
    for _ in range(600):
        if pid_file.exists() and (game_pid := pid_file.read_text().strip()):
            break
        time.sleep(0.2)
    try:
        pad("wait=60", "cross", "wait=6", "cross", "wait=4", "cross", "wait=60")
        if not re.search(r"Switching world: from core to world-", LOG.read_text(encoding="utf-8", errors="replace")):
            print("the checkpoint did not load")
            return 1
        start_line = len(LOG.read_text(encoding="utf-8", errors="replace").splitlines())
        # The 3D engine's load from Windows' GPU counters (nvidia-smi reports none on Optimus laptops).
        counter = (f"$s = Get-Counter '\\GPU Engine(*engtype_3D)\\Utilization Percentage' "
                   f"-SampleInterval 1 -MaxSamples {max(args.seconds - 2, 1)}; "
                   "$s | ForEach-Object { ($_.CounterSamples | Measure-Object CookedValue -Sum).Sum }")
        smi = subprocess.Popen(["powershell", "-NoProfile", "-Command", counter],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        # The busiest threads of the game process (mean % of one hardware thread, thread ID).
        threads = None
        if args.threads:
            # Each thread's CPU time over the measurement (Get-Process: not localized, unlike the
            # per-thread performance counters), as a share of one hardware thread.
            span = max(args.seconds - 4, 1)
            game = game_pid
            per_thread = (f"$a = @{{}}; foreach ($t in (Get-Process -Id {game}).Threads) {{ "
                          "$a[$t.Id] = $t.TotalProcessorTime.TotalMilliseconds }; "
                          f"Start-Sleep -Seconds {span}; foreach ($t in (Get-Process -Id {game}).Threads) {{ "
                          "if ($a.ContainsKey($t.Id)) { '' + $t.Id + '=' + "
                          f"(($t.TotalProcessorTime.TotalMilliseconds - $a[$t.Id]) / {span * 10}) }} }}")
            threads = subprocess.Popen(["powershell", "-NoProfile", "-Command", per_thread],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if args.turn:
            end = time.monotonic() + args.seconds
            while time.monotonic() < end:
                pad("hold=2:rx=230", "hold=2:rx=30")
        else:
            time.sleep(args.seconds)
        gpu = []
        for line in smi.communicate(timeout=60)[0].splitlines():
            try:
                gpu.append(float(line.replace(",", ".")))
            except ValueError:
                pass
        busiest = []
        if threads:
            for line in threads.communicate(timeout=120)[0].splitlines():
                tid, _, value = line.partition("=")
                try:
                    busiest.append((float(value.replace(",", ".")), int(tid)))
                except ValueError:
                    pass
            busiest = sorted(busiest, reverse=True)[:8]
        lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()[start_line:]
        fps = [float(m.group(1)) for l in lines if (m := re.match(r"Frame stats: ([0-9.]+) FPS", l))]
        worst = [float(m.group(1)) for l in lines if (m := re.search(r"worst frame ([0-9.]+) ms", l))]
        thread = [l for l in lines if l.startswith("Frame stats")]
        print(f"== {args.label or ' '.join(args.vars) or 'baseline'}")
        if fps:
            print(f"FPS mean {statistics.mean(fps):.1f} (min {min(fps):.1f}, max {max(fps):.1f}), "
                  f"worst frame {max(worst):.0f} ms")
        if gpu:
            print(f"GPU 3D engine load {statistics.mean(gpu):.0f}% (min {min(gpu):.0f}, max {max(gpu):.0f})")
        if busiest:
            print("Busiest threads (% of a hardware thread, thread ID): " +
                  ", ".join(f"{load:.0f}% ({tid})" for load, tid in busiest))
        if thread:
            m = re.search(r"GPU thread ([0-9.]+) us/draw, ([0-9]+) draws/frame, idle ([0-9.]+)%; blocked: (.*?);",
                          thread[-1])
            if m:
                print(f"GPU command thread: {m.group(1)} us/draw, {m.group(2)} draws/frame, idle {m.group(3)}%, "
                      f"blocked {m.group(4)}")
        for key in ("Stall:", "DMA sync (5 s)", "SRT sync (5 s)", "       fault handlers", "       GPU thread on CPU",
                    "       ms in:", "Memory:"):
            found = [l for l in lines if l.startswith(key)]
            if found:
                print(found[-1][:220])
        return 0
    finally:
        try:
            subprocess.run(["taskkill", "/PID", game_pid, "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
        probe.wait(timeout=60)


if __name__ == "__main__":
    sys.exit(main())
