#!/bin/sh

ansible-playbook \
	-u bsradmin \
	--become-password-file bsradminpass \
	-v \
	-i inventory.yaml \
	bootstrap-keys.yml
