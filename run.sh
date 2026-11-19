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

repodir=$(cd "$(dirname "$0")" && pwd -P)

# fapolicyd on a hardened control node lets nothing open an untrusted Python
# file, and ansible-playbook must read this repository's own plugins
# (library/, filter_plugins/, test_plugins/). Rebuild the repository's
# fapolicyd trust file from the plugins' current contents on every run, so
# added, edited and removed plugins are all accounted for, then reload it.
trust_name=lustre-ansible

refresh_fapolicyd_trust() {
	systemctl is-active --quiet fapolicyd 2>/dev/null || return 0

	plugins=$(find "$repodir/library" "$repodir/filter_plugins" \
	    "$repodir/test_plugins" -type f -name '*.py' 2>/dev/null | sort)
	[ -n "$plugins" ] || return 0

	# One plugin path per line; split on newlines only.
	oldifs=$IFS
	IFS='
'
	echo "$0: adding $(echo "$plugins" | wc -l) plugin files to the" \
	    "fapolicyd trust database"
	if ! sudo -S -p '' sh -c '
		set -e
		name=$1
		shift
		rm -f "/etc/fapolicyd/trust.d/$name"
		for f; do
			fapolicyd-cli --file add "$f" --trust-file "$name"
		done
		fapolicyd-cli --update
	    ' sh "$trust_name" $plugins <"$passfile" >/dev/null; then
		echo "$0: failed to update the fapolicyd trust database" >&2
		return 1
	fi

	# fapolicyd reloads its database in the background; wait until every
	# plugin can be opened before starting Ansible.
	tries=0
	for f in $plugins; do
		until head -c 1 "$f" >/dev/null 2>&1; do
			tries=$((tries + 1))
			if [ $tries -gt 30 ]; then
				echo "$0: fapolicyd still denies access to $f" >&2
				return 1
			fi
			sleep 1
		done
	done
	IFS=$oldifs
}

refresh_fapolicyd_trust || exit 1

exec ansible-playbook \
	-u bsradmin \
	--become-password-file "$passfile" \
	$vault_args \
	-v \
	-i "$inventory" \
	global-playbook.yml
