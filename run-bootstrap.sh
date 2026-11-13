#!/bin/sh

ansible-playbook \
	-u bsradmin \
	--become-password-file bsradminpass \
	-v \
	-i inventory.yml \
	bootstrap-keys.yml
