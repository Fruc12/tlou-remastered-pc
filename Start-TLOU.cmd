@echo off
rem The Last of Us Remastered (CUSA00552) - prepares and starts the game with no time limit.
rem The game folder is ..\CUSA00552 (update in ..\CUSA00552-patch); the log is analysis\tlou\boot.log.
cd /d "%~dp0"
python tools\probe_tlou.py --boot --seconds 0 %*
