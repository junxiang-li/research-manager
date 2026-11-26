@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   科研项目管理软件
echo   启动后浏览器打开: http://127.0.0.1:8765
echo   关闭服务: 在本窗口按 Ctrl+C
echo ============================================================
python -m pip show flask >nul 2>&1
if errorlevel 1 (
  echo 首次运行，正在安装依赖（flask / pypdf / python-docx）...
  python -m pip install --disable-pip-version-check flask pypdf python-docx
)
python app.py
pause
