@echo off
setlocal
cd /d "%~dp0" || goto :error
title Tarla Pusulasi - EXE olustur
set "TARLA_PY=py -3"
py -3 -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
if errorlevel 1 set "TARLA_PY=python"
%TARLA_PY% -c "import sys; assert sys.version_info >= (3,10), 'Python 3.10 veya ustu gerekli'"
if errorlevel 1 goto :error
for %%F in (build_exe.py TarlaPusulasi.spec tarla_masaustu.py tarla_toprak.py tarla_verim.py tarla_pencere.py requirements.txt tarla_pusulasi.ico tarla_pusulasi.png tarla_ayarlar.py tarla_dil.py tarla_kayip.py tarla_gorunum.py) do (
 if not exist "%%F" (
  echo Eksik dosya: %%F
  echo ZIP'in tamamini yeni bir klasore cikarin.
  goto :error
 )
)
%TARLA_PY% -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error
%TARLA_PY% -c "import tarla_masaustu, tarla_toprak, tarla_verim, tarla_pencere; import webview, serial; print('Modul kontrolu tamam.')"
if errorlevel 1 goto :error
%TARLA_PY% build_exe.py
if errorlevel 1 goto :error
pause
exit /b 0
:error
echo.
echo EXE olusturulamadi. Yukaridaki hata mesajini paylasin.
pause
exit /b 1
