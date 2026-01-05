@echo off
echo Initializing Conda and activating NRMK environment...
call C:\ProgramData\anaconda3\Scripts\activate.bat
call conda activate NRMK

echo Starting the server...
python run.py

pause