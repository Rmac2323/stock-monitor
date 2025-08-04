@echo off
cd /d "%~dp0"
start "Stock Monitor - AAPL" cmd /k "venv\Scripts\activate && python main.py"