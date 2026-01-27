@echo off

:: "ShimadzuLogic" 제목을 가진 창(프로세스)을 찾아 강제 종료 (/F) 및 하위 프로세스 포함 종료 (/T)
taskkill /FI "WINDOWTITLE eq ShimadzuLogic" /T /F