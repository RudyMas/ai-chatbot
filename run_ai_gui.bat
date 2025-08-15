@echo off
cd d:\ai-chatbot
call conda activate ai-chatbot
call uvicorn server.api:app --reload
pause