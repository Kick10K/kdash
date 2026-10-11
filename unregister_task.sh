#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/mac_common.sh"
launchctl bootout "gui/$(id -u)/com.kdash.daily" >/dev/null 2>&1 || true
rm -f "$HOME/Library/LaunchAgents/com.kdash.daily.plist"
echo 'kdash 자동 실행 등록을 해제했습니다.'
