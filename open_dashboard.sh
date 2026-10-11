#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/mac_common.sh"
# 열기 전에 수집하려면 아래 줄의 #을 지우세요.
# /bin/bash "$KDASH_ROOT/run_daily.sh"
/usr/bin/open "$KDASH_ROOT/docs/index.html"
