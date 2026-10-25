#!/usr/bin/env bash
# Breaks (or un-breaks) the database's password changes, to practise failure.
#   tools/fault.sh down     password changes fail (DB unreachable from the rotator)
#   tools/fault.sh ignore   password changes say OK but don't happen
#   tools/fault.sh none     back to normal
curl -s -XPOST "${DB_URL:-http://localhost:8034}/admin/fault" -d "{\"mode\": \"${1:-none}\"}"; echo
