#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

HOST="127.0.0.1"
PORT="8788"
PID_FILE="$ROOT_DIR/.uvicorn.pid"
LOG_FILE="/tmp/nms_uvicorn.log"

if [[ -x "/home/ad39013/.asdf/installs/python/3.11.4/bin/python3" ]]; then
	PYTHON_BIN="/home/ad39013/.asdf/installs/python/3.11.4/bin/python3"
else
	PYTHON_BIN="python3"
fi

is_running() {
	if [[ -f "$PID_FILE" ]]; then
		local pid
		pid="$(cat "$PID_FILE")"
		if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
			return 0
		fi
	fi
	return 1
}

start() {
	if is_running; then
		echo "Backend already running (pid $(cat "$PID_FILE"))."
		return 0
	fi

	fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
	nohup "$PYTHON_BIN" -m uvicorn api.main:app --host "$HOST" --port "$PORT" >"$LOG_FILE" 2>&1 &
	local pid=$!
	echo "$pid" >"$PID_FILE"
	sleep 1

	if kill -0 "$pid" 2>/dev/null; then
		echo "Backend started on http://${HOST}:${PORT} (pid $pid)."
	else
		echo "Backend failed to start. Check logs: $LOG_FILE"
		exit 1
	fi
}

stop() {
	if ! is_running; then
		echo "Backend is not running."
		rm -f "$PID_FILE"
		return 0
	fi

	local pid
	pid="$(cat "$PID_FILE")"
	kill "$pid" >/dev/null 2>&1 || true
	sleep 1
	kill -9 "$pid" >/dev/null 2>&1 || true
	rm -f "$PID_FILE"
	echo "Backend stopped."
}

status() {
	if is_running; then
		echo "Backend running (pid $(cat "$PID_FILE")) on http://${HOST}:${PORT}."
	else
		echo "Backend not running."
		return 1
	fi
}

logs() {
	if [[ -f "$LOG_FILE" ]]; then
		tail -n 80 "$LOG_FILE"
	else
		echo "No log file found at $LOG_FILE"
	fi
}

case "${1:-start}" in
	start)
		start
		;;
	stop)
		stop
		;;
	restart)
		stop
		start
		;;
	status)
		status
		;;
	logs)
		logs
		;;
	foreground)
		exec "$PYTHON_BIN" -m uvicorn api.main:app --host "$HOST" --port "$PORT"
		;;
	*)
		echo "Usage: $0 {start|stop|restart|status|logs|foreground}"
		exit 2
		;;
esac
