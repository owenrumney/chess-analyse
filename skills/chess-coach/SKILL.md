---
name: chess-coach
description: Fetches recent Chess.com games and turns them into short, actionable chess coaching focused on openings, recurring habits, algebraic-notation drills, and easy-to-remember improvements. Use when the user asks to analyse Chess.com games, review recent chess games, improve openings, find recurring chess mistakes, practise notation, or get chess coaching.
---

# Chess Coach

Use this skill to analyse recent Chess.com games and produce small, memorable improvements. The skill values practical opening memory and recurring habit feedback over deep engine commentary.

## Default assumptions

- Chess.com username should be passed with `--username` or configured as `CHESS_COACH_USERNAME` in `~/.pi/agent/chess-coach/config.env`.
- Default window: last 3 days.
- Prefer concise, ADHD-friendly coaching:
  - one main lesson
  - 2-3 supporting observations
  - one opening memory card
  - one drill for the next session
  - rote algebraic-notation practice when the user mentions struggling to read notation
- Do not overwhelm with long PGN dumps.
- Do not pretend to do engine analysis unless an engine-backed script was actually run.

## Run the analyser

After installation, from any directory:

```bash
python3 "$HOME/.pi/agent/skills/chess-coach/scripts/chess_coach.py" --days 3
```

Useful options:

```bash
# Analyse a different window
python3 "$HOME/.pi/agent/skills/chess-coach/scripts/chess_coach.py" --days 7

# Analyse the previous UTC calendar day
python3 "$HOME/.pi/agent/skills/chess-coach/scripts/chess_coach.py" --yesterday

# Analyse from an explicit date
python3 "$HOME/.pi/agent/skills/chess-coach/scripts/chess_coach.py" --since 2026-05-24

# Emit JSON for custom summarisation
python3 "$HOME/.pi/agent/skills/chess-coach/scripts/chess_coach.py" --days 3 --json

# Save opening flashcards locally under ~/.pi/agent/chess-coach/
python3 "$HOME/.pi/agent/skills/chess-coach/scripts/chess_coach.py" --days 7 --save-cards

# Generate rote algebraic-notation drills from recent games
python3 "$HOME/.pi/agent/skills/chess-coach/scripts/chess_coach.py" --days 3 --notation-drill
```

The script uses Chess.com's public API and only standard-library Python. It caches monthly archives under `~/.pi/agent/cache/pi-chess-coach/`.

## Daily scheduled report

A wrapper script writes a combined coaching + notation report for the previous UTC day:

```bash
"$HOME/.pi/agent/skills/chess-coach/scripts/daily_chess_report.sh"
```

Reports are saved under:

```text
~/.pi/agent/chess-coach/reports/
```

On macOS, install the LaunchAgent via the package installer:

```bash
./install.sh --username YOUR_CHESS_COM_USERNAME --with-launchagent --hour 8 --minute 0
```

## How to respond

After running the analyser, transform the report into coaching language:

1. Start with: `Your one thing to work on:`
2. Name the most important recurring pattern.
3. Give a concrete rule of thumb, not vague advice.
4. Include one opening memory card using a short line from the user's own games.
5. End with a next-session goal that can be checked after 3-5 games.

Example response shape:

```md
Your one thing to work on: castle before pawn-grabbing in the Italian-style positions.

Why: in 3 recent losses you pushed flank pawns or hunted material before your king was safe.

Memory card:
1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5
Rule: develop, castle, then open the centre — not the other way round.

Next-session drill:
For your next 5 rapid games, write down after move 8: "Is my king safe and are both minor pieces developed?"
```

## Analysis limits

This first version is pattern-based, not engine-based. It can reliably spot:

- opening families from Chess.com PGN headers
- recent win/loss/draw patterns by opening
- short losses
- delayed castling
- early queen moves
- flank/f-pawn moves before castling
- low minor-piece development in the opening
- rote algebraic-notation drills using the first moves from the user's own recent games

If the user asks for tactical/blunder accuracy, say that this needs a Stockfish-backed upgrade and offer to add it.
