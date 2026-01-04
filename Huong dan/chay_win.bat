@echo off
gunicorn app:app -k gevent -w 1 -b 0.0.0.0:5000 --timeout 120