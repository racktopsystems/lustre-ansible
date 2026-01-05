#!/usr/bin/env python3
import json
import os
import subprocess
from typing import Any, Dict

from ansible.module_utils.basic import AnsibleModule

DEFAULT_CONFIGFILE = "/etc/racktop/hiavd/hiavd.conf"
DEFAULT_STATEFILE = "/etc/racktop/hiavd/serialized.dat"
DEFAULT_REVISION_ID = 1


class MissingRevisionError(Exception):
    pass


def get_conf_subgroup(statefile: str, subgroup: str) -> Dict[str, Any]:
    """Fetches the named subgroup from the serialized configuration."""
    d = dict()
    state = statefile_to_dict(statefile)
    cluster = state.get("Cluster")
    if cluster:
        d = cluster.get(subgroup)
    return d


def statefile_to_dict(statefile: str) -> Dict[str, Any]:
    """Converts serialized statefile to a native dict object."""
    try:
        with open(statefile, "rb") as fp:
            current_state = json.load(fp)
    except FileNotFoundError:
        return dict()
    return current_state


def resource_groups(statefile: str) -> Dict[str, Any]:
    """Fetches the ResourceGroups object out of the serialized configuration."""
    return get_conf_subgroup(statefile, "ResourceGroups")


def pools(statefile: str) -> Dict[str, Any]:
    """Fetches the Pools object out of the serialized configuration."""
    return get_conf_subgroup(statefile, "Pools")


def pool_info_by_name(statefile: str) -> Dict[str, Any]:
    """
    Generates a dict where keys are pool names and values are details for the
    given pool.
    """
    p = pools(statefile)
    new_p = dict()
    for k, v in p.items():
        poolname = v.get("CachedName")
        if not poolname:
            continue
        new_p[poolname] = v
    return new_p


def statefile_is_missing(statefile: str) -> bool:
    """Returns True if there is no statefile on the system."""
    return not os.path.exists(statefile)


def revision_is_initial(statefile: str) -> bool:
    state = statefile_to_dict(statefile)
    cluster = state.get("Cluster")
    if cluster:
        return cluster.get("Revision") == DEFAULT_REVISION_ID
    raise MissingRevisionError("no revision field found in the state file")


def statefile_missing_or_initial(statefile: str) -> bool:
    """Returns True if no configuration or initial configuration."""
    return statefile_is_missing(statefile) or revision_is_initial(statefile)


def no_cluster_nodes_defined(configfile: str):
    """Returns True if there are no nodes defined in the cluster."""
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
                "new_configuration": no_cluster_nodes_defined(configfile)
                or statefile_missing_or_initial(statefile),
                "pools": pool_info_by_name(statefile),
                "version": version,
            }
        }
        module.exit_json(changed=False, ansible_facts=hiavd_facts)
    except subprocess.CalledProcessError as e:
        module.fail_json(changed=False, msg=str(e))


if __name__ == "__main__":
    main()
