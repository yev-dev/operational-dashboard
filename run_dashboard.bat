@echo off
REM run_dashboard.bat
REM Interactive helper to manage conda envs and run the Streamlit dashboard.

setlocal ENABLEDELAYEDEXPANSION
set BASE_DIR=%~dp0
set DEFAULT_ENV=qf
set REQS=%BASE_DIR%requirements.txt
if exist "%BASE_DIR%dashboard\requirements.txt" set REQS=%BASE_DIR%dashboard\requirements.txt
set ENV_YML=%BASE_DIR%environment.yml

where conda >nul 2>&1
if errorlevel 1 (
  echo Error: 'conda' not found on PATH. Please install Anaconda/Miniconda or add conda to PATH.
  exit /b 1
)

:menu
echo.
echo Select an action:
echo   1) List conda environments
echo   2) Check a conda env for missing packages (streamlit or requirements.txt)
echo   3) Install requirements.txt into a conda env
echo   4) Install specific Python packages into a conda env
echo   5) Create conda env from environment.yml
echo   6) Run the dashboard in a conda env
echo   7) Quit
set /p CHOICE=Choice [1-7]: 
if "%CHOICE%"=="1" goto :list_envs
if "%CHOICE%"=="2" goto :check_env_packages
if "%CHOICE%"=="3" goto :install_reqs
if "%CHOICE%"=="4" goto :install_pkgs
if "%CHOICE%"=="5" goto :create_env
if "%CHOICE%"=="6" goto :run
if "%CHOICE%"=="7" goto :quit
echo Invalid choice
goto :menu

:list_envs
conda env list
goto :menu

:check_env_packages
set /p CONDA_ENV=Conda environment name to check [%DEFAULT_ENV%]: 
if "%CONDA_ENV%"=="" set CONDA_ENV=%DEFAULT_ENV%
echo Checking for streamlit in %CONDA_ENV%...
conda run -n %CONDA_ENV% python -c "import importlib.util; print('missing' if importlib.util.find_spec('streamlit') is None else 'ok')" > "%TEMP%\_dash_check.txt" 2>&1
for /f "usebackq delims=" %%L in ("%TEMP%\_dash_check.txt") do set CHECK=%%L
if "%CHECK%"=="missing" (
  echo Streamlit missing in %CONDA_ENV%
  if exist "%REQS%" (
    set /p ANS=Install requirements from %REQS% into %CONDA_ENV% now? [Y/n]: 
    if /i "%ANS%"=="Y" goto :install_reqs
    if "%ANS%"=="" goto :install_reqs
  ) else (
    echo No requirements file found. You can run: conda run -n %CONDA_ENV% pip install streamlit
  )
)
goto :menu

:install_reqs
set /p CONDA_ENV=Conda environment name to use [%DEFAULT_ENV%]: 
if "%CONDA_ENV%"=="" set CONDA_ENV=%DEFAULT_ENV%
if not exist "%REQS%" (
  echo Requirements file not found: %REQS%
  goto :menu
) else (
  conda run -n %CONDA_ENV% pip install -r "%REQS%"
)
goto :menu

:install_pkgs
set /p CONDA_ENV=Conda environment name to use [%DEFAULT_ENV%]: 
if "%CONDA_ENV%"=="" set CONDA_ENV=%DEFAULT_ENV%
set /p PKGS=Enter package(s) to install (space-separated): 
if "%PKGS%"=="" (
  echo No packages provided
  goto :menu
)
conda run -n %CONDA_ENV% pip install %PKGS%
goto :menu

:create_env
set /p CONDA_ENV=Conda environment name to create [%DEFAULT_ENV%]: 
if "%CONDA_ENV%"=="" set CONDA_ENV=%DEFAULT_ENV%
if not exist "%ENV_YML%" (
  echo No environment.yml found at %ENV_YML%
  goto :menu
) else (
  conda env create -f "%ENV_YML%" -n %CONDA_ENV%
)
goto :menu

:run
set /p CONDA_ENV=Conda environment name to run dashboard in [%DEFAULT_ENV%]: 
if "%CONDA_ENV%"=="" set CONDA_ENV=%DEFAULT_ENV%
echo Launching Streamlit in env '%CONDA_ENV%'
cd /d "%BASE_DIR%dashboard"
conda run -n %CONDA_ENV% streamlit run dashboard.py --server.fileWatcherType=watchdog --server.runOnSave=true
goto :menu

:quit
echo Bye
endlocal
exit /b 0
