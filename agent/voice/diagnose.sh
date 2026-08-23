#!/bin/bash
# Lugalay's diagnostics. Wraps the venv, because the tools need sounddevice,
# faster-whisper and friends, and a bare `python3` has none of them.
#
#   ./diagnose.sh mic     is the microphone actually delivering audio?
#   ./diagnose.sh lang     record your voice, show how the router sees it
#   ./diagnose.sh tune     score Burmese decoding against a known sentence
#   ./diagnose.sh keys     is macOS letting us see the keyboard?
#   ./diagnose.sh check    every dependency, model, the mic and the brain
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/.venv/bin/python"
case "${1:-check}" in
  mic)   exec "$PY" "$HERE/mictest.py" ;;
  lang)  exec "$PY" "$HERE/langtest.py" ;;
  tune)  exec "$PY" "$HERE/tune_my.py" ;;
  keys)  exec "$PY" "$HERE/keytest.py" ;;
  check) exec "$PY" "$HERE/voice.py" --check ;;
  *) echo "usage: $(basename "$0") [check|mic|lang|tune|keys]" >&2; exit 1 ;;
esac
