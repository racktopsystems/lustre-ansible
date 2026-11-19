#!/bin/sh

usage() {
	echo "usage: $0 <inventory-file>" >&2
	exit 2
}

[ $# -eq 1 ] || usage

inventory=$1
if [ ! -f "$inventory" ]; then
	echo "$0: inventory file '$inventory' does not exist" >&2
	exit 1
fi

passfile=bsradminpass
if [ ! -f "$passfile" ]; then
	echo "$0: become password file '$passfile' does not exist;" \
	    "create it containing the bsradmin password" >&2
	exit 1
fi

# Per-host passwords in the inventory are encrypted with ansible-vault. Read
# the vault password from sensitive/vaultpass when it exists (unless
# ANSIBLE_VAULT_PASSWORD_FILE already names one), otherwise prompt for it
# when the inventory or host_vars hold encrypted values.
vaultfile=sensitive/vaultpass
vaulted='^[^#]*(!vault|\$ANSIBLE_VAULT)'
vault_args=
if [ -n "$ANSIBLE_VAULT_PASSWORD_FILE" ]; then
	:
elif [ -f "$vaultfile" ]; then
	vault_args="--vault-password-file $vaultfile"
elif grep -qE "$vaulted" "$inventory" ||
    { [ -d host_vars ] && grep -rqE "$vaulted" host_vars; }; then
	vault_args=--ask-vault-pass
fi

exec ansible-playbook \
	-u bsradmin \
	--become-password-file "$passfile" \
	$vault_args \
	-v \
	-i "$inventory" \
	bootstrap-keys.yml
