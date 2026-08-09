#!/bin/bash
python bot.py &
gunicorn app:app
