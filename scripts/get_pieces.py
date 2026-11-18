"""Download extra piece sets from lichess (https://github.com/lichess-org/lila) into ./pieces/.

Usage:  python scripts/get_pieces.py [--dest DIR]

The repository itself only ships piece sets whose licenses allow redistribution. This script fetches
the rest for your own local use. Many of them are CC BY-NC-SA 4.0 or "personal use only" - see
THIRD_PARTY.md and lila's COPYING.md before sharing anything that contains them.
"""
import argparse
import concurrent.futures as cf
import os
import shutil
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = "https://raw.githubusercontent.com/lichess-org/lila/master/public/"

SVG_SETS = ("alpha anarcandy caliente california cardinal cburnett celtic chess7 chessboart chessnut companion cooke "
            "dubrovny fantasy firi fresca gioco governor horsey icpieces kiwen-suwi kosal leipzig letter maestro merida "
            "minimal-warmth mpchess papercut pirouetti pixel reillycraig rhosgfx riohacha shahi-ivory-brown shapes "
            "spatial staunty tatiana totoy xkcd").split()
SETS_3D = "Staunton Wood Metal Glass RedVBlue ModernJade ModernWood Trimmed Basic CubesAndPi Experimental".split()
NAMES = {"P": "Pawn", "N": "Knight", "B": "Bishop", "R": "Rook", "Q": "Queen", "K": "King"}


def fetch(job):
    url, dest = job
    if os.path.isfile(dest) and os.path.getsize(dest) > 100:
        return None
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        urllib.request.urlretrieve(url, dest)
        return None
    except Exception as e:  # noqa: BLE001
        return url, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=os.path.join(ROOT, "pieces"))
    args = ap.parse_args()

    jobs = []
    for s in SVG_SETS:
        for c in "wb":
            for p in NAMES:
                jobs.append((f"{RAW}piece/{s}/{c}{p}.svg", os.path.join(args.dest, s, f"{c}{p}.svg")))
    for s in SETS_3D:
        for c, cn in (("w", "White"), ("b", "Black")):
            for p, pn in NAMES.items():
                jobs.append((f"{RAW}images/staunton/piece/{s}/{cn}-{pn}.webp",
                             os.path.join(args.dest, "3d-" + s.lower(), f"{c}{p}.webp")))
    print("Fetching %d files ..." % len(jobs))
    with cf.ThreadPoolExecutor(10) as ex:
        errors = [r for r in ex.map(fetch, jobs) if r]
    # Drop sets that did not download completely so the UI never shows broken pieces.
    dropped = []
    for d in sorted(os.listdir(args.dest)) if os.path.isdir(args.dest) else []:
        full = os.path.join(args.dest, d)
        if os.path.isdir(full):
            files = os.listdir(full)
            if len(files) != 12 or any(os.path.getsize(os.path.join(full, f)) < 100 for f in files):
                shutil.rmtree(full)
                dropped.append(d)
    ok = len([d for d in os.listdir(args.dest) if os.path.isdir(os.path.join(args.dest, d))])
    print("Done: %d piece sets available (%d files failed, dropped incomplete: %s)" % (ok, len(errors), dropped or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
