#!/bin/bash
# Mac 실행 스크립트의 공통 경로와 Python 선택.
KDASH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
cd "$KDASH_ROOT"

kdash_python() {
    local candidate
    for candidate in "$KDASH_ROOT/.venv/bin/python" python3.11 python3.12 python3.13 python3.14 python3.10 python3; do
        if command -v "$candidate" >/dev/null 2>&1 &&
            "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            command -v "$candidate"
            return 0
        fi
    done
    echo 'Python 3.10 이상이 필요합니다. 설치 후 setup_mac.sh를 실행하세요.' >&2
    return 1
}

kdash_ready() {
    if [[ ! -x "$KDASH_ROOT/.venv/bin/python" ]]; then
        echo '먼저 bash setup_mac.sh를 실행하세요.' >&2
        return 1
    fi
    KDASH_PYTHON="$KDASH_ROOT/.venv/bin/python"
    if ! "$KDASH_PYTHON" -c 'import pandas, numpy, requests, pykrx, FinanceDataReader' >/dev/null 2>&1; then
        echo '필요한 Python 패키지가 준비되지 않았습니다. bash setup_mac.sh를 다시 실행하세요.' >&2
        return 1
    fi
}

kdash_settings() {
    if [[ ! -f "$KDASH_ROOT/settings.sh" ]]; then
        echo 'settings.example.sh를 settings.sh로 복사하고 KRX 계정을 입력하세요.' >&2
        return 1
    fi
    source "$KDASH_ROOT/settings.sh"
}
