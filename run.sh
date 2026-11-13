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

exec ansible-playbook \
	-u bsradmin \
	--become-password-file bsradminpass \
	-v \
	-i "$inventory" \
	global-playbook.yml
