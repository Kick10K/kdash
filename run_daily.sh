#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/mac_common.sh"
kdash_ready
kdash_settings
KDASH_CAN_PUBLISH=1
for KDASH_ARG in "$@"; do
    case "$KDASH_ARG" in
        --help|-h|--sample|--debug-funds) KDASH_CAN_PUBLISH=0 ;;
    esac
done
"$KDASH_PYTHON" -u "$KDASH_ROOT/collector/run.py" "$@"
if [[ "${PUBLISH:-0}" == '1' && "$KDASH_CAN_PUBLISH" == '1' ]]; then
    if [[ ! -d "$KDASH_ROOT/.git" ]]; then
        echo 'GitHub 저장소 연결이 필요합니다. bash publish_setup.sh를 먼저 실행하세요.' >&2
        exit 1
    fi
    # 일일 업로드에는 대시보드와 시장 데이터만 포함합니다.
    git add -- data docs sectors
    if ! git diff --cached --quiet -- data docs sectors; then
        git commit -m "data $(TZ=Asia/Seoul date +%F)" --only -- data docs sectors
    fi
    git push
fi
