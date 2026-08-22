@echo off
pip install pyinstaller
pip install -r requirements.txt
call build_native.bat
python scripts\download_punctuation_model.py
python scripts\generate_icon.py
pyinstaller Dictate.spec --noconfirm
copy /Y config.json dist\config.json >nul 2>&1
if exist dictate_native.dll copy /Y dictate_native.dll dist\dictate_native.dll >nul 2>&1
echo.
echo Build complete. Executable is in dist\Dictate.exe
echo Optional: edit dist\config.json for settings.
