@echo off
rem Build PkgFree.exe (GUI) and pkgfree-cli.exe (riga di comando) in dist\
rem Richiede Python 3.10+ installato e nel PATH.
setlocal
python -m venv .venv || goto :error
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip || goto :error
pip install -r requirements.txt pyinstaller || goto :error
python -m unittest discover -s tests || goto :error
pyinstaller --noconfirm --onefile --windowed --name PkgFree pkgfree_gui.py || goto :error
pyinstaller --noconfirm --onefile --console --name pkgfree-cli pkgfree_cli.py || goto :error
echo.
echo Fatto: dist\PkgFree.exe e dist\pkgfree-cli.exe
exit /b 0
:error
echo Build fallita.
exit /b 1
