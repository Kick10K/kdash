#!/bin/bash
set -euo pipefail
source "$(dirname "$0")/mac_common.sh"
read -r -p 'GitHub 저장소 주소 (예: https://github.com/아이디/kdash.git): ' KDASH_REPO
[[ -n "$KDASH_REPO" ]] || exit 0
if [[ "$KDASH_REPO" != https://github.com/* && "$KDASH_REPO" != git@github.com:* ]]; then
    echo 'https://github.com/ 또는 git@github.com: 형식의 주소를 입력하세요.' >&2
    exit 1
fi
if [[ ! -d "$KDASH_ROOT/.git" ]]; then
    git init -b main
fi
if [[ "$(git branch --show-current)" != 'main' ]]; then
    echo '현재 브랜치가 main이 아닙니다. main 브랜치에서 다시 실행하세요.' >&2
    exit 1
fi
if [[ -z "$(git config user.name || true)" ]]; then
    git config user.name 'kdash'
fi
if [[ -z "$(git config user.email || true)" ]]; then
    git config user.email 'kdash@users.noreply.github.com'
fi
if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$KDASH_REPO"
else
    git remote add origin "$KDASH_REPO"
fi
git add -A
if ! git diff --cached --quiet; then
    git commit -m 'Mac setup and dashboard'
fi
git push -u origin main
echo 'GitHub Settings → Pages → Branch: main, Folder: /docs로 저장하세요.'
echo '이후 settings.sh에서 export PUBLISH=1로 바꾸면 일일 수집 뒤 자동 업로드합니다.'
