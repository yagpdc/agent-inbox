@echo off
REM Sobe o Inbox Agent e abre o painel. Fechar esta janela desliga o servidor.
cd /d "%~dp0"
start "" http://localhost:8787/
python -m servidor
