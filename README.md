# lustre-ansible
This repository contains scripts and Ansible-powered IaC playbooks for configuring RackTop's Linux-based Lustre configurations. This is work in progress and is at this moment not complete. There are a number of gaps in this stack and over time we are going to be filling them.

At this moment we can only support a single pool, because we use the name of the pool as an index (think hash table) and the tasks which use this approach do not loop through a list of pools. Instead, a variable stores the name of the pool and that variable is used as a key into the hash.

## Capabilities
### Out of scope
Once this project is fully implemented we expect certain functions to remain out of scope. The following things are going to remain out of scope for the foreseable future:
- Configuration of the "primary" network interface. Without this interface we cannot connect to the system in the first place, thus it is assumed to be managed outside of Ansible
- Configuration of storage all enclosures, which should only ever happen once
- Creation of ZFS pools which should only ever happen once
- Any package updates, firmware updates, etc., because the systems are assumed to have no access to external repositories and do not have any internal private repositories

### What should be covered
- BMC (remote management)
- Licensing and registration of the systems
- Basic network configuration beyond the "primary" interface, such as the heartbeat, infiniband, etc.
- Common system settings such as DNS, NTP, SELinux
- High availability and associated resource groups
- Lnet setup (Lustre networking), via `lustreadm lnet` on the InfiniBand interfaces in `ib_addrs`
- Lustre storage configuration

## Repository organization
We chose to make things fairly modular and loosely coupled. There is a primary playbook called `global-playbook.yml` which is a meta playbook and does not itself has much code. It however imports tasks and handlers from other files. The aim is to progressively develop new functionality and place it into new or existing files in the `tasks` directory.

### _tasks_ directory
The `tasks` directory contains a number of YAML files which are meant to be fragments that the `global-playbook.yml` imports. These files are groups of tasks in proper order and as we add new functionality or harden existing functionality. These units of functionality should be largely independent from each other. Functionality that's relatively tightly coupled together belongs in the same file, ideally. All _tasks_ belong in the tasks directory and they are grouped by function. We have tasks for configuring various parts of HA, Lustre, etc. Please review existing tasks file before creating new ones to determine whether additions should be placed into one of the already existing files or a new file is justified.

### _handlers_ directory
The `handlers` directory like the tasks directory contains a number of YAML files which contain handlers used by tasks that the `global-playbook.yml` imports. Like the tasks the handlers are also imported by the global playbook. Handlers are in this way made available to the tasks that utilize them. Handlers are in general not very different from tasks, other than their behaviour. Handlers once notified will only run once on each machine no matter how many times they are notified.

### _templates_ directory
The `templates` directory contains configuration file templates which Ansible is responsible for rendering and placing on the remote systems.

### _library_ directory
The `library` directory contains custom modules. As long as tasks are imported into the global playbook they are going to have access to custom modules in this directory.

## Getting started
### Setting up environment
While it is possible to get started in many ways, we document one method which is fairly straight forward and makes development and triggering of the automation quite easy.

The repository includes a `requirements.txt` file which contains all prerequisites. Ansible requires a POSIX-y environment, thus we assume that it is executed from Linux, Darwin or some BSD system. Python 3 is a core dependency of Ansible, which is written in Python. This should all work with Python 3.11 and newer. It may work with older versions of Python 3, but this is untested. To quickly get situated run the following command after checking out this repository:

#### Virtual environment
It is not necessary to do this, but it makes using and developing with Ansible much easier and decouples the user from the host system. It eliminates need for super-user access, which is otherwise required to install Python packages system-wide.

Create a fresh virtual environment in this directory with the following command.
```bash
$ python3 -m venv venv
```
This will create a brand new local Python installation. Next, we need to activate this "virtual" environment and install Ansible. For anything other than bash, please consult `virtualenv` documentation.
```bash
$ source venv/bin/activate
```
To deactivate the environment, simply run `deactivate` from the same shell where the environment was previously activated. To remove the environment entirely it is sufficient to delete the `venv` directory.

#### Ansible installation
Next, we need to install required packages. Please make sure the environment is active before performing this step. Exact versions of all packages are specified in the `requirements.txt` file, thus ensuring a fully reproducible build and execution environment.
```bash
$ pip install -r requirements.txt
```

#### Ansible configuration
To customize Ansible make changes to the `ansible.cfg` file in the repository. This file is relatively well documented. It will be used automatically unless another configuration file is explicitly specified.

#### Credentials
Ansible connects to remote systems over SSH and normally assumes key-based authentication. It is assumed that keys have already been setup on all remote systems for whichever user is going to be used to connect to them. It is also assumed that this user will have ability to execute tasks via `sudo`. Most tasks do require super-user privileges and will fail unless the given user can `sudo` and assume `root`'s role.

To bootstrap key-based authentication on freshly installed nodes, run the `bootstrap-keys.yml` playbook once. It generates a dedicated RSA 4096 key pair at `sensitive/ansible_id_rsa` on the control node (if not already present), logs in to every `lustre_nodes` host as `bsradmin` using the factory default password, installs the public key, and verifies key-based login. `ansible.cfg` points `private_key_file` at this key, so all subsequent runs use it. Password-based SSH requires `sshpass` on the control node. Use `-e bootstrap_user=<user>` to target a different remote account.
```bash
$ ansible-playbook -i inventory.yaml bootstrap-keys.yml
```

It is rather inconvenient to type in the password each time, which is required when `sudo` requires user to enter the password. Create a password file at the root of this checked out repository to avoid interactive prompting. _Please_ do not check this file into `git`. You may call it anything, but during development we called it `bsradminpass`. The password must be in plain text, thus make sure this file is not wide open. Set very restrictive permissions to limit access.

#### IPMI Credentials
This is only relavant to physical systems. If any hosts in the Inventory configuration have `configure_ipmi: true`, then it is necessary to create a credentials file in the repository containing the password for the IPMI interface. The username for the IPMI user is set via the `group_vars/all` file and should normally not change. Adjust the value of `ipmi_username` as necessary. The password is very sensitive and must be handled carefully. Create a directory at the root of this repository called `sensitive` and place into it a file called `creds.yaml`. The contents of this file look as follows where the placeholder must be replaced with the password for the `ipmi_username` user.
```yaml
---
ipmi_password: <password>
```

## Configuration
Once the environment is setup and you are ready to run the automation it is necessary to properly configure various settings specific to this environment. Two files govern these settings: `inventory.yaml` and `group_vars/lustre_nodes`. As this project matures we may find need for multiple groups and thus variable files for each such group. At this time only one group is actively used: `lustre_nodes`.

### Inventory file
We placed an example inventory file in the root of this repository. Ansible supports a number of styles (formats) for the inventory file. We chose YAML for its flexibility and inherently hierarchical nature. The inventory file is reasonably well commented to make it easier to get started. Please, copy `inventory.yaml.example` to `inventory.yaml` and fill it out according to the specifics in the environment.

### Organization of the inventory file
The top-most level in this file is a hash containing group names, each of which is itself a hash with a single key called `hosts`. Items in this hash are the hosts belonging to this group. Each group can also have variables assigned to it in the inventory file called _group variables_.

#### Hosts
The HA tasks look hosts up by fixed inventory names, so the Lustre servers must be named `ossnode1`, `ossnode2`, `mdsnode1` and `mdsnode2`. The real address of each host is supplied with `ansible_host`. The groups are:

- `oss` and `mds`: the two HA pairs. Each group sets `witness_instance` (see below) and may define a `zpools` list of the ZFS pools managed by that pair.
- `ost` and `mdt`: used by the Lustre storage tasks. They contain the `oss` and `mds` groups respectively.
- `cluster_witness`: the HA witness. One host can witness both pairs by listing it once per pair under different inventory names with the same `ansible_host`. Each entry sets `role` (`oss` or `mds`) and `witness_instance`, which must match the value on that pair's group.
- `lustre_nodes`: everything the playbooks configure (`oss`, `mds` and `cluster_witness`). The witness must be included so its facts are available when the HA peers are configured.

`witness_instance` selects the confd/hiavd service instance on the witness that serves a pair. The ha-witness RPM provides these instances:

| `witness_instance` | Witness services | hiavd config directory | hiavd port | confd ports |
|---|---|---|---|---|
| 0 | `confd`, `hiavd` | `/etc/racktop/hiavd/` | 4746 | 2379, 2380 |
| 1 | `confd@1`, `hiavd@1` | `/etc/racktop/hiavd_1/` | 4747 | 2381, 2382 |

The HA nodes always run the default services. Their hiavd uses the same port as their witness instance, so the nodes of a pair served by instance 1 also listen on 4747. When firewalld is running, the playbook opens these ports.

Every server in `oss` and `mds` must define `hostname`, `first_ha_node` (true on exactly one node of each pair), `ha_peer_ipaddr` (address of the peer), `admin_iface` (management interface, the only one confd uses for peer traffic), `hb_iface` (physical heartbeat link, excluded from confd client URLs; its NetworkManager connection is renamed to `hb0`), `hb_iface_ipaddr` (heartbeat address), `ipmi_ip_address`, `configure_ipmi`, `ib_addrs` and `license_file` (path to the system's `.oreg` license). Ansible will fail if only _some_ of the hosts define a variable that the playbooks reference. Interface addresses (`hb_iface_ipaddr` and the `ib_addrs` values) must be IPv4 CIDR, e.g. `192.255.0.1/24`; the playbooks fail otherwise. In the `ib_addrs` hash there are two keys, `ib0` and `ib1`. If only one interface is used, set the unused one to `null` so it is ignored.

#### Variables
To create variables applicable only to this group create another key at the same level of the hierarchy as `hosts` named `vars`. See example below where we create a variable called `widget_count`. Each group can have the same variables but with different values, which allows for a level of customization in playbooks based on the system's or group's role or purpose.
```yaml
ost:
  hosts:
    192.168.10.1:
    192.168.10.2:
  vars:
    widget_count: 5
```

### Group variables file
In addition to the inventory file which contains _all_ remote systems that Ansible needs to know about we created a `group_vars/example_lustre_nodes` variables file. This file should be named `lustre_nodes`, which will match the name of the group defined in the inventory file. Thus, variables in this file will be made available at runtime to all systems in the inventory which belong to the `lustre_nodes` group. This file is meant to provide environment-specific parameters, but unlike the inventory file where variables are specific to each system, these variables will apply to _all_ members of the `lustre_nodes` group.

## Running the playbook
### Runtime dependencies
#### Licensing and registration
Each HA node needs its own BrickStor license, a system-specific `.oreg` file supplied by RackTop. Set the host's `license_file` inventory variable to that file, either absolute or relative to the root of this repository (for example `inputs/registration/ossnode1.oreg`). Registration is the first thing the playbook does: on hosts that are not yet registered it copies the file over and applies it with `licadm register --file <file> --eula-signer <license_eula_signer>`, then restarts the platform services.

To obtain the offline registration key RackTop needs to generate a system's `.oreg` file, run `sudo /usr/racktop/sbin/licadm register` on that system without `--file`.

As previously mentioned, the `global-playbook.yml` is the primary playbook which aggregates tasks and handlers from several files. This is the playbook which must be executed.
The following command assumes that the user executing tasks on the remote systems is called `bsradmin`, the password lives in the `bsradminpass` and inventory is in the `inventory.yaml` file.
```bash
$ ansible-playbook -u bsradmin --become-password-file bsradminpass -v -i inventory.yaml global-playbook.yml
```

Registration runs by default. To skip it, for example while the `.oreg` files are not yet available, add `-e perform_registration=false`.

## Development
The repository is organized in a modular fashion to ease development. We should aim for tasks files which are relatively standalone and complete a single objective. It may make sense to have files which combine objectives when those objectives are related and the file isn't so long that developing and debugging it is becoming a burden. It may make sense to have variables in the global playbook, but you are more likely to benefit from variables defined in individual task blocks. There are examples of this in the repo. It makes sense to do this when the variable is only used in one place, or perhaps in a handful of tasks, in which case it has to be defined in each task, since the scope of the variable does not extend beyond the scope of the given task.

Because we may not always want to run _all_ the tasks imported by the global playbook we can create a minimized version of the global playbook by copying the global playbook and commenting out all but the included files that we need to run. This will speed-up development and debugging efforts.




Notes:
MDS / MGS pool configuration

Pool names for metadata/management servers:
p_mdt01

Clarify with Max whether we should have two pools, both with `mdt` in their names, where one of those two pools will contain the management dataset as well as the metadata dataset and the second pool will contain _only_ the metadata dataset.

Clarify also whether there will be more than one Lustre dataset per pool.
p_mdt02

p_mgt01

Dataset names for metadata/management servers:
p_mdt01/lustre-mdt
p_mgt01/lustre-mgt01

Pool names for object storage servers:
p_ost01
p_ost02

Dataset names for object storage servers:
p_ost01/lustre-ost01
p_ost02/lustre-ost01
