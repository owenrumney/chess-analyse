# Chess Coach Pi Skill

A small, installable [Pi](https://github.com/earendil-works/pi-coding-agent)-style skill for analysing recent Chess.com games and producing short, actionable coaching notes.

It focuses on:

- recurring opening habits
- simple next-game rules
- algebraic-notation rote drills
- daily previous-day reports

It deliberately does **not** claim engine/blunder accuracy. The analyser is pattern-based and uses only Python's standard library plus Chess.com's public API.

## Install

```bash
git clone <this-repo>
cd chess-analyse
./install.sh --username YOUR_CHESS_COM_USERNAME
```

Example:

```bash
./install.sh --username owen1979
```

This installs the skill to:

```text
~/.pi/agent/skills/chess-coach
```

and writes config/reports under:

```text
~/.pi/agent/chess-coach
```

## Run manually

```bash
python3 ~/.pi/agent/skills/chess-coach/scripts/chess_coach.py --username YOUR_CHESS_COM_USERNAME --days 3
```

Notation drills:

```bash
python3 ~/.pi/agent/skills/chess-coach/scripts/chess_coach.py --username YOUR_CHESS_COM_USERNAME --days 3 --notation-drill
```

Previous UTC day:

```bash
python3 ~/.pi/agent/skills/chess-coach/scripts/chess_coach.py --username YOUR_CHESS_COM_USERNAME --yesterday
```

Daily combined report:

```bash
~/.pi/agent/skills/chess-coach/scripts/daily_chess_report.sh
```

Reports are written to:

```text
~/.pi/agent/chess-coach/reports/YYYY-MM-DD-chess-coach.md
```

## macOS LaunchAgent schedule

Install the skill and schedule a report at 08:00 every morning:

```bash
./install.sh --username YOUR_CHESS_COM_USERNAME --with-launchagent --hour 8 --minute 0
```

The LaunchAgent runs the daily report script for the previous UTC calendar day.

To open the new Markdown report in `mdview` with Pi chat after creation:

```bash
./install.sh --username YOUR_CHESS_COM_USERNAME --with-launchagent --open-mdview
```

That sets the daily script to start `mdview`, detect the local live URL, then open that URL in the browser:

```bash
mdview <new_markdown_report> --chat --chat-agent pi -c
open <mdview_live_url>
```

`mdview` must be installed and available on the LaunchAgent PATH. The installer includes common locations such as `/opt/homebrew/bin`, `/usr/local/bin`, `~/go/bin`, and `~/.local/bin`.

You can choose a different mdview chat agent with:

```bash
./install.sh --username YOUR_CHESS_COM_USERNAME --with-launchagent --open-mdview --mdview-agent pi
```

Logs:

```text
~/.pi/agent/chess-coach/logs/launchd.out.log
~/.pi/agent/chess-coach/logs/launchd.err.log
~/.pi/agent/chess-coach/logs/mdview.log
~/.pi/agent/chess-coach/logs/mdview-YYYY-MM-DD.log
```

Inspect the job:

```bash
launchctl print gui/$(id -u)/com.pi.chess-coach.daily
```

Run immediately for testing:

```bash
~/.pi/agent/skills/chess-coach/scripts/daily_chess_report.sh
```

## Configuration

Config is stored in:

```text
~/.pi/agent/chess-coach/config.env
```

Example:

```bash
CHESS_COACH_USERNAME=owen1979
CHESS_COACH_REPORT_DIR=/Users/you/.pi/agent/chess-coach/reports
CHESS_COACH_LOG_DIR=/Users/you/.pi/agent/chess-coach/logs
CHESS_COACH_DRILL_COUNT=5
CHESS_COACH_DRILL_PLIES=8
CHESS_COACH_OPEN_MDVIEW=0
CHESS_COACH_MDVIEW_AGENT=pi
```

## Uninstall

```bash
~/.pi/agent/chess-coach/uninstall.sh
```

This removes the skill and LaunchAgent. Reports are left in place.

## Development

Validate the Python script:

```bash
python3 -m py_compile skills/chess-coach/scripts/chess_coach.py
```

Run from the repo without installing:

```bash
CHESS_COACH_USERNAME=YOUR_CHESS_COM_USERNAME \
CHESS_COACH_CONFIG_DIR="$PWD/.local" \
./skills/chess-coach/scripts/daily_chess_report.sh
```
