@echo off
REM OpenCode session.start Hook wrapper for Windows.
REM Configure in ~/.opencode/config.json with an absolute path to this file.
setlocal
if "%AGENT_TRIAGE_PROJECT_ROOT%"=="" (
  set "AGENT_TRIAGE_PROJECT_ROOT=%~dp0.."
)
cd /d "%AGENT_TRIAGE_PROJECT_ROOT%\backend"
python -m sop.hook_cli
exit /b %ERRORLEVEL%
