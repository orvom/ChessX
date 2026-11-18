"""Build a single-file Windows executable (dist/ChessX.exe) with PyInstaller.

Usage:  python scripts/build_exe.py

Needs: pip install pyinstaller, and stockfish/stockfish.exe (python scripts/get_stockfish.py).
Everything inside ./pieces is bundled - do NOT publish a build made with the non-redistributable piece sets
(see THIRD_PARTY.md). Build from a clean clone (no scripts/get_pieces.py run) to publish a release.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEP = os.pathsep


def main():
    sf = os.path.join(ROOT, "stockfish", "stockfish.exe")
    if not os.path.isfile(sf):
        print("Missing", sf, "- run: python scripts/get_stockfish.py")
        return 1
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--noconsole", "--name", "ChessX",
           "--distpath", os.path.join(ROOT, "dist"), "--workpath", os.path.join(ROOT, "build_tmp"),
           "--specpath", os.path.join(ROOT, "build_tmp"),
           "--add-data", os.path.join(ROOT, "index.html") + SEP + ".",
           "--add-data", os.path.join(ROOT, "pieces") + SEP + "pieces",
           "--add-data", os.path.join(ROOT, "data") + SEP + "data",
           "--add-binary", sf + SEP + "stockfish",
           os.path.join(ROOT, "server.py")]
    print(" ".join(cmd))
    code = subprocess.call(cmd, cwd=ROOT)
    if code == 0:
        print("\nBuilt:", os.path.join(ROOT, "dist", "ChessX.exe"))
    return code


if __name__ == "__main__":
    sys.exit(main())
