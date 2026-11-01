"""Copies a Windows Python installation into the package (python/): the interpreter, the standard
library without tests and tools, Tkinter (DLLs, tcl) and Pillow. Players need no Python installed.
From bc160201983/Uncharted-The-Nathan-Drake-Collection-PC-port (GPL-2.0-or-later).

usage: copy_python.py <python home> <destination>
"""
import shutil
import sys
from pathlib import Path

SKIP_LIB = {"site-packages", "test", "tests", "idlelib", "ensurepip", "turtledemo", "__pycache__",
            "lib2to3", "venv", "pydoc_data"}
SITE_PACKAGES = ("PIL",)


def main():
    home, dest = Path(sys.argv[1]), Path(sys.argv[2])
    dest.mkdir(parents=True, exist_ok=True)
    for pattern in ("python.exe", "pythonw.exe", "python3.dll", "python3*.dll", "vcruntime140*.dll",
                    "LICENSE.txt"):
        for path in home.glob(pattern):
            shutil.copy2(path, dest / path.name)
    for folder in ("DLLs", "tcl"):
        if (home / folder).exists():
            shutil.copytree(home / folder, dest / folder, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__"))

    def ignore_lib(directory, names):
        return {name for name in names if name in SKIP_LIB or name.endswith(".pyc")}

    shutil.copytree(home / "Lib", dest / "Lib", dirs_exist_ok=True, ignore=ignore_lib)
    site = dest / "Lib" / "site-packages"
    site.mkdir(exist_ok=True)
    for name in SITE_PACKAGES:
        found = sorted((home / "Lib" / "site-packages").glob(name + "*"))
        if not found:
            raise SystemExit(f"{name} is not installed in {home}")
        for path in found:
            if path.is_dir():
                shutil.copytree(path, site / path.name, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(path, site / path.name)
    for path in (home / "Lib" / "site-packages").glob("pillow*"):
        if path.is_dir():
            shutil.copytree(path, site / path.name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__"))


if __name__ == "__main__":
    main()
