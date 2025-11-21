#!/usr/bin/env python3
import os

from ansible.module_utils.basic import AnsibleModule


def find_pools_via_procfs(basedir: str = "/proc/spl/kstat/zfs"):
    pools = []
    for contents in os.walk(basedir):
        if contents[1]:
            pools = contents[1]
            break
    return tuple(pools)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            procfs_path=dict(type="str", required=False),
        ),
    )

    procfs_path = module.params["procfs_path"]
    if procfs_path:
        pools = find_pools_via_procfs(procfs_path)
    else:
        pools = find_pools_via_procfs()

    module.exit_json(changed=False, ansible_facts={"zfs": {"pools": pools}})


if __name__ == "__main__":
    main()
