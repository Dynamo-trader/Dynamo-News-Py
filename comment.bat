@echo off
setlocal enabledelayedexpansion

python bump_version.py

REM Add all modified files
git add .

REM Retrieve modified file names
set "files="
for /f "tokens=*" %%i in ('git diff --name-only --cached') do (
    for %%f in ("%%i") do (
        set "filename=%%~nxf"
        set "files=!files! !filename!"
    )
)

REM Create commit message with modified file names
set "commit_msg=Changes on !files!"

REM Commit changes
git commit -m "!commit_msg!"

REM Push changes
git push

REM Show push analysis
git log -n 5 --pretty=format:"%h - %s (%an, %ar)"

endlocal
