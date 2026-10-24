#!/usr/bin/env bash
# Usage: smoke-test.sh IMAGE [INSTALL_PYTHON] [INSTALL_GO] [INSTALL_DOCKER]
set -euo pipefail
image=${1:?Usage: smoke-test.sh IMAGE [true|false] [true|false] [true|false]}
python_enabled=${2:-true}
go_enabled=${3:-true}
docker_enabled=${4:-true}
for flag in "$python_enabled" "$go_enabled" "$docker_enabled"; do
  case "$flag" in true|false) ;; *) printf 'Expected true or false, got %s\n' "$flag" >&2; exit 2 ;; esac
done
container="dsh-smoke-$$-${RANDOM}"
cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT
security=(--security-opt seccomp=unconfined --security-opt no-new-privileges --cap-drop ALL)
docker run --rm "${security[@]}" --entrypoint /bin/bash "$image" -euc '
  test "$(id -u)" = 1000
  for tool in node npm pnpm git ssh curl jq rg unzip zip make gcc bwrap; do command -v "$tool" >/dev/null; done
  test -w /data
  test -w /workspace
  test ! -S /var/run/docker.sock
  test ! -e /usr/bin/dockerd
  bwrap --ro-bind / / --dev /dev --proc /proc --die-with-parent -- true
'
docker run --rm --entrypoint /bin/bash "$image" -euc '
  if [ "$1" = true ]; then python3 --version; python3 -m pip --version; python3 -m venv /tmp/check-venv; elif command -v python3; then echo "Python was not disabled" >&2; exit 1; fi
  if [ "$2" = true ]; then go version; elif command -v go; then echo "Go was not disabled" >&2; exit 1; fi
  if [ "$3" = true ]; then docker --version; docker buildx version; docker compose version; elif command -v docker; then echo "Docker was not disabled" >&2; exit 1; fi
' -- "$python_enabled" "$go_enabled" "$docker_enabled"
docker run --rm "${security[@]}" "$image" --help >/dev/null
docker run --rm "${security[@]}" "$image" web --help >/dev/null
docker run -d --name "$container" "${security[@]}" \
  -e DSH_PERMISSION_MODE=workspace-write -e DSH_TELEMETRY_DISABLED=1 \
  "$image" web --trusted-host 127.0.0.1 >/dev/null
for _ in $(seq 1 90); do
  if docker exec "$container" /usr/local/bin/dsh-healthcheck; then
    docker exec "$container" /bin/sh -ec 'test -d "$HOME" && test -w "$HOME" && test -d "$DSH_HOME"'
    printf 'Smoke test passed: %s\n' "$image"
    exit 0
  fi
  if [ "$(docker inspect --format '{{.State.Running}}' "$container")" != true ]; then break; fi
  sleep 2
done
docker logs "$container" >&2
printf 'Web health check failed: %s\n' "$image" >&2
exit 1
