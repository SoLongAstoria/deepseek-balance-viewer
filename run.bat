@echo off
REM 一键启动（Windows）。优先用 pythonw 隐藏控制台窗口，缺失则退回 python。
cd /d "%~dp0"
where pythonw >nul 2>nul && set PY=pythonw || set PY=python
if not defined PY (echo 未找到 Python，请先安装 Python 3.8+ 并勾选 "Add to PATH" & pause & exit /b 1)
"%PY%" main.py
if errorlevel 1 (echo 启动失败，请检查 Python 环境与依赖 & pause)
