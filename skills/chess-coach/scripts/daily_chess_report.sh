#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COACH="${SCRIPT_DIR}/chess_coach.py"
CONFIG_DIR="${CHESS_COACH_CONFIG_DIR:-${HOME}/.pi/agent/chess-coach}"
CONFIG_FILE="${CHESS_COACH_CONFIG:-${CONFIG_DIR}/config.env}"

if [[ -f "${CONFIG_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

USERNAME="${CHESS_COACH_USERNAME:-}"
if [[ -z "${USERNAME}" ]]; then
  echo "CHESS_COACH_USERNAME is not set. Add it to ${CONFIG_FILE} or export it." >&2
  exit 2
fi

REPORT_DIR="${CHESS_COACH_REPORT_DIR:-${CONFIG_DIR}/reports}"
DRILL_COUNT="${CHESS_COACH_DRILL_COUNT:-5}"
DRILL_PLIES="${CHESS_COACH_DRILL_PLIES:-8}"

REPORT_DATE="${CHESS_COACH_DATE:-$(python3 - <<'PY'
import datetime as dt
print((dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat())
PY
)}"

mkdir -p "${REPORT_DIR}"
OUT="${REPORT_DIR}/${REPORT_DATE}-chess-coach.md"
TMP="${OUT}.tmp"

{
  echo "# Daily Chess Coach — ${REPORT_DATE}"
  echo
  echo "Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo
  echo "## Coaching notes"
  echo
  python3 "${COACH}" --username "${USERNAME}" --yesterday
  echo
  echo "---"
  echo
  echo "## Notation drills"
  echo
  python3 "${COACH}" --username "${USERNAME}" --yesterday --notation-drill --drill-count "${DRILL_COUNT}" --drill-plies "${DRILL_PLIES}"
} > "${TMP}"

mv "${TMP}" "${OUT}"

if command -v osascript >/dev/null 2>&1; then
  osascript -e "display notification \"Saved ${OUT}\" with title \"Chess coach report ready\"" >/dev/null 2>&1 || true
fi

echo "Saved ${OUT}"
