#!/usr/bin/env bash
# This script exists because with version 23.6 of BSR SP-L there is not an easy
# command-line mechanism for obtaining the registration code.
# Ensure that this script is executable and run it on each node which must be
# registered. This is a one-time process. Once you have been able to download
# the oreg files, rename them to <hostname>.oreg, matching the hostname of the machine to which the given offline registration file belongs and place them under `inputs/registration`.
BASE_ADDR=https://localhost:8443
USERPASS=${USERNAME}:${PASSWORD} auth="$(curl -fslS -X POST -H 'X-User-Agent: myRackHttp' -u "${USERPASS}" -k ${BASE_ADDR}/login)"

AUTHTOK="$(jq -r '.token' <<< "${auth}")"

curl -fslS \
    -X POST \
    -H 'X-User-Agent: myRackHttp' \
    -H "Authorization: Bearer ${AUTHTOK}" \
    -k \
    ${BASE_ADDR}/internal/v1/init/offline_key \
    | jq -r '.Data.RegistrationCode'
