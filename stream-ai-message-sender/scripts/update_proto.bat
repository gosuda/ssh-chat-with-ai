@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
rem Remove trailing backslash if present
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PROJECT_ROOT=%SCRIPT_DIR%\.."
for %%i in ("%PROJECT_ROOT%") do set "PROJECT_ROOT=%%~fi"
set "SOURCE_PROTO=%PROJECT_ROOT%\..\ssh-chat\proto\middleware.proto"
set "TARGET_PROTO=%PROJECT_ROOT%\proto\middleware.proto"

if not exist "%SOURCE_PROTO%" (
  echo Source proto not found: %SOURCE_PROTO%
  exit /b 1
)

copy /Y "%SOURCE_PROTO%" "%TARGET_PROTO%" >nul
if errorlevel 1 (
  echo Failed to copy proto file.
  exit /b 1
)

pushd "%PROJECT_ROOT%\proto"
set "PY_CMD="
where uv >nul 2>nul
if %errorlevel%==0 set "PY_CMD=uv run python"
if not defined PY_CMD (
  where python3 >nul 2>nul
  if %errorlevel%==0 set "PY_CMD=python3"
)
if not defined PY_CMD (
  where python >nul 2>nul
  if %errorlevel%==0 set "PY_CMD=python"
)
if not defined PY_CMD (
  where py >nul 2>nul
  if %errorlevel%==0 set "PY_CMD=py -3"
)
if not defined PY_CMD (
  echo No suitable Python interpreter found. Install Python.
  popd
  exit /b 1
)

call %PY_CMD% -m grpc_tools.protoc --python_out=. --grpc_python_out=. --proto_path=. middleware.proto
if errorlevel 1 (
  echo Failed to run protoc.
  popd
  exit /b 1
)

popd

call %PY_CMD% "%SCRIPT_DIR%\fix_proto_import.py"
if errorlevel 1 (
  echo Failed to patch middleware_pb2_grpc.py import.
  exit /b %ERRORLEVEL%
)

echo Updated proto and regenerated Python gRPC stubs.
endlocal
