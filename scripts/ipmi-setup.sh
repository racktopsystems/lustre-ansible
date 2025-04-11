#!/usr/bin/bash

# TODO:
# This script should be converted into an Ansible module which is the
# preferred way for modularizing a step which consists of a series of
# operations.

ipaddr="$1"
netmask="$2"
ipmi_cfg_before="/tmp/ipmi-lan-config-before-$$.txt"
ipmi_cfg_after="/tmp/ipmi-lan-config-after-$$.txt"

function cleanup {
    rm -f "stderr.$$" "${ipmi_cfg_before}" "${ipmi_cfg_before}"
}

trap cleanup EXIT

if [ "$ipaddr" == "" ]; then
    echo "IP address is an empty string" >&2
    exit 1
elif [ "$netmask" == "" ]; then
    echo "Network mask is an empty string" >&2
    exit 1
fi

ipmitool lan print 3 > "${ipmi_cfg_before}"

# We may need to set IPMI to static configuration from DHCP. It is also possible
# that DHCP will be used and will provide pinned IP addresses. We need to make
# our playbook aware of this and more tolerant than it is now.

ipaddr_set_stdout=$(ipmitool lan set 3 ipaddr "${ipaddr}") 2>stderr.$$

if [ "${ipaddr_set_stdout}" != "Setting LAN IP Address to ${ipaddr}" ]; then
    cat stderr.$$
    exit 1
fi

netmask_set_stdout=$(ipmitool lan set 3 netmask "${netmask}") 2>stderr.$$
if [ "${netmask_set_stdout}" != "Setting LAN Subnet Mask to ${netmask}" ]; then
    cat stderr.$$
    exit 1
fi

ipmitool lan print 3 > "${ipmi_cfg_after}"

# If there are changes, print "changed" to stdout. We will use this information
# from Ansible to determine whether or not an actual change to state of the
# IPMI configuration occurred.
if ! diff -q >/dev/null "${ipmi_cfg_before}" "${ipmi_cfg_after}"; then
    echo "changed"
fi

exit 0
