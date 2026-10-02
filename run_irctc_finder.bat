@echo off
echo Installing required packages...
pip install -r requirements.txt

echo.
echo Starting IRCTC Green Seat Finder...
echo Open your browser and go to: http://localhost:5000
echo.

python app.py

pause
