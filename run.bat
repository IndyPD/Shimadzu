@echo off
cd /d "%~dp0"

:: Conda 환경 활성화
echo Activating Conda environment 'NRMK'...
call C:\ProgramData\anaconda3\Scripts\activate.bat
call conda activate NRMK

:: 디버깅을 위해 화면에 출력하고 종료 시 대기하도록 수정
echo Starting Shimadzu Logic...
python run.py --project=shimadzu_logic

:: 에러 발생 시 창이 바로 꺼지지 않게 함
echo.
echo Program exited.
pause