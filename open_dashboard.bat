@echo off
chcp 65001 > nul
cd /d "%~dp0"
rem 대시보드 열기. 열 때마다 최신 데이터를 먼저 받으려면 아래 줄 앞의 rem 을 지우세요.
rem call run_daily.bat
start "" "docs\index.html"
