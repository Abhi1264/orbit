#!/bin/sh
set -e

# Only the API container owns migrations; the worker and seed containers wait
# for the schema to exist instead of racing to create it.
case "$1" in
  uvicorn)
    alembic upgrade head
    ;;
esac

exec "$@"
