#!/usr/bin/env bash
set -euo pipefail

LABEL="com.pi.chess-coach.daily"
HOUR="${CHESS_COACH_LAUNCH_HOUR:-8}"
MINUTE="${CHESS_COACH_LAUNCH_MINUTE:-0}"
SKILL_DIR="${CHESS_COACH_SKILL_DIR:-${HOME}/.pi/agent/skills/chess-coach}"
CONFIG_DIR="${CHESS_COACH_CONFIG_DIR:-${HOME}/.pi/agent/chess-coach}"
REPORT_DIR="${CHESS_COACH_REPORT_DIR:-${CONFIG_DIR}/reports}"
LOG_DIR="${CHESS_COACH_LOG_DIR:-${CONFIG_DIR}/logs}"
DEST_DIR="${HOME}/Library/LaunchAgents"
DEST="${DEST_DIR}/${LABEL}.plist"
DOMAIN="gui/$(id -u)"

usage() {
  cat <<EOF
Usage: $0 [--hour H] [--minute M]

Installs a macOS LaunchAgent that runs the Chess Coach daily report.

Environment overrides:
  CHESS_COACH_SKILL_DIR      default: ~/.pi/agent/skills/chess-coach
  CHESS_COACH_CONFIG_DIR     default: ~/.pi/agent/chess-coach
  CHESS_COACH_REPORT_DIR     default: ~/.pi/agent/chess-coach/reports
  CHESS_COACH_LAUNCH_HOUR    default: 8
  CHESS_COACH_LAUNCH_MINUTE  default: 0
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hour) HOUR="$2"; shift 2 ;;
    --minute) MINUTE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ! -x "${SKILL_DIR}/scripts/daily_chess_report.sh" ]]; then
  echo "Could not find executable daily script at ${SKILL_DIR}/scripts/daily_chess_report.sh" >&2
  echo "Run ./install.sh first, or set CHESS_COACH_SKILL_DIR." >&2
  exit 2
fi

mkdir -p "${DEST_DIR}" "${REPORT_DIR}" "${LOG_DIR}"

cat > "${DEST}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${SKILL_DIR}/scripts/daily_chess_report.sh</string>
  </array>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>${HOUR}</integer>
    <key>Minute</key>
    <integer>${MINUTE}</integer>
  </dict>

  <key>WorkingDirectory</key>
  <string>${HOME}</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:${HOME}/go/bin:${HOME}/.local/bin:${HOME}/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>CHESS_COACH_CONFIG_DIR</key>
    <string>${CONFIG_DIR}</string>
    <key>CHESS_COACH_REPORT_DIR</key>
    <string>${REPORT_DIR}</string>
  </dict>

  <key>StandardOutPath</key>
  <string>${LOG_DIR}/launchd.out.log</string>

  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchd.err.log</string>
</dict>
</plist>
PLIST

plutil -lint "${DEST}"
launchctl bootout "${DOMAIN}" "${DEST}" >/dev/null 2>&1 || true
launchctl bootstrap "${DOMAIN}" "${DEST}"
launchctl enable "${DOMAIN}/${LABEL}"

echo "Installed ${LABEL} at ${DEST}"
echo "Schedule: daily at $(printf '%02d:%02d' "${HOUR}" "${MINUTE}")"
echo "Reports: ${REPORT_DIR}"
echo "Logs: ${LOG_DIR}"
