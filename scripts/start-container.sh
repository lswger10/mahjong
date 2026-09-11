#!/usr/bin/env bash
set -euo pipefail

# No tunnel configuration keeps the existing standalone deployment behavior.
if [[ -z ${MAHJONG_TUNNEL_ID:-} && -z ${CONTROL_PLANE_API_KEY:-} ]]; then
  exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8080}"
fi
: "${MAHJONG_TUNNEL_ID:?Set the tunnel ID}"
: "${CONTROL_PLANE_API_KEY:?Set the tunnel runtime key}"
export MAHJONG_MCP_PORT=8898
profile_dir=$(mktemp -d)
game_pid=''
tunnel_pid=''
cleanup() {
  trap - EXIT TERM INT
  [[ -z $tunnel_pid ]] || kill -TERM "$tunnel_pid" 2>/dev/null || true
  [[ -z $game_pid ]] || kill -TERM "$game_pid" 2>/dev/null || true
  wait || true
  rm -rf -- "$profile_dir"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# The generated profile contains only a secret reference, never the key.
env -u CONTROL_PLANE_API_KEY tunnel-client init \
  --profile mahjong-seat --profile-dir "$profile_dir" \
  --tunnel-id "$MAHJONG_TUNNEL_ID" \
  --mcp-server-url http://127.0.0.1:8898/mcp \
  --health-listen-addr 127.0.0.1:8897
(unset CONTROL_PLANE_API_KEY; exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8080}") &
game_pid=$!
(exec tunnel-client run --profile mahjong-seat --profile-dir "$profile_dir") &
tunnel_pid=$!
# A failed child ends this container; the platform owns restart policy.
set +e
wait -n "$game_pid" "$tunnel_pid"
status=$?
[[ $status -ne 0 ]] || status=1
exit "$status"
