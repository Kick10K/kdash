#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/mac_common.sh"
kdash_ready
kdash_settings
# --write-only는 등록 없이 설정 파일만 생성하므로 내용을 확인할 때 사용합니다.
KDASH_PLIST="$KDASH_ROOT/work/com.kdash.daily.plist"
KDASH_WRITE_ONLY=0
if [[ "${1:-}" == '--write-only' ]]; then
    KDASH_WRITE_ONLY=1
else
    KDASH_PLIST="$HOME/Library/LaunchAgents/com.kdash.daily.plist"
fi
mkdir -p "$(dirname "$KDASH_PLIST")" "$KDASH_ROOT/data"
"$KDASH_PYTHON" - "$KDASH_ROOT" "$KDASH_PLIST" <<'PY'
import pathlib
import plistlib
import sys

root = pathlib.Path(sys.argv[1])
plist = {
    'Label': 'com.kdash.daily',
    'ProgramArguments': ['/bin/bash', str(root / 'run_daily.sh')],
    'WorkingDirectory': str(root),
    'StartCalendarInterval': [
        {'Weekday': day, 'Hour': 18, 'Minute': 40} for day in range(1, 6)
    ],
    'StandardOutPath': str(root / 'data' / 'launchd.log'),
    'StandardErrorPath': str(root / 'data' / 'launchd_error.log'),
    'EnvironmentVariables': {'PYTHONUNBUFFERED': '1'},
    'ProcessType': 'Background',
}
pathlib.Path(sys.argv[2]).write_bytes(plistlib.dumps(plist))
PY
/usr/bin/plutil -lint "$KDASH_PLIST"
if [[ "$KDASH_WRITE_ONLY" == '1' ]]; then
    echo "설정 파일만 생성했습니다: $KDASH_PLIST (자동 실행 미등록)"
    exit 0
fi
KDASH_DOMAIN="gui/$(id -u)"
launchctl bootout "$KDASH_DOMAIN/com.kdash.daily" >/dev/null 2>&1 || true
launchctl bootstrap "$KDASH_DOMAIN" "$KDASH_PLIST"
launchctl enable "$KDASH_DOMAIN/com.kdash.daily"
echo '평일 18:40 자동 실행 등록 완료 (Mac에 설정된 시간대 기준).'
echo '잠자기 중 놓친 실행은 깨어난 뒤 처리합니다. 전원이 꺼져 있거나 로그아웃한 동안은 실행되지 않습니다.'
echo '해제: bash unregister_task.sh'
