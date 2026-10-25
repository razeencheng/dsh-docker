#!/bin/sh
set -eu
umask 077
mkdir -p "$HOME" "$DSH_HOME" "$HOME/.local/bin" "$HOME/go" "$HOME/.cache"
if [ "${1:-}" = web ]; then
    shift
    has_host=false
    has_port=false
    dump_config=false
    for argument do
        case "$argument" in
            --host|--host=*) has_host=true ;;
            --port|--port=*) has_port=true ;;
            --dump-config|--dump-default-config|--dump-config-schema) dump_config=true ;;
        esac
    done
    # Launcher flags such as --patch must precede the first Web-only flag.
    # Append missing defaults so user arguments keep their original boundary.
    if [ "$dump_config" = false ]; then
        if [ "$has_host" = false ]; then
            set -- "$@" --host "$(node /opt/dsh/listen-address.mjs)"
        fi
        if [ "$has_port" = false ]; then
            set -- "$@" --port "${PORT:-3080}"
        fi
        set -- "$@" --no-open
    fi
    exec dsh web "$@"
fi
exec dsh "$@"
