@echo off
REM ============================================================================
REM LAN File-Sharing Platform - Setup & Run Script
REM For Windows systems
REM ============================================================================

setlocal EnableDelayedExpansion

REM Default configuration
set PORT=8000
set MODE=
set SCRIPT_DIR=%~dp0

REM Colors for Windows console
set "RED=[91m"
set "GREEN=[92m"
set "YELLOW=[93m"
set "BLUE=[94m"
set "CYAN=[96m"
set "BOLD=[1m"
set "NC=[0m"

REM ============================================================================
REM Parse Arguments
REM ============================================================================

:parse_args
if "%~1"=="" goto :main
if /i "%~1"=="--docker" (
    set MODE=docker
    shift
    goto :parse_args
)
if /i "%~1"=="--python" (
    set MODE=python
    shift
    goto :parse_args
)
if /i "%~1"=="--port" (
    set PORT=%~2
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--build" (
    call :check_docker
    if !errorlevel!==0 (
        echo %BLUE%[INFO]%NC% Rebuilding Docker image...
        docker build -t fileshare:latest "%SCRIPT_DIR%"
        echo %GREEN%[SUCCESS]%NC% Image rebuilt successfully
    ) else (
        echo %RED%[ERROR]%NC% Docker is not available
    )
    exit /b 0
)
if /i "%~1"=="--help" goto :show_help
if /i "%~1"=="-h" goto :show_help
echo %RED%[ERROR]%NC% Unknown option: %~1
goto :show_help

REM ============================================================================
REM Main Script
REM ============================================================================

:main
call :print_banner

cd /d "%SCRIPT_DIR%"

if "%MODE%"=="docker" (
    call :check_docker
    if !errorlevel!==0 (
        call :run_docker
    ) else (
        echo %RED%[ERROR]%NC% Docker is not available or not running
        exit /b 1
    )
    goto :eof
)

if "%MODE%"=="python" (
    call :check_python
    if !errorlevel!==0 (
        call :run_python
    ) else (
        echo %RED%[ERROR]%NC% Python 3.9+ is required but not found
        exit /b 1
    )
    goto :eof
)

REM Auto-detect mode
echo.
echo %BOLD%^> Detecting available runtime environments...%NC%

set HAS_DOCKER=0
set HAS_PYTHON=0

call :check_docker
if !errorlevel!==0 (
    set HAS_DOCKER=1
    echo %BLUE%[INFO]%NC% Docker is available
)

call :check_python
if !errorlevel!==0 (
    set HAS_PYTHON=1
    echo %BLUE%[INFO]%NC% Python 3.9+ is available
)

if %HAS_DOCKER%==1 if %HAS_PYTHON%==1 (
    REM Both are available - let user choose
    echo.
    echo %BOLD%Both Docker and Python are available. Choose your preferred method:%NC%
    echo.
    echo   1^) Docker  - Containerized deployment ^(recommended for production^)
    echo   2^) Python  - Native deployment ^(faster startup, easier debugging^)
    echo.
    set /p CHOICE="Enter choice [1/2] (default: 1): "
    
    if "!CHOICE!"=="2" (
        echo %BLUE%[INFO]%NC% Using native Python deployment
        call :run_python
    ) else (
        echo %BLUE%[INFO]%NC% Using Docker containerized deployment
        call :run_docker
    )
    goto :eof
)

if %HAS_DOCKER%==1 (
    echo %BLUE%[INFO]%NC% Using Docker containerized deployment
    call :run_docker
    goto :eof
)

if %HAS_PYTHON%==1 (
    echo %BLUE%[INFO]%NC% Using native Python deployment
    call :run_python
    goto :eof
)

echo %RED%[ERROR]%NC% Neither Docker nor Python 3.9+ found!
echo.
echo Please install one of the following:
echo   - Docker: https://docs.docker.com/get-docker/
echo   - Python 3.9+: https://www.python.org/downloads/
exit /b 1

REM ============================================================================
REM Helper Functions
REM ============================================================================

:print_banner
echo.
echo %CYAN%========================================================%NC%
echo %CYAN%          LAN File-Sharing Platform v1.0.0              %NC%
echo %CYAN%========================================================%NC%
echo.
goto :eof

:show_help
echo Usage: %~nx0 [OPTIONS]
echo.
echo Options:
echo   --docker      Force Docker mode
echo   --python      Force Python mode
echo   --port PORT   Set server port (default: 8000)
echo   --build       Rebuild Docker image
echo   --help        Show this help message
echo.
echo Examples:
echo   %~nx0                    # Auto-detect best method
echo   %~nx0 --docker           # Use Docker
echo   %~nx0 --python --port 3000  # Use Python on port 3000
exit /b 0

:check_docker
where docker >nul 2>&1
if errorlevel 1 exit /b 1

docker info >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%[WARNING]%NC% Docker is installed but not running
    exit /b 1
)
exit /b 0

:check_python
where python >nul 2>&1
if errorlevel 1 (
    where python3 >nul 2>&1
    if errorlevel 1 exit /b 1
)
exit /b 0

:get_local_ip
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    for /f "tokens=1" %%b in ("%%a") do (
        set LOCAL_IP=%%b
        goto :eof
    )
)
set LOCAL_IP=localhost
goto :eof

REM ============================================================================
REM Docker Functions
REM ============================================================================

:run_docker
echo.
echo %BOLD%^> Starting with Docker...%NC%

REM Create necessary directories
if not exist "%SCRIPT_DIR%uploads" mkdir "%SCRIPT_DIR%uploads"
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

REM Check if container already exists
docker ps -a --format "{{.Names}}" | findstr /c:"fileshare-server" >nul 2>&1
if not errorlevel 1 (
    echo %BLUE%[INFO]%NC% Stopping existing container...
    docker stop fileshare-server >nul 2>&1
    docker rm fileshare-server >nul 2>&1
)

REM Check if image exists, build if not
docker images --format "{{.Repository}}:{{.Tag}}" | findstr /c:"fileshare:latest" >nul 2>&1
if errorlevel 1 (
    echo %BLUE%[INFO]%NC% Building Docker image...
    docker build -t fileshare:latest "%SCRIPT_DIR%"
) else (
    echo %BLUE%[INFO]%NC% Using existing Docker image
    echo %BLUE%[INFO]%NC% To rebuild, run: docker build -t fileshare:latest .
)

REM Get host IP to pass to container
call :get_local_ip

REM Run container
echo %BLUE%[INFO]%NC% Starting container...
docker run -d ^
    --name fileshare-server ^
    -p %PORT%:8000 ^
    -v "%SCRIPT_DIR%uploads:/app/uploads" ^
    -e SERVER_PORT=8000 ^
    -e MAX_FILE_SIZE=536870912 ^
    -e HOST_IP=%LOCAL_IP% ^
    --restart unless-stopped ^
    fileshare:latest

REM Wait for service to start
echo %BLUE%[INFO]%NC% Waiting for service to start...
set attempts=0
:docker_wait_loop
if %attempts% geq 30 goto :docker_timeout
timeout /t 1 /nobreak >nul
curl -s "http://localhost:%PORT%/health" >nul 2>&1
if errorlevel 1 (
    set /a attempts+=1
    goto :docker_wait_loop
)

call :get_local_ip

echo.
echo %GREEN%[SUCCESS]%NC% Server is running!
echo.
echo %CYAN%========================================================%NC%
echo   %GREEN%Local Access:%NC%     http://localhost:%PORT%
echo   %GREEN%Network Access:%NC%   http://%LOCAL_IP%:%PORT%
echo %CYAN%--------------------------------------------------------%NC%
echo   %YELLOW%Commands:%NC%
echo     Stop:    docker stop fileshare-server
echo     Logs:    docker logs -f fileshare-server
echo     Restart: docker restart fileshare-server
echo %CYAN%========================================================%NC%
echo.
goto :eof

:docker_timeout
echo %RED%[ERROR]%NC% Service failed to start. Check logs with: docker logs fileshare-server
exit /b 1

REM ============================================================================
REM Python Functions
REM ============================================================================

:run_python
echo.
echo %BOLD%^> Starting with Python...%NC%

REM Create necessary directories
if not exist "%SCRIPT_DIR%uploads" mkdir "%SCRIPT_DIR%uploads"
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

REM Setup virtual environment
set VENV_DIR=%SCRIPT_DIR%.venv

if not exist "%VENV_DIR%" (
    echo %BLUE%[INFO]%NC% Creating virtual environment...
    python -m venv "%VENV_DIR%"
)

echo %BLUE%[INFO]%NC% Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"

echo %BLUE%[INFO]%NC% Installing dependencies...
pip install --upgrade pip -q
pip install -r "%SCRIPT_DIR%requirements.txt" -q

call :get_local_ip

echo.
echo %GREEN%[SUCCESS]%NC% Starting server...
echo.
echo %CYAN%========================================================%NC%
echo   %GREEN%Local Access:%NC%     http://localhost:%PORT%
echo   %GREEN%Network Access:%NC%   http://%LOCAL_IP%:%PORT%
echo %CYAN%--------------------------------------------------------%NC%
echo   %YELLOW%Press Ctrl+C to stop the server%NC%
echo %CYAN%========================================================%NC%
echo.

REM Run the server
cd /d "%SCRIPT_DIR%"
set SERVER_PORT=%PORT%
set SERVER_HOST=0.0.0.0
python app.py

goto :eof

