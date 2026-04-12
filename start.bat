@echo off
title Book Sales - Local Dev Server
echo ========================================
echo  Book Sales Prediction - Local Dev
echo  http://localhost:8000
echo ========================================
echo.
echo Starting API server...
python db/api_server.py
pause
