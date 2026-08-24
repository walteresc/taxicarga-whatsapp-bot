#!/bin/bash
# Start Django with settings_test for E2E testing
cd "$(dirname "$0")"
export DJANGO_SETTINGS_MODULE=config.settings_test
python manage.py runserver 0.0.0.0:8001
