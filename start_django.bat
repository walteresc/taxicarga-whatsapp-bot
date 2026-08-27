@echo off
cd /d "d:/DESARROLLO_IA/Proyecto_taxi_carga/Taxi_carga_bot/taxicarga_whatsapp_bot"
python manage.py runserver 0.0.0.0:8001 --noreload > django_restart.log 2>&1
