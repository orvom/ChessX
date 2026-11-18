# Third-party software and assets

ChessX itself is licensed under the **GNU GPL v3** (see `LICENSE`). It builds on the following.

## Software

| Component | License | How it is used |
|---|---|---|
| [Stockfish](https://github.com/official-stockfish/Stockfish) | GPL-3.0 | The chess engine. **Not** included in this repository; `scripts/get_stockfish.py` downloads the official release. |
| [python-chess](https://github.com/niklasf/python-chess) | GPL-3.0 | Move generation, PGN/FEN, UCI communication. Installed with `pip`. |

## Data

| Asset | License | Notes |
|---|---|---|
| [lichess chess-openings](https://github.com/lichess-org/chess-openings) (`data/*.tsv`) | CC0 1.0 | Opening names / ECO codes. |

## Piece sets (from [lichess/lila](https://github.com/lichess-org/lila), see its `COPYING.md`)

**Included in this repository** (licenses allow redistribution):

| Set | License |
|---|---|
| cburnett, merida | GPLv2+ (Colin M.L. Burnett / Armando Hernandez Marroquin) |
| chessnut | Apache 2.0 (Alexis Luengas) |
| mpchess | GPLv3+ (Maxime Chupin) |
| letter, pirouetti, pixel | AGPLv3+ |
| fantasy, spatial, celtic | MIT (Maurizio Monge) |
| rhosgfx | CC0 1.0 |
| kiwen-suwi, totoy, papercut, firi | CC BY 4.0 |
| shapes | CC BY-SA 4.0 (flugsio) |

**Not included - fetched on demand by `python scripts/get_pieces.py`** for personal use. Most of these are
CC BY-NC-SA 4.0 (non-commercial, share-alike: cardinal, maestro, fresca, gioco, tatiana, staunty, dubrovny,
icpieces, california, caliente, anarcandy, cooke, minimal-warmth, chessboart, horsey, ...), some are
"freeware / personal use only" (alpha, chess7, companion, leipzig), one has a no-derivatives license
(shahi-ivory-brown), and a few have no stated license (reillycraig, riohacha, the `3d-*` Staunton-style sets).
**Do not redistribute builds or repositories containing them.** Check lila's `COPYING.md` for details.

Per-set authorship is listed in [lila's COPYING.md](https://github.com/lichess-org/lila/blob/master/COPYING.md).
