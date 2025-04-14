#!/usr/bin/env bash
# set -x

#
# is_eula_accepted: returns 0 if EULA has been previously accepted and
# the acceptance recorded. It returns 1 otherwise.
#
function is_eula_accepted {
    [ "$(sqlite3 /etc/brickstor/repo.db 'select * from system WHERE namespace = "eula";')" != "" ]
}

#
# is_already_installed: returns 0 if the supplied key is present in the list of all supplied keys. It returns 0 otherwise.
#
function is_already_installed {
    local key="$1"
    local keys="$2"

    for installed_key in ${keys[@]}; do
        if [ "${key}" == "${installed_key}" ]; then
            return 0
        fi
    done
    echo "DEBUG: ${key} is not installed" >&2
    return 1
}

exit_code=0

USER="${USER:-$1}"
PASSWORD="${PASSWORD:-$2}"
OREG_FILENAME="${OREG_FILENAME:-$3}"
OREG_LIC_KEYS_FILENAME="${OREG_LIC_KEYS_FILENAME:-$4}"
EULA_ACCEPT_NAME="${EULA_ACCEPT_NAME:-$5}"
USERPASS="${USER}:${PASSWORD}"

auth=$(curl -fslS -X POST -H 'X-User-Agent: myRackHttp' -u "${USERPASS}" -k https://localhost:8443/login) || exit 1

AUTHTOK=$(jq -r '.token' <<<  "${auth}")

if [ "${AUTHTOK}" == "null" ]; then
    echo "ERROR: problem with authenticating ${USER}" >&2
    exit 1
fi

# If the EULA has not yet been accepted we need to make sure that the EULA is
# first accepted.
if ! is_eula_accepted; then
    # First, we need to obtain the hash value for the EULA.
    eula=$(curl -fslS \
        -H "Authorization: Bearer ${AUTHTOK}" \
        -H "X-User-Agent: myRackHttp" \
        -k https://localhost:8443/internal/v1/init/eula) || exit 1
    eula_hash=$(jq -r '.Data.Hash' <<< "${eula}")

    # POST to the same endpoint with the hash obtained in the previous step and
    # the name of the entity accepting the EULA.
    accept_eula=$(curl -fslS \
        -X POST \
        -H "Content-type: application/json" \
        -H "Authorization: Bearer ${AUTHTOK}" \
        -H "X-User-Agent: myRackHttp" \
        -k https://localhost:8443/internal/v1/init/eula \
        -d "{\"Name\": \"${EULA_ACCEPT_NAME}\", \"Hash\": \"${eula_hash}\" }") || \
        {
            echo "${accept_eula}";
            exit 1;
        }
fi

# We only dump this output when the command fails.
oreg=$(curl -fslS \
    -X POST \
    -H "Authorization: Bearer ${AUTHTOK}" \
    -H "X-User-Agent: myRackHttp" \
    -k https://localhost:8443/internal/v1/init/register_offline \
    -F "filedata=@${OREG_FILENAME}") || \
    {
        echo "${oreg}";
        exit 1;
    }

# Obtain all already installed keys
# This is kind of terrible, but we don't have much better options. We have a
# problem seemingly getting all keys via the API and this command does not
# provide structured output.
installed_keys=$(/usr/racktop/sbin/licadm s -k | cut -b29-86 | tail -n +2)

while read -r key; do
    if ! is_already_installed "${key}" "${installed_keys[@]}"; then
        err=$(curl -slS \
          -X PUT \
          -H "Content-type: application/json" \
          -H "X-User-Agent: myRackHttp" \
          -H "Authorization: Bearer ${AUTHTOK}" \
          -k https://localhost:8443/internal/v1/license \
          -d "{\"Key\": \"${key}\"}" | jq -r '.Data.Error')
        # The duplicate key error should not be possible since we are checking
        # against already installed keys and skipping over those. But, we are
        # just being extra conservative here.
        if [ "${err}" != "duplicate key" ] && [ "${err}" != "" ]; then
          exit_code=1
          echo "ERROR: ${err}" >&2
        fi
    fi
done < "${OREG_LIC_KEYS_FILENAME}"

exit "${exit_code}"
