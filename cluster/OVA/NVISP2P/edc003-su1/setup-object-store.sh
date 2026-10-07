#!/bin/sh
set -eu

mc --insecure mb --ignore-existing nvis/nvis-p2p-artifacts
mc --insecure admin policy create nvis nvis-p2p-import /policies/dfstore-policy.json
mc --insecure admin policy create nvis nvis-p2p-readonly /policies/dfstore-readonly-policy.json

import_secret=$(cat /secrets/dfstore-import-password)
readonly_secret=$(cat /secrets/dfstore-readonly-password)
mc --insecure admin user add nvis nvis-p2p-import "$import_secret"
mc --insecure admin user add nvis nvis-p2p-readonly "$readonly_secret"
mc --insecure admin policy attach nvis nvis-p2p-import --user nvis-p2p-import
mc --insecure admin policy attach nvis nvis-p2p-readonly --user nvis-p2p-readonly
unset import_secret readonly_secret

mc --insecure stat nvis/nvis-p2p-artifacts
mc --insecure admin user info nvis nvis-p2p-import
mc --insecure admin user info nvis nvis-p2p-readonly
