#!/bin/bash
# Lugalay's voice. Wraps the venv so nobody has to remember to activate it.
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/.venv/bin/python" "$HERE/voice.py" "$@"
