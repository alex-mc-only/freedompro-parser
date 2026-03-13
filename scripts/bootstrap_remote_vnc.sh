#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

DISPLAY_NUM="${DISPLAY_NUM:-:99}"
SCREEN_GEOMETRY="${SCREEN_GEOMETRY:-1600x900x24}"
VNC_PORT="${VNC_PORT:-5901}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
WAIT_SECONDS="${WAIT_SECONDS:-300}"
CDP_PORT="${CDP_PORT:-9222}"

if ! command -v Xvfb >/dev/null 2>&1; then
  echo "Xvfb is required. Install: sudo apt-get install -y xvfb x11vnc fluxbox" >&2
  exit 1
fi

if ! command -v x11vnc >/dev/null 2>&1; then
  echo "x11vnc is required. Install: sudo apt-get install -y x11vnc" >&2
  exit 1
fi

if ! command -v fluxbox >/dev/null 2>&1; then
  echo "fluxbox is required. Install: sudo apt-get install -y fluxbox" >&2
  exit 1
fi

cleanup() {
  set +e
  [[ -n "${NOVNC_PID:-}" ]] && kill "$NOVNC_PID" >/dev/null 2>&1
  [[ -n "${VNC_PID:-}" ]] && kill "$VNC_PID" >/dev/null 2>&1
  [[ -n "${WM_PID:-}" ]] && kill "$WM_PID" >/dev/null 2>&1
  [[ -n "${XVFB_PID:-}" ]] && kill "$XVFB_PID" >/dev/null 2>&1
}
trap cleanup EXIT

Xvfb "$DISPLAY_NUM" -screen 0 "$SCREEN_GEOMETRY" -nolisten tcp &
XVFB_PID=$!
export DISPLAY="$DISPLAY_NUM"
sleep 1

fluxbox >/tmp/petrovich-fluxbox.log 2>&1 &
WM_PID=$!

x11vnc -display "$DISPLAY" -nopw -forever -shared -rfbport "$VNC_PORT" >/tmp/petrovich-x11vnc.log 2>&1 &
VNC_PID=$!

if [[ -x "./.venv/bin/novnc_proxy" ]]; then
  ./.venv/bin/novnc_proxy --vnc "127.0.0.1:${VNC_PORT}" --listen "$NOVNC_PORT" >/tmp/petrovich-novnc.log 2>&1 &
  NOVNC_PID=$!
fi

echo "Remote desktop ready: VNC :${VNC_PORT}, noVNC :${NOVNC_PORT}"
python3 main.py bootstrap-remote --wait-seconds "$WAIT_SECONDS" --remote-debugging-port "$CDP_PORT" --verbose
