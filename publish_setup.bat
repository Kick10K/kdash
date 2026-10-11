@echo off
chcp 65001 > nul
cd /d "%~dp0"
rem ===== GitHub Pages 첫 업로드 (한 번만 실행) =====
rem 준비: Git 설치, GitHub 에 빈 저장소 생성 (Public)
set /p REPO=GitHub 저장소 주소를 붙여넣으세요 (예: https://github.com/아이디/kdash.git): 
if "%REPO%"=="" goto :eof
if not exist .git git init -b main
git config user.name "kdash"
git config user.email "kdash@users.noreply.github.com"
git add -A
git commit -m "first upload"
git remote remove origin 2> nul
git remote add origin %REPO%
git push -u origin main
echo.
echo 완료되면 GitHub 저장소 Settings - Pages 에서 Branch: main, Folder: /docs 로 저장하세요.
pause
