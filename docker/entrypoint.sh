#!/bin/sh
set -eu
umask 077
mkdir -p "$HOME" "$DSH_HOME" "$HOME/.local/bin" "$HOME/go" "$HOME/.cache"
if [ "${1:-}" = web ]; then
    shift
    exec dsh web --host "$(node /opt/dsh/listen-address.mjs)" --port "${PORT:-3080}" --no-open "$@"
fi
exec dsh "$@"
