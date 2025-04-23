# lustre-ansible
This repository contains scripts and Ansible-powered IaC playbooks for configuring RackTop's Linux-based Lustre configurations. This is work in progress and is at this moment not complete. There are a number of gaps in this stack and over time we are going to be filling them.

At this moment we can only support a single pool, because we use the name of the pool as an index (think hash table) and the tasks which use this approach do not loop through a list of pools. Instead, a variable stores the name of the pool and that variable is used as a key into the hash.

## Capabilities
### Out of scope
Once this project is fully implemented we expect certain functions to remain out of scope. The following things are going to remain out of scope for the foreseable future:
- Placement of SSH keys on the Lustre nodes
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
- Lnet setup (Lustre networking)
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

It is rather inconvenient to type in the password each time, which is required when `sudo` requires user to enter the password. Create a password file at the root of this checked out repository to avoid interactive prompting. _Please_ do not check this file into `git`. You may call it anything, but during development we called it `bsradminpass`. The password must be in plain text, thus make sure this file is not wide open. Set very restrictive permissions to limit access.

## Configuration
Once the environment is setup and you are ready to run the automation it is necessary to properly configure various settings specific to this environment. Two files govern these settings: `inventory.yml` and `group_vars/lustre_nodes`. As this project matures we may find need for multiple groups and thus variable files for each such group. At this time only one group is actively used: `lustre_nodes`.

### Inventory file
We placed an example inventory file in the root of this repository. Ansible supports a number of styles (formats) for the inventory file. We chose YAML for its flexibility and inherently hierarchical nature. The inventory file is reasonably well commented to make it easier to get started. Please, rename the inventory file `inventory.yml.example` to `inventory.yml` and fill it out according to the specifics in the environment.

### Organization of the inventory file
The top-most level in this file is a hash containing group names, each of which is itself a hash with a single key called `hosts`. Items in this hash are the hosts belonging to this group. Each group can also have variables assigned to it in the inventory file called _group variables_.

#### Hosts
Each host may be specified by an IP address, a DNS name or a name from the local hosts file, as well as long as they are resolvable. All hosts in the `mdt` and `ost` groups will have several variables. These variables, expressed as elements in a hash (key/value pairs) are applicable to _that host only_. In other words, their scope is limited to this one host and each host must have these variables defined. Ansible will fail if only _some_ of the hosts in the inventory have these variables if these variables are referenced anywhere in the playbooks. In the case of the `ib_addrs` hash we have two keys, `ib0` and `ib1`. If only one of two interfaces is expected to be used, make sure that the unused interface has `null` as its value. This will ensure that this interface is ignored when configuration is applied to the remote system.

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
#### Offline Registration
Among other things, one of the steps is registration of the systems. In order for registration to happen, because these systems have no access to the Internet, offline registration files must be provided. RackTop is expected to supply offline registration files for each system. All registration files must be renamed such that the filename matches the hostname specified in the inventory file plus the `.oreg` extension. These files must reside in the `inputs/registration` directory. Thus, if a hostname assigned to a system is `system01`, the filename will be `system01.oreg` and the path relative to the root of this repository is `inputs/registration/system01.oreg`.

As previously mentioned, the `global-playbook.yml` is the primary playbook which aggregates tasks and handlers from several files. This is the playbook which must be executed.
The following command assumes that the user executing tasks on the remote systems is called `bsradmin`, the password lives in the `bsradminpass` and inventory is in the `inventory.yml` file.
```bash
$ ansible-playbook -u bsradmin --become-password-file bsradminpass -v -i inventory.yaml global-playbook.yml
```

## Development
The repository is organized in a modular fashion to ease development. We should aim for tasks files which are relatively standalone and complete a single objective. It may make sense to have files which combine objectives when those objectives are related and the file isn't so long that developing and debugging it is becoming a burden. It may make sense to have variables in the global playbook, but you are more likely to benefit from variables defined in individual task blocks. There are examples of this in the repo. It makes sense to do this when the variable is only used in one place, or perhaps in a handful of tasks, in which case it has to be defined in each task, since the scope of the variable does not extend beyond the scope of the given task.

Because we may not always want to run _all_ the tasks imported by the global playbook we can create a minimized version of the global playbook by copying the global playbook and commenting out all but the included files that we need to run. This will speed-up development and debugging efforts.
