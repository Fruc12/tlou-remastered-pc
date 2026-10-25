@echo off
rem The Last of Us Remastered with the sampling profiler on (the GPU command, draw recording and
rem Vulkan recording threads): a report every 10 s in analysis\tlou\profile-user, read with
rem tools\profile_rank.py. Play to a slow area, stay there about a minute, then close the game.
cd /d "%~dp0"
if exist "analysis\tlou\profile-user" rmdir /s /q "analysis\tlou\profile-user"
mkdir "analysis\tlou\profile-user"
set GOW3_PROFILE=10
set GOW3_THREAD_IDS=1
set GOW3_COMPUTE_WAIT_STATS=1
set GOW3_FAULT_STATS=1
set GOW3_FAULT_TIMES=1
set GOW3_PROFILE_GUEST=NdJobWorkerThread
rem Each page a write fault shared with the GPU (or waited for) is checked once clean: the GPU's
rem copy of the game's bytes against guest memory, and poison left in them ("Share check").
set GOW3_SHARE_CHECK=1
set GOW3_DUMP_DIR=%~dp0analysis\tlou\profile-user
python tools\probe_tlou.py --boot --seconds 0 %*
