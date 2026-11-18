"""Download the official Stockfish release for Windows into ./stockfish/stockfish.exe.

Usage:  python scripts/get_stockfish.py [--dest DIR] [--force]

Source: https://github.com/official-stockfish/Stockfish/releases (GPL-3.0).
Uses the "x86-64-universal" build, which picks the best CPU instructions at run time.
"""
import argparse
import io
import json
import os
import shutil
import sys
import time
import urllib.request
import zipfile

API = "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=os.path.join(ROOT, "stockfish"), help="folder to put stockfish.exe in")
    ap.add_argument("--force", action="store_true", help="download even if stockfish.exe already exists")
    args = ap.parse_args()

    target = os.path.join(args.dest, "stockfish.exe")
    if os.path.isfile(target) and not args.force:
        print("Already there:", target)
        return 0
    if sys.platform != "win32":
        print("This script fetches the Windows build. On Linux/macOS install Stockfish with your package manager\n"
              "(e.g. `apt install stockfish` / `brew install stockfish`) - ChessX finds it on PATH.")
        return 1

    with urllib.request.urlopen(urllib.request.Request(API, headers={"User-Agent": "chessx-setup"})) as r:
        release = json.load(r)
    asset = next((a for a in release["assets"] if a["name"] == "stockfish-windows-x86-64-universal.zip"), None)
    if not asset:
        print("Could not find the Windows x86-64 asset in release", release.get("tag_name"))
        return 1
    print("Downloading %s (%s, %.0f MB) ..." % (asset["name"], release["tag_name"], asset["size"] / 1e6))
    data = None
    for attempt in range(1, 4):  # tolerate a flaky connection
        try:
            with urllib.request.urlopen(asset["browser_download_url"]) as r:
                data = r.read()
            break
        except OSError as e:
            print("  attempt %d failed: %s" % (attempt, e))
            time.sleep(2 * attempt)
    if data is None:
        print("Download failed. Get it manually from https://stockfish-chess.org/download/ and put it at", target)
        return 1
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        exe = next(n for n in z.namelist() if n.lower().endswith(".exe"))
        os.makedirs(args.dest, exist_ok=True)
        with z.open(exe) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
    print("Saved", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
