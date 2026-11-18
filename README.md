# ChessX

**Made by AmiRAli** - [aphex.ir](https://aphex.ir)

A local chess analysis board with a modern, chess.com-style interface, powered by **Stockfish** and **python-chess**.
Play both sides, see the best moves as arrows, review your game move by move, and get move-quality labels.

> Runs entirely on your machine: a small Python server + a browser (app-window) UI. No accounts, no cloud.

## Features

- **Play both sides** - drag & drop or click-click, legal-move dots, promotion picker, castling, en passant.
- **Best moves** - top 1-5 Stockfish lines as colored arrows and in a panel (score, principal variation, depth); double-click a line to play it. Win/Draw/Loss bar and evaluation bar.
- **Move quality labels** - Brilliant, Great, Best, Excellent, Good, Book, Inaccuracy, Miss, Mistake, Blunder, plus per-side **Accuracy**.
- **Analyze game** - one click to evaluate every move of a loaded game; evaluation graph you can click to jump around.
- **Threat arrows** - red arrows for hanging pieces and mate-in-one threats.
- **History review** - click any move to jump there; undo / redo; Home / End.
- **Opening names** - ECO code + name (lichess opening database).
- **Import / export** - paste or open PGN / FEN, copy FEN, download PGN.
- **Themes** - light/dark UI, 6 board colors, up to 50 piece sets, sound effects, right-click arrows & circles.
- **Engine settings** - threads, hash size, battery saver. Stockfish is restarted automatically if it dies.
- **Responsive layout** - the UI adapts to narrow windows. The server listens on `127.0.0.1` only (not reachable from other devices).

## Quick start (Windows)

```bash
git clone <your-repo-url> ChessX
cd ChessX
pip install -r requirements.txt
python scripts/get_stockfish.py     # downloads the official Stockfish release (~100 MB)
python scripts/get_pieces.py        # optional: ~40 more piece sets for personal use (see THIRD_PARTY.md)
python server.py                    # opens the app window
```

Requirements: Python 3.9+ and Edge or Chrome (the UI opens in a chromeless app window; any other browser works at
`http://127.0.0.1:8765/`). On Linux/macOS install Stockfish with your package manager - ChessX finds it on `PATH`
(or set `STOCKFISH_PATH`).

The server exits ~90 s after the window is closed. Use `python server.py --keep` to keep it running.

## Keyboard shortcuts

| Key | Action |
|---|---|
| `Space` / `B` | Play the best move |
| `←` / `→` | Undo / redo |
| `Home` / `End` | Jump to start / end of the game |
| `F` | Flip the board |
| `N` | New game |
| `Esc` | Deselect / close dialogs |
| Right-click (+ drag) | Circle / arrow (`Shift` yellow, `Ctrl` blue, `Alt` purple) |

## Build a single-file `.exe`

```bash
pip install pyinstaller
python scripts/get_stockfish.py
python scripts/build_exe.py         # -> dist/ChessX.exe (Stockfish, UI, pieces and openings bundled)
```

If you plan to **publish** the exe, build it from a fresh clone *without* running `get_pieces.py`: many extra piece sets
are non-commercial / non-redistributable (see [THIRD_PARTY.md](THIRD_PARTY.md)). The first start of the one-file build
takes a few seconds (it unpacks itself); antivirus tools sometimes flag unsigned PyInstaller executables.

## How it works

`server.py` (stdlib HTTP server) owns the game (`python-chess`) and talks to Stockfish over UCI; `index.html` is the
whole UI (vanilla JS, no build step) and polls `/api/state`. Move labels use Stockfish's evaluation of the position
before and after each move, converted to win probability; "Brilliant" needs a real material sacrifice, "Great" an
only-move, "Miss" a failure to punish an opponent error. This approximates chess.com's review, it is not identical.

## 🇮🇷 خلاصه (فارسی)

صفحه شطرنج محلی با رابط شبیه chess.com و موتور Stockfish: دو طرف را خودت بازی می‌کنی، بهترین حرکت‌ها با فلش نشان
داده می‌شوند، کیفیت هر حرکت (Best / Mistake / Blunder ...) و دقت (Accuracy) محاسبه می‌شود و می‌توانی PGN و FEN وارد
یا خارج کنی. اجرا: `pip install -r requirements.txt` ← `python scripts/get_stockfish.py` ← `python server.py`.

## License

Copyright (C) 2026 AmiRAli ([aphex.ir](https://aphex.ir)). GPL-3.0 - see [LICENSE](LICENSE) and [THIRD_PARTY.md](THIRD_PARTY.md). Stockfish and python-chess are GPL-3.0 as well.
Not affiliated with chess.com or lichess.
