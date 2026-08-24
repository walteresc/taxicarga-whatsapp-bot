#!/bin/bash
# Start Django with settings_e2e for E2E testing
cd "$(dirname "$0")"
export DJANGO_SETTINGS_MODULE=config.settings_e2e
python manage.py runserver 0.0.0.0:8001
