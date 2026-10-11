#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/mac_common.sh"
KDASH_BASE_PYTHON="$(kdash_python)"
if [[ ! -x "$KDASH_ROOT/.venv/bin/python" ]]; then
    "$KDASH_BASE_PYTHON" -m venv "$KDASH_ROOT/.venv"
fi
"$KDASH_ROOT/.venv/bin/python" -m pip install -r "$KDASH_ROOT/requirements.txt"
if [[ ! -f "$KDASH_ROOT/settings.sh" ]]; then
    cp "$KDASH_ROOT/settings.example.sh" "$KDASH_ROOT/settings.sh"
    echo 'settings.sh에 KRX 계정을 입력하세요.'
fi
chmod 600 "$KDASH_ROOT/settings.sh"
kdash_ready
echo 'Mac 실행 준비 완료. 수집: bash run_daily.sh / 화면 열기: bash open_dashboard.sh'
