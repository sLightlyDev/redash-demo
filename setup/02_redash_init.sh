#!/bin/sh
# Runs once to initialize Redash DB schema and create the demo admin user.
# Called by the 'setup' service in docker-compose.demo.yml.
set -e

echo "==> Waiting for postgres..."
until python -c "import psycopg2; psycopg2.connect(host='postgres',user='redash',password='redash_pass',dbname='redash')" 2>/dev/null; do
  echo "  postgres not ready, retrying..."
  sleep 2
done

echo "==> Creating Redash DB tables..."
/app/manage.py database create_tables

echo "==> Creating admin user (admin@demo.com / demo1234)..."
/app/manage.py users create_root admin@demo.com Admin \
  --org default \
  --password demo1234 \
  2>&1 | grep -v "already exists" || true

echo "==> Setup complete."
