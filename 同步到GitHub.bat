@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   GitHub Sync  /  GitHub 同步脚本
echo ============================================================
echo.
echo Remote is read from local .git/config (owner/repo not shown here).
echo 远程地址从本地 .git/config 读取，本脚本不显示账号与仓库名。
echo.
echo Make sure you are signed in to GitHub (Git Credential Manager
echo will prompt, or use a Personal Access Token as password).
echo 请确保已登录 GitHub（凭据管理器会弹窗，或用 Token 作为密码）。
echo.
echo Press any key to continue, or close this window to cancel...
echo 按任意键继续，关闭窗口则取消。
pause >nul

echo.
echo [1/3] Fetching remote... 正在获取远程...
git fetch origin
if errorlevel 1 goto :fetchfail

echo.
echo [2/3] Current status... 当前状态:
git status --short --branch

echo.
echo [3/3] Pushing (force, history was sanitized)... 正在推送（强制，历史已脱敏重写）...
git push -u --force origin main
if errorlevel 1 goto :pushfail

echo.
echo [OK] Source code synced. 源码已同步成功。
echo.
pause
exit /b 0

:fetchfail
echo.
echo [FAIL] Cannot reach remote. 无法连接远程，请检查:
echo   - Network / proxy 网络或代理
echo   - Remote URL: git remote -v 远程地址
echo   - GitHub login 登录状态
echo.
pause
exit /b 1

:pushfail
echo.
echo [FAIL] Push rejected. 推送被拒绝。If remote main has its own initial
echo commit (e.g. an auto-created README), merge once with:
echo 若远程 main 自带初始提交（如自动生成的 README），先执行一次：
echo.
echo   git pull origin main --allow-unrelated-histories
echo   git push -u origin main
echo.
echo If permission denied, sign in again or check repo access.
echo 若为权限问题，请重新登录或确认仓库访问权限。
echo.
pause
exit /b 1
