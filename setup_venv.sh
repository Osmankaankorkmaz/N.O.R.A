#!/bin/bash
python3 -m venv .venv 2>/dev/null
.venv/bin/pip install -q PyQt5 ruff==0.15.16 pytest pillow psutil requests speechrecognition sounddevice numpy 2>&1|tail -2
