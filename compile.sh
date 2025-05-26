#!/usr/bin/zsh
echo "This compile file uses the uv tool. You can find and install uv here:
https://github.com/astral-sh/uv" 

uv venv server-venv
source server-venv/bin/activate
uv pip install -r requirements.txt
