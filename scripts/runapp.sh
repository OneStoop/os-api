#!/bin/sh
gunicorn --name "OS API" --chdir /app/src --bind 0.0.0.0:$SERVER_PORT app:app gevent --worker-connections 1000 --workers 4 --log-file appgunicorn.log


