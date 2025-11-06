#!/usr/bin/env python3
import json
import os
import subprocess

from ansible.module_utils.basic import AnsibleModule


DEFAULT_CONFIGFILE = "/etc/racktop/hiavd/hiavd.conf"
DEFAULT_STATEFILE = "/etc/racktop/hiavd/serialized.dat"
DEFAULT_REVISION_ID = 1


class MissingRevisionError(Exception):
    pass


def statefile_is_missing(statefile: str) -> bool:
    return not os.path.exists(statefile)


def revision_is_initial(statefile: str) -> bool:
    with open(statefile, "rb") as fp:
        state = json.load(fp)
        cluster = state.get("Cluster")
        if cluster:
            return cluster.get("Revision") == DEFAULT_REVISION_ID
    raise MissingRevisionError("no revision field found in the state file")


def statefile_missing_or_initial(statefile: str) -> bool:
    return statefile_is_missing(statefile) or revision_is_initial(statefile)


def no_cluster_nodes_defined(configfile: str):
    with open(configfile, "rb") as f:
        for line in f.readlines():
            if line.startswith(b"[[ClusterNodes]]"):
                return False
    return True


def main():
    module = AnsibleModule(
        argument_spec=dict(
            config_path=dict(type="str", required=False),
            statefile_path=dict(type="str", required=False),
            revision_id=dict(type="int", required=False),
        ),
    )

    configfile = module.params["config_path"]
    configfile = configfile or DEFAULT_CONFIGFILE

    statefile = module.params["statefile_path"]
    statefile = statefile or DEFAULT_STATEFILE

    revision_id = module.params["revision_id"]
    revision_id = revision_id or DEFAULT_REVISION_ID

    try:
        res = subprocess.check_output("/usr/racktop/lib/hiavd -version".split())
        _, version = res.split()
        hiavd_facts = {
            "hiavd": {
                "version": version,
                "new_configuration": no_cluster_nodes_defined(configfile)
                or statefile_missing_or_initial(statefile),
            }
        }
        module.exit_json(changed=False, ansible_facts=hiavd_facts)
    except subprocess.CalledProcessError as e:
        module.fail_json(changed=False, msg=str(e))


if __name__ == "__main__":
    main()
