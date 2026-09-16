#!/usr/bin/env bash
# Reconstruye el frontend (Vite build dentro de Docker) y lo despliega en
# static_build/, reiniciando nginx. Correr esto después de CUALQUIER cambio
# en frontend_materio/src/**/*.vue (o cualquier archivo del frontend) — el
# sitio no lee los .vue directamente, sirve el build compilado.
#
# Uso: desde la raíz del repo (taxicarga_whatsapp_bot/)
#   bash deploy_frontend.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "==> 1/4 Compilando el frontend (Docker build)..."
docker build -f Dockerfile.frontend -t taxicarga-frontend-build:latest .

echo "==> 2/4 Extrayendo el build compilado..."
docker rm -f frontend-extract >/dev/null 2>&1 || true
docker create --name frontend-extract taxicarga-frontend-build:latest
rm -rf static_build_new
docker cp frontend-extract:/frontend/dist static_build_new
docker rm frontend-extract >/dev/null

echo "==> 3/4 Reemplazando static_build/..."
rm -rf static_build_old
mv static_build static_build_old
mv static_build_new static_build

echo "==> 4/4 Reiniciando nginx..."
docker restart taxicarga-nginx >/dev/null
sleep 2
docker ps --filter name=taxicarga-nginx --format "    {{.Names}}: {{.Status}}"

rm -rf static_build_old
echo "==> Listo. Cambios en vivo."
