#!/bin/sh
set -eu

MODE_FILE="/opt/topo/runtime-mode.txt"
FAIL_EXIT_CODE=42
INVALID_MODE_EXIT_CODE=64

healthy_loop() {
    while :; do
        sleep 3600
    done
}

run_mode() {
    case "$1" in
        healthy)
            printf '%s\n' 'topo causal fixture: healthy mode'
            healthy_loop
            ;;
        fail)
            printf '%s\n' 'topo causal fixture: fail mode; exiting 42' >&2
            exit "$FAIL_EXIT_CODE"
            ;;
        *)
            printf '%s\n' 'topo causal fixture: invalid runtime mode' >&2
            exit "$INVALID_MODE_EXIT_CODE"
            ;;
    esac
}

main() {
    mode=''
    if ! IFS= read -r mode < "$MODE_FILE"; then
        printf '%s\n' 'topo causal fixture: runtime mode is unreadable' >&2
        exit "$INVALID_MODE_EXIT_CODE"
    fi
    run_mode "$mode"
}

if [ "${0##*/}" = 'run.sh' ]; then
    main
fi
