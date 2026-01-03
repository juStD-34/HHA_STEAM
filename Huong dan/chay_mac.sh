#!/bin/sh
set -e
gunicorn app:app -k eventlet -w 1 -b 0.0.0.0:5000 --timeout 120
