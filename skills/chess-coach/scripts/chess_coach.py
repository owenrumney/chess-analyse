#!/usr/bin/env python3
"""Pattern-based Chess.com coach for recent games.

Fetches public Chess.com games, extracts opening/performance patterns, and prints a
short coaching report. This intentionally avoids claiming engine accuracy: it is a
fast recurring-habit and opening-memory analyser.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import json
import os
import re
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

API_ROOT = "https://api.chess.com/pub"
CACHE_DIR = Path(os.environ.get("CHESS_COACH_CACHE", "~/.pi/agent/cache/pi-chess-coach")).expanduser()
CARDS_DIR = Path(os.environ.get("CHESS_COACH_HOME", "~/.pi/agent/chess-coach")).expanduser()
CONFIG_DIR = Path(os.environ.get("CHESS_COACH_CONFIG_DIR", "~/.pi/agent/chess-coach")).expanduser()
CONFIG_FILE = Path(os.environ.get("CHESS_COACH_CONFIG", str(CONFIG_DIR / "config.env"))).expanduser()
USER_AGENT = "pi-chess-coach/0.1 (+https://api.chess.com/pub)"
RESULT_TOKENS = {"1-0", "0-1", "1/2-1/2", "*"}

HEADER_RE = re.compile(r'^\[(\w+) "((?:[^"\\]|\\.)*)"\]$', re.MULTILINE)
COMMENT_RE = re.compile(r"\{[^}]*\}")
NAG_RE = re.compile(r"\$\d+")
MOVE_PREFIX_RE = re.compile(r"^(\d+)\.(\.\.\.)?(.+)?$")
MOVE_NUMBER_ONLY_RE = re.compile(r"^\d+\.(?:\.\.)?$")


@dataclass
class Move:
    fullmove: int
    color: str
    san: str


@dataclass
class GameSummary:
    url: str
    end_time: int
    date: str
    time_class: str
    time_control: str
    color: str
    opponent: str
    opponent_elo: int | None
    player_elo: int | None
    result: str
    termination: str
    eco: str
    opening: str
    opening_key: str
    line: str
    opening_moves: list[Move]
    moves_count: int
    player_moves_opening: list[str]
    motifs: list[str] = field(default_factory=list)


@dataclass
class Report:
    username: str
    days: int | None
    since: str | None
    until: str
    games: list[GameSummary]
    opening_rows: list[dict[str, Any]]
    motif_rows: list[dict[str, Any]]
    recommendations: list[str]
    generated_at: str


def load_config_env(path: Path = CONFIG_FILE) -> None:
    """Load simple KEY=VALUE config without overriding existing environment."""
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def http_json(url: str, timeout: int = 30) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Chess.com API returned HTTP {exc.code} for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Chess.com API at {url}: {exc}") from exc


def cache_path(username: str, year: int, month: int) -> Path:
    safe_user = re.sub(r"[^a-zA-Z0-9_.-]+", "_", username.lower())
    return CACHE_DIR / f"{safe_user}-{year:04d}-{month:02d}.json"


def fetch_month(username: str, year: int, month: int, ttl_seconds: int, no_cache: bool = False) -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(username, year, month)
    now = time.time()
    if not no_cache and path.exists() and now - path.stat().st_mtime < ttl_seconds:
        return json.loads(path.read_text())

    url = f"{API_ROOT}/player/{urllib.parse.quote(username)}/games/{year:04d}/{month:02d}"
    data = http_json(url)
    path.write_text(json.dumps(data, indent=2))
    return data


def month_range(start: dt.datetime, end: dt.datetime) -> Iterable[tuple[int, int]]:
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


def parse_headers(pgn: str) -> dict[str, str]:
    return {key: value.replace('\\"', '"') for key, value in HEADER_RE.findall(pgn)}


def remove_variations(text: str) -> str:
    out: list[str] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
            continue
        if ch == ")" and depth:
            depth -= 1
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out)


def movetext_from_pgn(pgn: str) -> str:
    parts = re.split(r"\n\s*\n", pgn, maxsplit=1)
    return parts[1] if len(parts) == 2 else ""


def clean_san(token: str) -> str:
    # Drop common annotation suffixes while keeping mate/check symbols useful.
    return token.strip().rstrip("!?⟳")


def parse_moves(pgn: str) -> list[Move]:
    text = movetext_from_pgn(pgn)
    text = COMMENT_RE.sub(" ", text)
    text = NAG_RE.sub(" ", text)
    text = remove_variations(text)
    text = text.replace("\n", " ")

    moves: list[Move] = []
    ply = 0
    for raw in text.split():
        token = raw.strip()
        if not token or token in RESULT_TOKENS:
            continue
        if MOVE_NUMBER_ONLY_RE.match(token):
            number = int(token.split(".", 1)[0])
            ply = (number - 1) * 2
            if "..." in token:
                ply += 1
            continue

        prefix = MOVE_PREFIX_RE.match(token)
        if prefix:
            number = int(prefix.group(1))
            rest = prefix.group(3)
            ply = (number - 1) * 2 + (1 if prefix.group(2) else 0)
            if not rest:
                continue
            token = rest

        if token in RESULT_TOKENS or token.startswith("["):
            continue

        san = clean_san(token)
        if not san:
            continue
        color = "white" if ply % 2 == 0 else "black"
        moves.append(Move(fullmove=(ply // 2) + 1, color=color, san=san))
        ply += 1
    return moves


def format_line(moves: list[Move], max_plies: int = 12) -> str:
    selected = moves[:max_plies]
    chunks: list[str] = []
    pending_white: str | None = None
    current_move: int | None = None
    for mv in selected:
        if mv.color == "white":
            if pending_white is not None:
                chunks.append(f"{current_move}. {pending_white}")
            current_move = mv.fullmove
            pending_white = mv.san
        else:
            if pending_white is not None and current_move == mv.fullmove:
                chunks.append(f"{current_move}. {pending_white} {mv.san}")
                pending_white = None
            else:
                chunks.append(f"{mv.fullmove}... {mv.san}")
    if pending_white is not None:
        chunks.append(f"{current_move}. {pending_white}")
    return " ".join(chunks)


def opening_from_headers(headers: dict[str, str]) -> tuple[str, str, str]:
    eco = headers.get("ECO", "?")
    eco_url = headers.get("ECOUrl", "")
    if "/openings/" in eco_url:
        slug = urllib.parse.unquote(eco_url.split("/openings/", 1)[1].strip("/"))
        parts = [p for p in slug.split("-") if p]
        name_parts: list[str] = []
        for part in parts:
            if re.match(r"^\d+\.", part):
                break
            name_parts.append(part)
        name = " ".join(name_parts) if name_parts else slug.replace("-", " ")
    else:
        name = headers.get("Opening", "Unknown opening")
    name = re.sub(r"\s+", " ", name).strip() or "Unknown opening"
    key = f"{eco} {name}"
    return eco, name, key


def int_or_none(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def game_result(game: dict[str, Any], username: str) -> tuple[str, str, str, int | None, int | None]:
    white = game.get("white", {})
    black = game.get("black", {})
    username_lower = username.lower()
    if white.get("username", "").lower() == username_lower:
        color = "white"
        mine = white
        theirs = black
    else:
        color = "black"
        mine = black
        theirs = white

    raw = mine.get("result", "")
    if raw == "win":
        result = "win"
    elif raw in {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}:
        result = "draw"
    else:
        result = "loss"
    return result, color, theirs.get("username", "?"), int_or_none(str(theirs.get("rating", ""))), int_or_none(str(mine.get("rating", "")))


def is_castle(san: str) -> bool:
    return san.startswith("O-O") or san.startswith("0-0")


def is_player_pawn_file_move(san: str, files: str) -> bool:
    # SAN pawn moves start with file for quiet moves (e4) and captures (exd5).
    s = san.lstrip("x")
    return len(s) >= 2 and s[0] in files and (s[1].isdigit() or s[1] == "x")


def classify_motifs(summary: GameSummary, all_moves: list[Move]) -> list[str]:
    motifs: list[str] = []
    player_moves = [m for m in all_moves if m.color == summary.color]
    opening_moves = [m for m in player_moves if m.fullmove <= 10]
    castle_move = next((m.fullmove for m in player_moves if is_castle(m.san)), None)

    early_queen = [m for m in opening_moves if m.san.startswith("Q") and m.fullmove <= 8]
    early_king = [m for m in opening_moves if m.san.startswith("K") and not is_castle(m.san)]
    flank_before_castle = [
        m
        for m in opening_moves
        if is_player_pawn_file_move(m.san, "abgh") and (castle_move is None or m.fullmove < castle_move)
    ]
    f_pawn_before_castle = [
        m
        for m in opening_moves
        if is_player_pawn_file_move(m.san, "f") and (castle_move is None or m.fullmove < castle_move)
    ]
    minor_development = [m for m in player_moves if m.fullmove <= 8 and m.san[:1] in {"N", "B"}]
    center_pawns = [m for m in player_moves if m.fullmove <= 6 and is_player_pawn_file_move(m.san, "de")]

    if castle_move is None or castle_move > 10:
        motifs.append("delayed castling")
    if early_queen:
        motifs.append("early queen move")
    if early_king:
        motifs.append("king moved before castling")
    if len(flank_before_castle) >= 2:
        motifs.append("flank pawns before castling")
    if f_pawn_before_castle:
        motifs.append("f-pawn before castling")
    if len(minor_development) < 2 and summary.moves_count >= 8:
        motifs.append("slow minor-piece development")
    if len(center_pawns) == 0 and summary.color == "white":
        motifs.append("no early central pawn claim")
    if summary.result == "loss" and summary.moves_count <= 20:
        motifs.append("short loss")
    return motifs


def summarise_game(game: dict[str, Any], username: str) -> GameSummary | None:
    pgn = game.get("pgn") or ""
    if not pgn:
        return None
    headers = parse_headers(pgn)
    moves = parse_moves(pgn)
    result, color, opponent, opponent_elo, player_elo = game_result(game, username)
    eco, opening, opening_key = opening_from_headers(headers)
    end_time = int(game.get("end_time") or 0)
    when = dt.datetime.fromtimestamp(end_time, tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M") if end_time else "?"
    player_moves_opening = [m.san for m in moves if m.color == color and m.fullmove <= 10]
    summary = GameSummary(
        url=game.get("url", ""),
        end_time=end_time,
        date=when,
        time_class=game.get("time_class", "?"),
        time_control=game.get("time_control", "?"),
        color=color,
        opponent=opponent,
        opponent_elo=opponent_elo,
        player_elo=player_elo,
        result=result,
        termination=headers.get("Termination", ""),
        eco=eco,
        opening=opening,
        opening_key=opening_key,
        line=format_line(moves, max_plies=12),
        opening_moves=moves[:16],
        moves_count=max((m.fullmove for m in moves), default=0),
        player_moves_opening=player_moves_opening,
    )
    summary.motifs = classify_motifs(summary, moves)
    return summary


def recent_games(username: str, start: dt.datetime, end: dt.datetime, ttl_seconds: int, no_cache: bool) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    for year, month in month_range(start, end):
        data = fetch_month(username, year, month, ttl_seconds=ttl_seconds, no_cache=no_cache)
        games.extend(data.get("games", []))
    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    filtered = [g for g in games if start_ts <= int(g.get("end_time") or 0) <= end_ts and g.get("rules") == "chess"]
    return sorted(filtered, key=lambda g: int(g.get("end_time") or 0))


def opening_stats(games: list[GameSummary]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[GameSummary]] = defaultdict(list)
    for game in games:
        grouped[(game.color, game.opening_key)].append(game)

    rows: list[dict[str, Any]] = []
    for (color, opening), items in grouped.items():
        counts = Counter(g.result for g in items)
        score = counts["win"] + 0.5 * counts["draw"]
        score_pct = round(100 * score / len(items)) if items else 0
        motifs = Counter(m for g in items for m in g.motifs)
        sample = items[-1]
        rows.append(
            {
                "color": color,
                "opening": opening,
                "games": len(items),
                "wins": counts["win"],
                "draws": counts["draw"],
                "losses": counts["loss"],
                "score_pct": score_pct,
                "top_motifs": [m for m, _ in motifs.most_common(3)],
                "sample_line": sample.line,
                "sample_url": sample.url,
            }
        )
    return sorted(rows, key=lambda r: (r["losses"], r["games"]), reverse=True)


def motif_stats(games: list[GameSummary]) -> list[dict[str, Any]]:
    grouped: dict[str, list[GameSummary]] = defaultdict(list)
    for game in games:
        for motif in game.motifs:
            grouped[motif].append(game)
    rows = []
    for motif, items in grouped.items():
        counts = Counter(g.result for g in items)
        rows.append(
            {
                "motif": motif,
                "games": len(items),
                "wins": counts["win"],
                "draws": counts["draw"],
                "losses": counts["loss"],
                "examples": [g.url for g in items[-3:]],
            }
        )
    return sorted(rows, key=lambda r: (r["losses"], r["games"]), reverse=True)


def recommendations(openings: list[dict[str, Any]], motifs: list[dict[str, Any]]) -> list[str]:
    recs: list[str] = []
    motif_names = [m["motif"] for m in motifs[:5]]
    if "delayed castling" in motif_names:
        recs.append("Use a move-8 king-safety checkpoint: if you are not castled, know exactly why.")
    if "flank pawns before castling" in motif_names:
        recs.append("Before pushing a/b/g/h pawns in the opening, develop two minor pieces and castle first.")
    if "f-pawn before castling" in motif_names:
        recs.append("Treat early f-pawn moves as a special weapon, not a default plan; they expose your king.")
    if "early queen move" in motif_names:
        recs.append("Try a no-queen-before-move-8 rule unless it wins forced material or stops mate.")
    if "slow minor-piece development" in motif_names:
        recs.append("Opening checklist: two minor pieces out before starting pawn adventures.")
    if openings:
        target = openings[0]
        recs.append(f"Review one line as {target['color']} in {target['opening']}: {target['sample_line']}")
    if not recs:
        recs.append("Pick one frequent opening and write down the plan after move 5, not just the moves.")
    return recs[:4]


def build_report(username: str, days: int | None, since: str | None, start: dt.datetime, end: dt.datetime, ttl: int, no_cache: bool) -> Report:
    raw_games = recent_games(username, start, end, ttl_seconds=ttl, no_cache=no_cache)
    summaries = [s for g in raw_games if (s := summarise_game(g, username))]
    openings = opening_stats(summaries)
    motifs = motif_stats(summaries)
    recs = recommendations(openings, motifs)
    return Report(
        username=username,
        days=days,
        since=since,
        until=end.strftime("%Y-%m-%d"),
        games=summaries,
        opening_rows=openings,
        motif_rows=motifs,
        recommendations=recs,
        generated_at=dt.datetime.now(tz=dt.timezone.utc).isoformat(timespec="seconds"),
    )


def result_summary(games: list[GameSummary]) -> str:
    counts = Counter(g.result for g in games)
    total = len(games)
    if total == 0:
        return "0 games"
    score = counts["win"] + 0.5 * counts["draw"]
    pct = round(100 * score / total)
    return f"{total} games: {counts['win']}W-{counts['draw']}D-{counts['loss']}L ({pct}% score)"


PIECE_NAMES = {
    "K": "king",
    "Q": "queen",
    "R": "rook",
    "B": "bishop",
    "N": "knight",
}


def explain_san(san: str, color: str) -> str:
    clean = san.strip().rstrip("!?")
    lower_color = "White" if color == "white" else "Black"
    if clean.startswith(("O-O-O", "0-0-0")):
        return f"{lower_color} castles queenside"
    if clean.startswith(("O-O", "0-0")):
        return f"{lower_color} castles kingside"

    suffix = ""
    if clean.endswith("#"):
        suffix = ", checkmate"
    elif clean.endswith("+"):
        suffix = ", check"

    body = clean.rstrip("+#")
    promotion = ""
    if "=" in body:
        body, promo = body.split("=", 1)
        promoted_piece = PIECE_NAMES.get(promo[:1], promo[:1])
        promotion = f" and promotes to a {promoted_piece}"

    squares = re.findall(r"[a-h][1-8]", body)
    target = squares[-1] if squares else "?"
    capture = "x" in body

    first = body[0] if body else ""
    if first in PIECE_NAMES:
        piece = PIECE_NAMES[first]
        action = "captures on" if capture else "to"
        return f"{lower_color} {piece} {action} {target}{suffix}"

    if capture and len(body) >= 1 and body[0] in "abcdefgh":
        return f"{lower_color} pawn from the {body[0]}-file captures on {target}{promotion}{suffix}"

    return f"{lower_color} pawn to {target}{promotion}{suffix}"


def notation_drill_report(report: Report, count: int, plies: int) -> str:
    lines: list[str] = []
    window = f"last {report.days} days" if report.days else f"since {report.since}"
    lines.append(f"# Notation drills for {report.username}")
    lines.append("")
    lines.append(f"Built from your games in the {window}.")
    lines.append("")
    lines.append("## Tiny key")
    lines.append("- No letter = pawn move, e.g. `e4` = pawn to e4")
    lines.append("- `N` knight, `B` bishop, `R` rook, `Q` queen, `K` king")
    lines.append("- `x` captures, `+` check, `#` checkmate")
    lines.append("- `O-O` castles kingside, `O-O-O` castles queenside")
    lines.append("")

    games = [g for g in reversed(report.games) if g.opening_moves]
    if not games:
        lines.append("No recent games found to build drills from.")
        return "\n".join(lines)

    seen: set[str] = set()
    drill_no = 1
    for game in games:
        moves = game.opening_moves[:plies]
        if not moves:
            continue
        read_line = format_line(moves, max_plies=plies)
        if read_line in seen:
            continue
        seen.add(read_line)
        lines.append(f"## Drill {drill_no}: {game.opening_key}")
        lines.append(f"Game: {game.date} as {game.color} vs {game.opponent}")
        lines.append("")
        lines.append(f"Read this: `{read_line}`")
        lines.append("")
        lines.append("Say each move aloud, then check:")
        for move in moves:
            label = f"{move.fullmove}." if move.color == "white" else f"{move.fullmove}..."
            lines.append(f"- `{label} {move.san}` → {explain_san(move.san, move.color)}")
        lines.append("")
        drill_no += 1
        if drill_no > count:
            break

    lines.append("## 5-minute rote loop")
    lines.append("1. Cover the translations.")
    lines.append("2. Read one drill aloud slowly.")
    lines.append("3. Put the moves on a board.")
    lines.append("4. Reset and repeat once without looking.")
    lines.append("5. Stop after 5 minutes — consistency beats cramming.")
    return "\n".join(lines)


def markdown_report(report: Report) -> str:
    games = report.games
    lines: list[str] = []
    window = f"last {report.days} days" if report.days else f"since {report.since}"
    lines.append(f"# Chess.com coaching report for {report.username}")
    lines.append("")
    lines.append(f"Window: {window} → {report.until} UTC")
    lines.append(f"Summary: {result_summary(games)}")

    if not games:
        lines.append("")
        lines.append("No Chess.com games found in this window.")
        return "\n".join(lines)

    lines.append("")
    lines.append("## Your one thing to work on")
    if report.recommendations:
        lines.append(report.recommendations[0])
    else:
        lines.append("Make one opening plan memorable before adding more theory.")

    lines.append("")
    lines.append("## Recurring patterns")
    if report.motif_rows:
        for row in report.motif_rows[:6]:
            lines.append(f"- **{row['motif']}** — {row['games']} games, {row['wins']}W-{row['draws']}D-{row['losses']}L")
    else:
        lines.append("- No obvious recurring opening-habit pattern detected in this small sample.")

    lines.append("")
    lines.append("## Opening review queue")
    if report.opening_rows:
        for row in report.opening_rows[:5]:
            motifs = ", ".join(row["top_motifs"]) if row["top_motifs"] else "no repeated motif"
            lines.append(
                f"- **As {row['color']}: {row['opening']}** — {row['games']} games, "
                f"{row['wins']}W-{row['draws']}D-{row['losses']}L, {row['score_pct']}% score. Pattern: {motifs}."
            )
            lines.append(f"  - Memory line: `{row['sample_line']}`")
            if row.get("sample_url"):
                lines.append(f"  - Example: {row['sample_url']}")
    else:
        lines.append("- No openings found.")

    lines.append("")
    lines.append("## Next-session checklist")
    for rec in report.recommendations[:4]:
        lines.append(f"- {rec}")

    latest_losses = [g for g in reversed(games) if g.result == "loss"][:3]
    if latest_losses:
        lines.append("")
        lines.append("## Recent losses to glance at")
        for game in latest_losses:
            motif_text = ", ".join(game.motifs[:3]) if game.motifs else "no opening motif tagged"
            lines.append(f"- {game.date} as {game.color} vs {game.opponent}: {game.opening_key}; {motif_text}; {game.url}")

    return "\n".join(lines)


def save_cards(report: Report) -> Path:
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(report.generated_at.encode()).hexdigest()[:8]
    path = CARDS_DIR / f"opening-cards-{dt.date.today().isoformat()}-{digest}.md"
    rows = report.opening_rows[:8]
    chunks = [f"# Opening cards for {report.username}", ""]
    for row in rows:
        chunks.append(f"## As {row['color']}: {row['opening']}")
        chunks.append("")
        chunks.append(f"Line: `{row['sample_line']}`")
        chunks.append("")
        motifs = ", ".join(row["top_motifs"]) if row["top_motifs"] else "none spotted"
        chunks.append(f"Remember: {motifs}")
        chunks.append("")
        chunks.append("Rule: develop, make the king safe, then start tactics unless there is a forcing reason.")
        chunks.append("")
    path.write_text("\n".join(chunks))
    return path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyse recent Chess.com games for opening habits and actionable coaching.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--username", default=os.environ.get("CHESS_COACH_USERNAME"), help="Chess.com username")
    parser.add_argument("--days", type=int, default=3, help="Number of days back to analyse")
    parser.add_argument("--yesterday", action="store_true", help="Analyse the previous UTC calendar day")
    parser.add_argument("--since", help="Start date YYYY-MM-DD. Overrides --days")
    parser.add_argument("--until", help="End date YYYY-MM-DD, defaults to now UTC")
    parser.add_argument("--cache-ttl", type=int, default=300, help="Monthly archive cache TTL in seconds")
    parser.add_argument("--no-cache", action="store_true", help="Bypass local cache")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    parser.add_argument("--notation-drill", action="store_true", help="Emit rote algebraic notation drills from recent games")
    parser.add_argument("--drill-count", type=int, default=5, help="Number of notation drills to emit")
    parser.add_argument("--drill-plies", type=int, default=8, help="Number of half-moves per notation drill")
    parser.add_argument("--save-cards", action="store_true", help="Write opening cards to ~/.pi/agent/chess-coach/")
    return parser.parse_args(argv)


def date_start(value: str) -> dt.datetime:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    except ValueError as exc:
        raise SystemExit(f"Invalid date {value!r}; expected YYYY-MM-DD") from exc


def main(argv: list[str]) -> int:
    load_config_env()
    args = parse_args(argv)
    if not args.username:
        raise SystemExit("Chess.com username required: pass --username or set CHESS_COACH_USERNAME")

    now = dt.datetime.now(tz=dt.timezone.utc)
    if args.yesterday:
        if args.since or args.until:
            raise SystemExit("--yesterday cannot be combined with --since or --until")
        yesterday = now.date() - dt.timedelta(days=1)
        start = dt.datetime.combine(yesterday, dt.time.min, tzinfo=dt.timezone.utc)
        until = dt.datetime.combine(yesterday, dt.time.max, tzinfo=dt.timezone.utc).replace(microsecond=0)
        days = None
        args.since = yesterday.isoformat()
    else:
        if args.until:
            until = date_start(args.until) + dt.timedelta(days=1) - dt.timedelta(seconds=1)
        else:
            until = now

        if args.since:
            start = date_start(args.since)
            days = None
        else:
            if args.days < 1:
                raise SystemExit("--days must be >= 1")
            days = args.days
            start = until - dt.timedelta(days=args.days)

    report = build_report(
        username=args.username,
        days=days,
        since=args.since,
        start=start,
        end=until,
        ttl=args.cache_ttl,
        no_cache=args.no_cache,
    )

    saved: Path | None = None
    if args.save_cards:
        saved = save_cards(report)

    if args.json:
        data = asdict(report)
        if saved:
            data["saved_cards"] = str(saved)
        print(json.dumps(data, indent=2))
    elif args.notation_drill:
        print(notation_drill_report(report, count=args.drill_count, plies=args.drill_plies))
        if saved:
            print(f"\nSaved opening cards: {saved}")
    else:
        print(markdown_report(report))
        if saved:
            print(f"\nSaved opening cards: {saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
