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
LOG_DIR="${CHESS_COACH_LOG_DIR:-${CONFIG_DIR}/logs}"
DRILL_COUNT="${CHESS_COACH_DRILL_COUNT:-5}"
DRILL_PLIES="${CHESS_COACH_DRILL_PLIES:-8}"
OPEN_MDVIEW="${CHESS_COACH_OPEN_MDVIEW:-0}"
MDVIEW_AGENT="${CHESS_COACH_MDVIEW_AGENT:-pi}"

REPORT_DATE="${CHESS_COACH_DATE:-$(python3 - <<'PY'
import datetime as dt
print((dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat())
PY
)}"

mkdir -p "${REPORT_DIR}" "${LOG_DIR}"
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

if [[ "${OPEN_MDVIEW}" == "1" ]]; then
  if command -v mdview >/dev/null 2>&1; then
    MDVIEW_BIN="$(command -v mdview)"
    MDVIEW_LOG="${LOG_DIR}/mdview.log"
    MDVIEW_RUN_LOG="${LOG_DIR}/mdview-${REPORT_DATE}.log"
    MDVIEW_PID_FILE="${LOG_DIR}/mdview.pid"

    if [[ -f "${MDVIEW_PID_FILE}" ]]; then
      OLD_PID="$(cat "${MDVIEW_PID_FILE}" 2>/dev/null || true)"
      if [[ "${OLD_PID}" =~ ^[0-9]+$ ]] && kill -0 "${OLD_PID}" >/dev/null 2>&1; then
        kill "${OLD_PID}" >/dev/null 2>&1 || true
      fi
    fi

    : >"${MDVIEW_RUN_LOG}"
    nohup "${MDVIEW_BIN}" "${OUT}" --chat --chat-agent "${MDVIEW_AGENT}" -c >>"${MDVIEW_RUN_LOG}" 2>&1 &
    MDVIEW_PID="$!"
    echo "${MDVIEW_PID}" >"${MDVIEW_PID_FILE}"

    MDVIEW_URL=""
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
      MDVIEW_URL="$(sed -n 's/.*url=\(http:\/\/[^ ]*\).*/\1/p' "${MDVIEW_RUN_LOG}" | tail -1)"
      if [[ -n "${MDVIEW_URL}" ]]; then
        break
      fi
      if ! kill -0 "${MDVIEW_PID}" >/dev/null 2>&1; then
        break
      fi
      sleep 0.5
    done

    cat "${MDVIEW_RUN_LOG}" >>"${MDVIEW_LOG}" 2>/dev/null || true
    echo "Opened ${OUT} with ${MDVIEW_BIN} --chat --chat-agent ${MDVIEW_AGENT}"
    echo "mdview pid: ${MDVIEW_PID}"
    echo "mdview run log: ${MDVIEW_RUN_LOG}"
    echo "mdview combined log: ${MDVIEW_LOG}"

    if [[ -n "${MDVIEW_URL}" ]]; then
      echo "mdview url: ${MDVIEW_URL}"
      if command -v open >/dev/null 2>&1; then
        open "${MDVIEW_URL}" >/dev/null 2>&1 || echo "Could not open ${MDVIEW_URL}; open it manually" >&2
      fi
    else
      echo "Could not detect mdview URL; check ${MDVIEW_RUN_LOG}" >&2
    fi
  else
    echo "CHESS_COACH_OPEN_MDVIEW=1 but mdview was not found on PATH" >&2
  fi
fi

echo "Saved ${OUT}"
