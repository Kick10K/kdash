@echo off
chcp 65001 > nul
rem ===== 평일 18:40 자동 실행 등록 (한 번만 실행) =====
rem PC가 꺼져/잠자기 중이었으면 켜진 직후 바로 실행합니다.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$a=New-ScheduledTaskAction -Execute '%~dp0run_daily.bat' -WorkingDirectory '%~dp0'; $t=New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 18:40; $s=New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2); Register-ScheduledTask -TaskName 'kdash_daily' -Description 'kdash daily collect' -Action $a -Trigger $t -Settings $s -Force | Out-Null; Write-Host 'OK: kdash_daily registered (Mon-Fri 18:40)'"
echo.
echo 등록을 지우려면: schtasks /delete /tn kdash_daily /f
pause
