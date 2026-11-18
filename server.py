"""ChessX backend: Stockfish + python-chess, served to a browser UI.

Run:  python server.py        (opens the app window automatically)

Copyright (C) 2026 AmiRAli - https://aphex.ir
License: GNU GPL v3 (see LICENSE)
"""
import io
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import chess
import chess.engine
import chess.pgn

FROZEN = getattr(sys, "frozen", False)
BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))  # bundled resources
APP_DIR = os.path.dirname(sys.executable) if FROZEN else BASE  # where the user's files live
PORT = 8765
IDLE_EXIT_SECONDS = 90  # quit after the browser tab has been closed this long
JOB_DEPTH = 16          # depth used by "Analyze game"
MAT = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
ATK_VAL = {**MAT, chess.KING: 100}


def find_stockfish():
    cands = [os.environ.get("STOCKFISH_PATH", ""),
             os.path.join(APP_DIR, "stockfish", "stockfish.exe"),
             os.path.join(APP_DIR, "stockfish.exe"),
             os.path.join(BASE, "stockfish", "stockfish.exe"),
             os.path.join(BASE, "stockfish", "stockfish"),
             shutil.which("stockfish") or ""]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def score_json(pov):
    s = pov.white()
    if s.is_mate():
        return {"mate": s.mate()}
    return {"cp": s.score()}


def pv_text(board, pv, limit=10):
    b = board.copy()
    out = []
    for i, mv in enumerate(pv[:limit]):
        if mv not in b.legal_moves:
            break
        num = b.fullmove_number
        if b.turn == chess.WHITE:
            out.append("%d. %s" % (num, b.san(mv)))
        elif i == 0:
            out.append("%d... %s" % (num, b.san(mv)))
        else:
            out.append(b.san(mv))
        b.push(mv)
    return " ".join(out)


def material_diff(board, color):
    d = 0
    for p in board.piece_map().values():
        d += MAT[p.piece_type] * (1 if p.color == color else -1)
    return d


def threats_against_mover(b):
    """Arrows for what the opponent threatens right now (hanging pieces, mate in one)."""
    out = []
    me, opp = b.turn, not b.turn
    for sq, p in b.piece_map().items():
        if p.color != me or p.piece_type == chess.KING:
            continue
        atk = b.attackers(opp, sq)
        if not atk:
            continue
        va, asq = min((ATK_VAL[b.piece_type_at(a)], a) for a in atk)
        if not b.attackers(me, sq) or va < MAT[p.piece_type]:
            out.append({"from": chess.square_name(asq), "to": chess.square_name(sq), "kind": "capture"})
    if not b.is_check():
        nb = b.copy()
        nb.push(chess.Move.null())
        found = 0
        for mv in list(nb.legal_moves):
            nb.push(mv)
            if nb.is_checkmate():
                out.append({"from": chess.square_name(mv.from_square), "to": chess.square_name(mv.to_square),
                            "kind": "mate"})
                found += 1
            nb.pop()
            if found >= 2:
                break
    return out


OPENINGS = {}


def load_openings():
    for letter in "abcde":
        path = os.path.join(BASE, "data", letter + ".tsv")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            next(f, None)
            for row in f:
                parts = row.rstrip("\r\n").split("\t")
                if len(parts) < 3:
                    continue
                eco, name, pgn = parts[:3]
                b = chess.Board()
                try:
                    for tok in pgn.split():
                        if tok[0].isdigit() and "." in tok:
                            continue
                        b.push_san(tok)
                except ValueError:
                    continue
                OPENINGS[b.epd()] = (eco, name)


class Game:
    def __init__(self):
        self.lock = threading.RLock()
        self.cv = threading.Condition(self.lock)
        self.board = chess.Board()
        self.redo = []
        self.settings = {"lines": 3, "seconds": 0, "hints": True, "threats": True}
        self.max_threads = os.cpu_count() or 2
        self.cfg = {"threads": max(1, self.max_threads // 2), "hash": 512, "saver": False}
        self.cfg_ver = 0
        self.gen = 0
        self.analysis = {"fen": None, "depth": 0, "lines": {}}
        self.engine_error = None
        self.engine_name = "Stockfish"
        self.evals = {}    # epd -> best line {"depth","score","uci","san","pv"}
        self.seconds = {}  # epd -> (depth, score) of the 2nd best line
        self.sac_cache = {}
        self.job = None
        threading.Thread(target=load_openings, daemon=True).start()
        threading.Thread(target=self.worker, daemon=True).start()

    # -- engine worker ----------------------------------------------------
    def _info_line(self, board, info):
        if "pv" not in info or "score" not in info or "multipv" not in info:
            return None
        if info.get("lowerbound") or info.get("upperbound"):
            return None
        pv = info["pv"]
        if not pv:
            return None
        line = {"uci": pv[0].uci(), "san": board.san(pv[0]), "score": score_json(info["score"]),
                "depth": info.get("depth", 0), "pv": pv_text(board, pv),
                "pvu": [m.uci() for m in pv[:6]]}
        wdl = info.get("wdl")
        if wdl is not None:
            w = wdl.white()
            line["wdl"] = [w.wins, w.draws, w.losses]
        return info["multipv"], line

    def _record(self, board, rank, line):
        key = board.epd()
        if rank == 1:
            old = self.evals.get(key)
            if not old or line["depth"] >= old["depth"]:
                self.evals[key] = {"depth": line["depth"], "score": line["score"], "uci": line["uci"],
                                   "san": line["san"], "pv": line["pvu"]}
        elif rank == 2:
            old = self.seconds.get(key)
            if not old or line["depth"] >= old[0]:
                self.seconds[key] = (line["depth"], line["score"])

    def _run_job(self, engine, job):
        for i, b in enumerate(job["boards"]):
            if job["cancel"]:
                return
            job["idx"] = i
            if b.is_game_over():
                continue
            key = b.epd()
            e, s2 = self.evals.get(key), self.seconds.get(key)
            if e and s2 and e["depth"] >= job["depth"] and s2[0] >= job["depth"] - 2:
                continue
            with engine.analysis(b, chess.engine.Limit(depth=job["depth"]), multipv=2) as an:
                for info in an:
                    if job["cancel"]:
                        break
                    r = self._info_line(b, info)
                    if r:
                        with self.lock:
                            self._record(b, r[0], r[1])
        job["idx"] = len(job["boards"])

    def _apply_cfg(self, engine, cfg):
        opts = {"Threads": cfg["threads"], "Hash": cfg["hash"]}
        if "UCI_ShowWDL" in engine.options:
            opts["UCI_ShowWDL"] = True
        engine.configure(opts)

    def worker(self):
        path = find_stockfish()
        if not path:
            self.engine_error = "Stockfish not found (run: python scripts/get_stockfish.py)"
            return
        kw = {}
        if sys.platform == "win32":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        engine = None
        done = -1
        cfg_seen = -1
        while True:
            if engine is None:  # (re)start Stockfish, e.g. after it was killed
                try:
                    engine = chess.engine.SimpleEngine.popen_uci(path, **kw)
                    self.engine_name = engine.id.get("name", "Stockfish")
                    self.engine_error = None
                    done, cfg_seen = -1, -1
                except Exception as e:  # noqa: BLE001
                    engine = None
                    self.engine_error = "Could not start Stockfish: %s" % e
                    time.sleep(2)
                    continue
            with self.cv:
                while self.gen == done and not self.job and cfg_seen == self.cfg_ver:
                    self.cv.wait()
                gen = self.gen
                board = self.board.copy()
                st = dict(self.settings)
                cfgv, cfg = self.cfg_ver, dict(self.cfg)
                job = self.job
            try:
                if cfgv != cfg_seen:
                    self._apply_cfg(engine, cfg)
                    cfg_seen = cfgv
                if job:
                    self._run_job(engine, job)
                    with self.lock:
                        self.job = None
                    done = -1
                    continue
                done = gen
                if not st["hints"] or board.is_game_over():
                    continue
                secs = st["seconds"] or (5 if cfg["saver"] else 0)
                limit = chess.engine.Limit(time=secs) if secs else chess.engine.Limit()
                with engine.analysis(board, limit, multipv=max(st["lines"], 2)) as an:
                    for info in an:
                        if self.gen != gen or self.job or self.cfg_ver != cfg_seen:
                            break
                        r = self._info_line(board, info)
                        if not r:
                            continue
                        rank, line = r
                        with self.lock:
                            if self.gen != gen:
                                break
                            if self.analysis["fen"] != board.fen():
                                self.analysis = {"fen": board.fen(), "depth": 0, "lines": {}}
                            self.analysis["lines"][rank] = line
                            self._record(board, rank, line)
                            self.analysis["depth"] = max(self.analysis["depth"], line["depth"])
            except Exception as e:  # noqa: BLE001
                # Engine died or hung up: drop it and start a fresh one on the next loop.
                self.engine_error = "Engine restarting (%s)" % e
                try:
                    engine.close()
                except Exception:  # noqa: BLE001
                    pass
                engine = None
                with self.lock:
                    self.job = None
                time.sleep(0.5)

    def _bump(self):
        self.gen += 1
        self.cv.notify_all()

    def _cancel_job(self):
        if self.job:
            self.job["cancel"] = True

    # -- actions ----------------------------------------------------------
    def move(self, uci):
        with self.lock:
            mv = chess.Move.from_uci(uci)
            if mv not in self.board.legal_moves:
                return False
            self.board.push(mv)
            self.redo.clear()
            self._bump()
            return True

    def undo(self):
        with self.lock:
            if self.board.move_stack:
                self.redo.append(self.board.pop())
                self._bump()

    def redo_move(self):
        with self.lock:
            if self.redo:
                self.board.push(self.redo.pop())
                self._bump()

    def new(self):
        with self.lock:
            self._cancel_job()
            self.board = chess.Board()
            self.redo.clear()
            self._bump()

    def goto(self, ply):
        """Jump to a ply of the full game line (played moves + redo stack)."""
        with self.lock:
            line = list(self.board.move_stack) + list(reversed(self.redo))
            ply = max(0, min(int(ply), len(line)))
            self.board = chess.Board(self.board.root().fen())
            for mv in line[:ply]:
                self.board.push(mv)
            self.redo = list(reversed(line[ply:]))
            self._bump()

    def pgn(self):
        with self.lock:
            line = list(self.board.move_stack) + list(reversed(self.redo))
            root = self.board.root()
            game = chess.pgn.Game()
            game.headers["Event"] = "ChessX analysis"
            game.headers["Site"] = "Local"
            game.headers["Date"] = time.strftime("%Y.%m.%d")
            game.headers["White"] = "White"
            game.headers["Black"] = "Black"
            if root.fen() != chess.STARTING_FEN:
                game.setup(root)
            node = game
            end = chess.Board(root.fen())
            for mv in line:
                node = node.add_variation(mv)
                end.push(mv)
            game.headers["Result"] = end.result() if end.is_game_over() else "*"
            exp = chess.pgn.StringExporter(headers=True, variations=False, comments=False)
            return game.accept(exp)

    def load(self, text):
        text = (text or "").strip()
        if not text:
            return False, "Nothing to load"
        with self.lock:
            looks_fen = "[" not in text and "/" in text and len(text.split()) >= 4 and "." not in text.split()[0]
            try:
                if looks_fen:
                    b = chess.Board(text)
                    if not b.is_valid():
                        return False, "That FEN is not a legal position"
                    self.board, self.redo = b, []
                else:
                    game = chess.pgn.read_game(io.StringIO(text))
                    if game is None:
                        return False, "Could not read a game"
                    b = game.board()
                    moves = list(game.mainline_moves())
                    if not moves and b.fen() == chess.STARTING_FEN:
                        return False, "No moves found in that text"
                    for mv in moves:
                        b.push(mv)
                    self.board, self.redo = b, []
            except ValueError as e:
                return False, "Invalid input: %s" % e
            self._cancel_job()
            self._bump()
            return True, ""

    def set_settings(self, d):
        with self.lock:
            if "lines" in d:
                self.settings["lines"] = max(1, min(5, int(d["lines"])))
            if "seconds" in d:
                self.settings["seconds"] = max(0, int(d["seconds"]))
            if "hints" in d:
                self.settings["hints"] = bool(d["hints"])
            if "threats" in d:
                self.settings["threats"] = bool(d["threats"])
            self._bump()

    def set_engine(self, d):
        with self.lock:
            if d.get("saver") is not None:
                self.cfg["saver"] = bool(d["saver"])
            if "threads" in d:
                self.cfg["threads"] = max(1, min(self.max_threads, int(d["threads"])))
            if "hash" in d:
                self.cfg["hash"] = max(16, min(4096, int(d["hash"])))
            if self.cfg["saver"]:
                self.cfg["threads"], self.cfg["hash"] = 1, 64
            self.cfg_ver += 1
            self._bump()

    def analyze_game(self, cancel=False):
        with self.lock:
            if cancel:
                self._cancel_job()
                self.cv.notify_all()
                return
            if self.job and not self.job["cancel"]:
                return
            line = list(self.board.move_stack) + list(reversed(self.redo))
            if not line:
                return
            b = chess.Board(self.board.root().fen())
            boards = [b.copy()]
            for mv in line:
                b.push(mv)
                boards.append(b.copy())
            self.job = {"boards": boards, "idx": 0, "total": len(boards), "depth": JOB_DEPTH, "cancel": False}
            self.cv.notify_all()

    # -- state ------------------------------------------------------------
    def _ev_of(self, pos):
        if pos.is_checkmate():
            return {"depth": 99, "score": {"cp": -10000 if pos.turn == chess.WHITE else 10000},
                    "uci": None, "san": None, "pv": [], "second": None}
        if pos.is_game_over():
            return {"depth": 99, "score": {"cp": 0}, "uci": None, "san": None, "pv": [], "second": None}
        key = pos.epd()
        e = self.evals.get(key)
        if not e:
            return None
        e = dict(e)
        s2 = self.seconds.get(key)
        e["second"] = s2[1] if s2 else None
        return e

    def _is_sacrifice(self, before, mv, after_eval, after_pos):
        """Did the mover give up >= 2 pawns of material that the engine line does not win back?"""
        if not after_eval or not after_eval.get("pv") or len(after_eval["pv"]) < 2:
            return False
        key = (after_pos.epd(), after_eval["depth"] // 4, mv.uci())
        if key in self.sac_cache:
            return self.sac_cache[key]
        mover = before.turn
        d0 = material_diff(before, mover)
        sim = after_pos.copy()
        try:
            for u in after_eval["pv"][:2]:
                sim.push(chess.Move.from_uci(u))
        except ValueError:
            return False
        res = material_diff(sim, mover) <= d0 - 2
        self.sac_cache[key] = res
        return res

    def state(self):
        with self.lock:
            b = self.board
            full = list(b.move_stack) + list(reversed(self.redo))
            ply = len(b.move_stack)
            root_fen = b.root().fen()
            tmp = chess.Board(root_fen)
            standard = root_fen == chess.STARTING_FEN
            moves, ucis, evals, book, sacs = [], [], [], [], []
            opening = None
            evals.append(self._ev_of(tmp))
            for i, mv in enumerate(full):
                before = tmp.copy(stack=False)
                moves.append(tmp.san(mv))
                ucis.append(mv.uci())
                tmp.push(mv)
                hit = OPENINGS.get(tmp.epd()) if standard else None
                book.append(bool(hit))
                if hit and i < ply:
                    opening = {"eco": hit[0], "name": hit[1]}
                ev = self._ev_of(tmp)
                evals.append(ev)
                sacs.append(self._is_sacrifice(before, mv, ev, tmp))
            over = None
            if b.is_checkmate():
                over = {"result": "0-1" if b.turn == chess.WHITE else "1-0",
                        "text": "Checkmate - %s wins" % ("Black" if b.turn == chess.WHITE else "White")}
            elif b.is_stalemate():
                over = {"result": "1/2-1/2", "text": "Stalemate - draw"}
            elif b.is_insufficient_material():
                over = {"result": "1/2-1/2", "text": "Draw - insufficient material"}
            elif b.is_fifty_moves():
                over = {"result": "1/2-1/2", "text": "Draw - 50-move rule"}
            elif b.is_repetition(3):
                over = {"result": "1/2-1/2", "text": "Draw - threefold repetition"}
            lines = []
            depth = 0
            if self.settings["hints"] and not over and self.analysis["fen"] == b.fen():
                lines = [self.analysis["lines"][k] for k in sorted(self.analysis["lines"])
                         if k <= self.settings["lines"]]
                depth = self.analysis["depth"]
            threats = []
            if self.settings["threats"] and not over:
                threats = threats_against_mover(b)
            job = None
            if self.job and not self.job["cancel"]:
                job = {"idx": self.job["idx"], "total": self.job["total"]}
            return {
                "fen": b.fen(),
                "turn": "w" if b.turn else "b",
                "ply": ply,
                "moves": moves,
                "ucis": ucis,
                "evals": evals,
                "book": book,
                "sacs": sacs,
                "opening": opening,
                "last": b.peek().uci() if b.move_stack else None,
                "check": chess.square_name(b.king(b.turn)) if b.is_check() else None,
                "legal": [m.uci() for m in b.legal_moves],
                "over": over,
                "can_redo": bool(self.redo),
                "settings": self.settings,
                "lines": lines,
                "depth": depth,
                "threats": threats,
                "job": job,
                "engine_cfg": dict(self.cfg, max_threads=self.max_threads),
                "engine": self.engine_name,
                "error": self.engine_error,
            }


GAME = Game()
last_hit = [0.0]


def piece_sets():
    root = os.path.join(BASE, "pieces")
    out = []
    for d in sorted(os.listdir(root)):
        full = os.path.join(root, d)
        if os.path.isdir(full):
            files = os.listdir(full)
            if files:
                out.append({"name": d, "ext": os.path.splitext(files[0])[1].lstrip(".")})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", cache="no-store"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        last_hit[0] = time.time()
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(os.path.join(BASE, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html")
        elif path == "/api/state":
            self._send(200, json.dumps(GAME.state()))
        elif path == "/api/pgn":
            self._send(200, GAME.pgn(), "text/plain")
        elif path == "/api/pieces":
            self._send(200, json.dumps(piece_sets()))
        elif path.startswith("/pieces/"):
            rel = path[len("/pieces/"):]
            full = os.path.normpath(os.path.join(BASE, "pieces", rel))
            if full.startswith(os.path.join(BASE, "pieces") + os.sep) and os.path.isfile(full):
                ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
                with open(full, "rb") as f:
                    self._send(200, f.read(), ctype, "public, max-age=86400")
            else:
                self._send(404, "{}")
        else:
            self._send(404, "{}")

    def do_POST(self):
        last_hit[0] = time.time()
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            body = {}
        path = urlparse(self.path).path
        ok = True
        try:
            if path == "/api/move":
                ok = GAME.move(body.get("uci", ""))
            elif path == "/api/undo":
                GAME.undo()
            elif path == "/api/redo":
                GAME.redo_move()
            elif path == "/api/new":
                GAME.new()
            elif path == "/api/settings":
                GAME.set_settings(body)
            elif path == "/api/engine":
                GAME.set_engine(body)
            elif path == "/api/analyze":
                GAME.analyze_game(cancel=bool(body.get("cancel")))
            elif path == "/api/goto":
                GAME.goto(body.get("ply", 0))
            elif path == "/api/load":
                ok, err = GAME.load(body.get("text", ""))
                self._send(200, json.dumps({"ok": ok, "error": err}))
                return
            else:
                self._send(404, "{}")
                return
        except Exception:  # noqa: BLE001
            ok = False
        self._send(200, json.dumps({"ok": ok}))


def open_window(url):
    """Prefer a chromeless app window (Edge/Chrome); fall back to the default browser."""
    if sys.platform == "win32":
        for exe in ("msedge", "chrome"):
            p = shutil.which(exe)
            if not p:
                for root in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
                    sub = r"Microsoft\Edge\Application\msedge.exe" if exe == "msedge" \
                        else r"Google\Chrome\Application\chrome.exe"
                    cand = os.path.join(root, sub)
                    if root and os.path.isfile(cand):
                        p = cand
                        break
            if p:
                try:
                    subprocess.Popen([p, "--app=" + url, "--window-size=1280,860"])
                    return
                except OSError:
                    pass
    webbrowser.open(url)


def main():
    ThreadingHTTPServer.request_queue_size = 256
    url = "http://127.0.0.1:%d/" % PORT
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:  # already running: just open another window on it
        if "--no-window" not in sys.argv:
            open_window(url)
        return
    srv.daemon_threads = True
    print("ChessX running at", url)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if "--no-window" not in sys.argv:
        open_window(url)
    last_hit[0] = time.time()
    try:
        while True:
            time.sleep(2)
            if "--keep" not in sys.argv and time.time() - last_hit[0] > IDLE_EXIT_SECONDS:
                break
    except KeyboardInterrupt:
        pass
    os._exit(0)


if __name__ == "__main__":
    main()
