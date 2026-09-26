#!/bin/sh
set -eu
mkdir -p /radio /data
chown 1000:1000 /radio /data
exec setpriv --reuid=1000 --regid=1000 --init-groups "$@"
