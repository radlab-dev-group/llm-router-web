#!/usr/bin/env bash
set -e

DEBUG_MODE=false
APP_NAME=""

for arg in "$@"; do
    case "$arg" in
        --debug|debug|--shell|shell)
            DEBUG_MODE=true
            ;;
        *)
            # pierwszy nie-debug argument traktujemy jako nazwę aplikacji
            if [ -z "$APP_NAME" ]; then
                APP_NAME="$arg"
            fi
            ;;
    esac
done

echo "[entrypoint] Working directory: $(pwd)"
echo "---"

if [ "$DEBUG_MODE" = true ]; then
    echo "[entrypoint] **Debug mode activated**. Container will stay alive for exec."
    sleep infinity
    exit 0
fi

# mapowanie nazwy aplikacji -> skrypt
case "$APP_NAME" in
    anonymizer)
        APP_SCRIPT="run-anonymizer.sh"
        ;;
    configs-manager|configs)
        APP_SCRIPT="run-configs-manager.sh"
        ;;
    "")
        echo "[entrypoint] ERROR: No application name provided!"
        echo "[entrypoint] Available apps: anonymizer, configs-manager"
        exit 1
        ;;
    *)
        echo "[entrypoint] ERROR: Unknown application: $APP_NAME"
        echo "[entrypoint] Available apps: anonymizer, configs-manager"
        exit 1
        ;;
esac

if [ ! -f "./$APP_SCRIPT" ]; then
    echo "[entrypoint] ERROR: Application script **$APP_SCRIPT** not found!"
    exit 1
fi

echo "[entrypoint] Starting application using **$APP_SCRIPT** ..."
exec bash "./$APP_SCRIPT"