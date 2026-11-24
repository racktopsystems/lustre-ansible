## Cluster reinstall ordering

This will be to operator taste. One can start off be either:

1. Reinstalling the Windows witness host with RHEL 8 WITNESS installation, then reinstalling the OSS/MDS nodes from it.
2. Using the existing Windows witness to reinstall the OSS/MDS nodes, then reinstalling the Windows witness with the RHEL 8 WITNESS install as the final major step.

Either way, all hosts will be reinstalled with the new RHEL 8 that is appropriate for them and whether you do that from a Windows or RHEL8 witness is your choice. Following their reinstallation, the post-install manual tasks must be performed.

1. Initial configuration of hostname and main/admin network interface via the systems' console
2. Applying firmware updates
3. Running Ansible from the witness to configure the systems for operational use.

## Post-install manual tasks

1. Login on system console (root/racktop1)
2. Set the hostname: `hostnamectl set-hostname <hostname>`
3. Configure network address on the main/admin interface. You will need the system's admin IP address with CIDR netmask (eg; 10.2.26.4/24), the default gateway IP address, and the IP addresses of any DNS servers. The main admin interface on the Stennis systems should be `ens259f0`. The commandline to input all this in one go is:

```text
# nmcli con mod ens259f0 \
	ipv4.method manual \
	ipv4.addresses <CIDR interface IP address> \
	ipv4.gateway <default gateway IP address> \
	ipv4.dns <DNS server IP address(es), comma-separated> \
	connection.autoconnect true \
	connection.zone public
```

Note that bash tab-completion works for the `nmcli` command options and interface names, making things a bit easier to type out.

A Reboot of the system following setting of the hostname and main interface is required.

## Updating system firmware

### Coyote Pass systems

Coyote Pass (M50CYP) systems must have their firmware versions serially updated to get to the latest available version. Intermediate versions may not be skipped. 

1. Run `sfup-update -l m50cyp` to get a list of available firmware versions.
2. Run `sfup-update m50cyp <version>` to install the given version of CPLD, BIOS, and BMC firmwares.

**NOTE:** Reboots are required between application of different versions. 

### Indium firmware upgrade

The firmware upgrade for the Seagate Indium systems is provided in `/opt/firmware/indium` on the witness and each OSS/MDS node. The firmware update is a zip file that may be uploaded to each Indium via its web UI. Follow on-screen instructions for applying it.

## Install KMIP key and certificates

If applicable, the cluster's KMIP configuration is managed by Ansible. Prior to the first Ansible run, the KMIP key certificates that the nodes in the cluster use must be exported from the Fortinex appliance and saved as PEM files in a speciifc directory in the Ansible directory structure.

1. Log into the KMIP/Fornetix system for the cluster and locate the KMIP certificate in its UI
2. The certificate files are saved on a per-node basis under the `inputs/keymgr` directory of the `lustre-ansible` directory structure:

```text
inputs/keymgr/ossnode1/certauth.pem
inputs/keymgr/ossnode1/clientkey.pem
inputs/keymgr/ossnode1/clientcert.pem

inputs/keymgr/ossnode2/certauth.pem
inputs/keymgr/ossnode2/clientkey.pem
inputs/keymgr/ossnode2/clientcert.pem

inputs/keymgr/mdsnode1/certauth.pem
inputs/keymgr/mdsnode1/clientkey.pem
inputs/keymgr/mdsnode1/clientcert.pem

inputs/keymgr/mdsnode2/certauth.pem
inputs/keymgr/mdsnode2/clientkey.pem
inputs/keymgr/mdsnode2/clientcert.pem
```

Note that these files may be identical across all the KMIP-participating nodes in the cluster. The decision to break things out on a node-by-node basis is a consideration made towards any future changes where individual nodes get their own certificates.

Clusters that lack KMIP management of keys should have the `kmip_*` variables commented out or removed in the cluster's inventory file.

## First Ansible run

1. Transfer the site or applicable inventory file(s) for the cluster(s) to the the witness. Put them in the `~bsradmin/lustre-ansible` directory. Inventory files for the RackTop labs will already be present there and can serve as templates of in-field clusters.
2. Go to the `~bsradmin/lustre-ansible` directory.
3. Create the `bsradminpass` text file with the command: `echo racktop1 > bsradminpass`
4. Run `bash ./run-bootstrap.sh <inventory file>` and specify the appropriate `inventory` YML file as its command line argument.
5. Run `bash ./run.sh <inventory file>` and specify the same inventory YML file you used with the bootstrap script.

At this point, the systems should be configured for operational use. Verify state and status via Hub and `lustreadm ds` and `lustreadm lnet` commands.