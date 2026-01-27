@echo off
:: set_env.bat
:: Usage: call set_env.bat [ENV] [CONFIG_PATH]
:: When run with CALL, this will set environment variables in the current cmd session.
:: Defaults: ENV=PROD, CONFIG=%USERPROFILE%\.dashboard\config.ini

nSETLOCAL ENABLEDELAYEDEXPANSION

nSET "ENV_NAME=%~1"
SET "CONFIG_PATH=%~2"
nIF "%CONFIG_PATH%"=="" SET "CONFIG_PATH=%USERPROFILE%\.dashboard\config.ini"
IF "%ENV_NAME%"=="" (
  set /p "ENV_NAME=Environment [PROD]: "
  if "%ENV_NAME%"=="" set "ENV_NAME=PROD"
)

nIF NOT EXIST "%CONFIG_PATH%" (
  echo Config file not found: %CONFIG_PATH%
  ENDLOCAL & EXIT /B 1
)

n:: Use PowerShell to parse the INI section and print KEY=VALUE pairs (uppercased keys)
for /f "usebackq delims=" %%L in (`powershell -NoProfile -Command "`n$cfg = Get-Content -Raw -Path \"%CONFIG_PATH%\";`n$sec = '\'['+('%ENV_NAME%')+']\'';`n$regex = '(?ms)\[(?<sec>[^\]]+)\](?<body>.*?)(?=\n\[|\z)';`n[regex]::Matches($cfg,$regex) | ForEach-Object { if ($_.Groups['sec'].Value -ieq '%ENV_NAME%') { $_.Groups['body'].Value -split '\n' | ForEach-Object { if ($_ -match '^[ \t]*([^=;#]+)\s*=\s*(.*)$') { $k=$matches[1].Trim().ToUpper() -replace '[^A-Z0-9_]','_'; $v=$matches[2].Trim(); $v = $v.Trim('"','\'') ; Write-Output ("$k=$v") } } } }"`) do (
  for /f "delims==" %%K in ("%%L") do (
    set "__K=%%K"
    set "__V=%%L"
    set "__V=!__V:*==!"
    :: Set the environment variable in this cmd session
    set "!__K!=!__V!"
    echo Set !__K!=!__V!
  )
)

n:: End, keep variables in calling environment when using CALL (ENDLOCAL would clear them)
ENDLOCAL & (
  for /f "tokens=1* delims==" %%A in ('powershell -NoProfile -Command "`n$cfg = Get-Content -Raw -Path \"%CONFIG_PATH%\";`n$regex = '(?ms)\[(?<sec>[^\]]+)\](?<body>.*?)(?=\n\[|\z)';`n[regex]::Matches($cfg,$regex) | ForEach-Object { if ($_.Groups['sec'].Value -ieq '%ENV_NAME%') { $_.Groups['body'].Value -split '\n' | ForEach-Object { if ($_ -match '^[ \t]*([^=;#]+)\s*=\s*(.*)$') { $k=$matches[1].Trim().ToUpper() -replace '[^A-Z0-9_]','_'; $v=$matches[2].Trim(); $v = $v.Trim('"','\''); Write-Output ("$k=$v") } } } }"') do (
    set "%%A=%%B"
  )
)

necho Done.
EXIT /B 0
