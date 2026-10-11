@echo off
chcp 65001 > nul
cd /d "%~dp0"
rem ===== 매일 수집 + 계산 (+ 텔레그램 알림, + GitHub 업로드) =====
rem 계정과 옵션은 settings.bat 에 적습니다.
call settings.bat
python collector\run.py
if "%PUBLISH%"=="1" (
  git add -A
  git commit -m "data %date%" > nul
  git push
)
