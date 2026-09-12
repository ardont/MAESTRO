#!/bin/sh
set -eu
# Kafka worker is the main process: signals and its exit status reach Docker.
exec "$@"
