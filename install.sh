#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USERNAME=""
INSTALL_LAUNCHAGENT=0
HOUR=8
MINUTE=0
SKILL_DEST="${HOME}/.pi/agent/skills/chess-coach"
CONFIG_DIR="${HOME}/.pi/agent/chess-coach"

usage() {
  cat <<EOF
Usage: ./install.sh --username CHESS_COM_USERNAME [options]

Installs the Chess Coach Pi skill and optional macOS LaunchAgent.

Options:
  --username NAME         Chess.com username to analyse (required)
  --with-launchagent      Install daily macOS LaunchAgent
  --hour H                LaunchAgent hour, 0-23 (default: 8)
  --minute M              LaunchAgent minute, 0-59 (default: 0)
  --skill-dest DIR        Skill install dir (default: ~/.pi/agent/skills/chess-coach)
  --config-dir DIR        Config/report dir (default: ~/.pi/agent/chess-coach)
  -h, --help              Show this help

Examples:
  ./install.sh --username owen1979
  ./install.sh --username owen1979 --with-launchagent --hour 8 --minute 0
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --username) USERNAME="$2"; shift 2 ;;
    --with-launchagent) INSTALL_LAUNCHAGENT=1; shift ;;
    --hour) HOUR="$2"; shift 2 ;;
    --minute) MINUTE="$2"; shift 2 ;;
    --skill-dest) SKILL_DEST="$2"; shift 2 ;;
    --config-dir) CONFIG_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "${USERNAME}" ]]; then
  echo "--username is required" >&2
  usage >&2
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

mkdir -p "$(dirname "${SKILL_DEST}")" "${CONFIG_DIR}" "${CONFIG_DIR}/reports" "${CONFIG_DIR}/logs"
rm -rf "${SKILL_DEST}"
cp -R "${ROOT_DIR}/skills/chess-coach" "${SKILL_DEST}"
chmod +x "${SKILL_DEST}/scripts/chess_coach.py" "${SKILL_DEST}/scripts/daily_chess_report.sh"

cat > "${CONFIG_DIR}/config.env" <<EOF
# Chess Coach config
CHESS_COACH_USERNAME=${USERNAME}
CHESS_COACH_REPORT_DIR=${CONFIG_DIR}/reports
CHESS_COACH_DRILL_COUNT=5
CHESS_COACH_DRILL_PLIES=8
EOF

python3 -m py_compile "${SKILL_DEST}/scripts/chess_coach.py"
rm -rf "${SKILL_DEST}/scripts/__pycache__"

cat > "${CONFIG_DIR}/uninstall.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
LABEL="com.pi.chess-coach.daily"
PLIST="\${HOME}/Library/LaunchAgents/\${LABEL}.plist"
launchctl bootout "gui/\$(id -u)" "\${PLIST}" >/dev/null 2>&1 || true
rm -f "\${PLIST}"
rm -rf "${SKILL_DEST}"
echo "Removed Chess Coach skill and LaunchAgent. Reports remain in ${CONFIG_DIR}/reports."
EOF
chmod +x "${CONFIG_DIR}/uninstall.sh"

if [[ "${INSTALL_LAUNCHAGENT}" == "1" ]]; then
  CHESS_COACH_SKILL_DIR="${SKILL_DEST}" \
  CHESS_COACH_CONFIG_DIR="${CONFIG_DIR}" \
  CHESS_COACH_LAUNCH_HOUR="${HOUR}" \
  CHESS_COACH_LAUNCH_MINUTE="${MINUTE}" \
    "${ROOT_DIR}/scripts/install-launchagent.sh"
fi

cat <<EOF
Installed Chess Coach.

Skill:   ${SKILL_DEST}
Config:  ${CONFIG_DIR}/config.env
Reports: ${CONFIG_DIR}/reports

Try it:
  python3 "${SKILL_DEST}/scripts/chess_coach.py" --username "${USERNAME}" --days 3
  "${SKILL_DEST}/scripts/daily_chess_report.sh"

Uninstall:
  "${CONFIG_DIR}/uninstall.sh"
EOF
