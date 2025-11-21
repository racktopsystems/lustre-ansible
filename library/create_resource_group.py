#!/usr/bin/env python3

import json
import subprocess
import time

from typing import Any, Dict, List, Tuple
from ansible.module_utils.basic import AnsibleModule

HIAVADM_CMD = "/usr/racktop/sbin/hiavadm"

hwadm_list_pools_cmd = [
    "/usr/racktop/sbin/hwadm",
    "-j",
    "ls",
    "p",
]

hwadm_rescan_cmd = [
    "/usr/racktop/sbin/hwadm",
    "rescan",
    "--ep",
]

hwadm_list_pools_cmd = [
    "/usr/racktop/sbin/hwadm",
    "-j",
    "ls",
    "p",
]


def generate_ssh_cmd_prefix(addr: str, keydir: str) -> List[str]:
    return [
        "/bin/ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-i",
        keydir + "/" + "id_ed25519",
        addr,
    ]


def ensure_pool_is_visible(
    poolname: str, addr: str = "", keydir: str = "/root/.ssh", locally: bool = True
) -> Tuple[bool, subprocess.CalledProcessError]:
    """Determine whether or not poolname pool is visible on the system, either locally or remotely."""
    res = None
    ssh_command_prefix = generate_ssh_cmd_prefix(addr, keydir)
    cmd = hwadm_list_pools_cmd if locally else ssh_command_prefix + hwadm_list_pools_cmd

    try:
        res = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as err:
        return False, err
    return pool_exists_in_the_result(poolname, res), None


def issue_refresh(addr: str = "", keydir: str = "/root/.ssh", locally: bool = True):
    ssh_command_prefix = generate_ssh_cmd_prefix(addr, keydir)
    cmd = hwadm_rescan_cmd if locally else ssh_command_prefix + hwadm_rescan_cmd

    try:
        res = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as err:
        return False, err

    # Normally we should only see the rescan message.
    return res.stdout + res.stderr == b"Rescan started.\ncomplete.\n", None


def pool_exists_in_the_result(poolname: str, result) -> bool:
    """Returns True if poolname exists in the result, else False."""
    pools = json.loads(result.stdout)
    # Ensure None value from json.loads(...) does not lead to a TypeError.
    poolnames = [pool["Name"] for pool in pools or []]
    return poolname in poolnames if poolnames else False


def create_resource_group(
    rgname: str, hostname: str = "", hostname_filename: str = "/etc/hostname"
) -> Tuple[bool, Exception]:
    """Creates a resource group without adding any pools."""

    # We read in the filename from the configuration file on the system if one
    # was not passed in explicitly.
    if not hostname:
        try:
            with open(hostname_filename, "rt") as fp:
                hostname = fp.read(256)
                if hostname:
                    hostname = hostname[:-1]  # Trim trailing newline
        except IOError as err:
            return False, err
    try:
        # Creating an already existing resource group is idempotent and will
        # result in a success process exit.
        res = subprocess.run(
            [HIAVADM_CMD, "u", "r", "-n", hostname, rgname],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as err:
        return False, err
    # Upon success we expect nothing on STDOUT or STDERR.
    return res.stdout + res.stdout == b"", None


def add_pool_to_resource_group(rgname: str, poolname: str) -> Tuple[bool, Exception]:
    try:
        res = subprocess.run(
            [HIAVADM_CMD, "u", "p", "--add", rgname, poolname],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as err:
        return False, err

    return res.stdout + res.stderr == b"", None


def get_current_cluster_state() -> Tuple[Dict[Any, Any], Exception]:
    try:
        res = subprocess.run(
            [HIAVADM_CMD, "i", "dump"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as err:
        return dict(), err
    return json.loads(res.stdout), None


class PoolNotFoundException(Exception):
    pass


class PoolNotRepairableException(Exception):
    pass


def check_and_repair_if_possible(poolname: str) -> Tuple[bool, Exception]:
    pool_info = dict()
    # FIXME: Add proper error handling
    cluster_state, err = get_current_cluster_state()
    if err:
        return False, err
    # Due to the dynamic nature of the environment the structure of the data
    # may be changing at the same time as we query it. Thus, it is possible
    # that cluster state will not contain some or all of the pools.
    for rg in cluster_state["ResourceGroups"]:
        pools = rg.get("Pools")
        if not pools:
            continue
        for pool in pools:
            if pool["Name"] == poolname:
                pool_info = pool
                break
    if not pool_info:
        return False, PoolNotFoundException(
            f"pool '{poolname}' missing from cluster info"
        )
    # If there are no known problems then there is nothing to fix.
    # At this point we are in a good state.
    if not pool_info["Problems"]:
        return True, None

    # If there are known problems and this flag indicates that they are
    # not repairable, we do not attempt to repair. Otherwise attempt to
    # repair and if the command is successful, we assume things are now OK.
    if not pool_info["CanRepair"]:
        return (False, PoolNotRepairableException(pool_info["Problems"]))
    try:
        _ = subprocess.run(
            [HIAVADM_CMD, "repair"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as err:
        return False, err
    return True, None


def check_pool_already_in_resource_group(
    poolname: str, statefile: str = "/etc/racktop/hiavd/serialized.dat"
) -> bool:
    """Checks whether the given pool is already tied to a resoure group."""
    current_state = dict()
    # We are not doing any exception handling here. If this fails there are
    # some real problems with the system and the failure of the task is a
    # relatively minor event in comparison.
    with open(statefile, "rb") as fp:
        current_state = json.loads(fp.read(-1))
    pools = current_state["Cluster"]["Pools"]
    group_ids = current_state["Cluster"]["ResourceGroups"].keys()
    for _, details in pools.items():
        if details["CachedName"] != poolname:
            continue
        if details["ResourceGroupId"] in group_ids:
            return True
    return False


def run_module():
    # Define available arguments/parameters a user can pass to the module
    module_args = dict(
        poolname=dict(type="str", required=True),
        ha_peer_ipaddr=dict(type="str", required=True),
        node=dict(type="str", required=False, default=""),
        use_random_delay=dict(type="bool", required=False, default=False),
        delay_min=dict(type="float", required=False, default=0.5),
        delay_max=dict(type="float", required=False, default=2.0),
    )

    # Seed result dict in the object
    result = dict(
        changed=False,
        original_message="",
        message="",
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    poolname = module.params["poolname"]
    ha_peer_ipaddr = module.params["ha_peer_ipaddr"]
    node = module.params["node"]

    # Wire this in later
    use_random_delay = module.params["use_random_delay"]
    delay_min = module.params["delay_min"]
    delay_max = module.params["delay_max"]

    # Don't do anything else if the pool is already part of the resource group.
    if check_pool_already_in_resource_group(poolname):
        result = dict(
            msg="pool already in a resource group",
            poolname=poolname,
            changed=False,
        )

        module.exit_json(**result)

    backoff = 1
    for _ in range(60):
        ok_on_local, _ = ensure_pool_is_visible(poolname)
        if not ok_on_local:
            _ = issue_refresh()
            time.sleep(backoff)  # Backoff just a bit, yes hacky
            backoff += 1
        else:
            break

    backoff = 1
    for _ in range(60):
        ok_on_peer, _ = ensure_pool_is_visible(poolname, ha_peer_ipaddr, locally=False)
        if not ok_on_peer:
            _ = issue_refresh(addr=ha_peer_ipaddr, locally=False)
            time.sleep(backoff)  # Backoff here as well, also hacky
            backoff += 1
        else:
            break

    # Create a resource group based on the name of the pool.
    rgname = "RG" + poolname[1:]  # Drop leading 'p' from the pool name

    delay = 1
    for _ in range(30):
        if node:
            ok, err = create_resource_group(rgname, hostname=node)
        else:
            ok, err = create_resource_group(rgname)

        # Resource group was created successfully. Move onto pool addition.
        if ok:
            break

        if isinstance(err, subprocess.CalledProcessError):
            # If the cluster is currently transitioning, let's try again
            # after a brief delay.
            if err.stderr == b"Cluster is currently in transition.\n":
                time.sleep(delay)
                delay += 1
                continue

            module.fail_json(
                msg="non-zero exit status",
                cmd=err.cmd,
                returncode=err.returncode,
                stdout=err.stdout,
                stderr=err.stderr,
                changed=False,
            )
        elif isinstance(err, IOError):
            module.fail_json(
                msg="IO error encountered",
                args=err.args,
                errno=err.errno,
                filename=err.filename,
                filename2=err.filename2,
                strerror=err.strerror,
                changed=False,
            )
        else:
            module.fail_json(msg=str(err), changed=False)

    delay = 1
    for _ in range(30):
        ok, err = add_pool_to_resource_group(rgname, poolname)

        # Pool was added to the resource group successfully.
        if ok:
            break

        if isinstance(err, subprocess.CalledProcessError):
            # If the cluster is currently transitioning, let's try again
            # after a brief delay.
            if err.stderr == b"Cluster is currently in transition.\n":
                time.sleep(delay)
                delay += 1
                continue

            module.fail_json(
                msg="non-zero exist status",
                cmd=err.cmd,
                returncode=err.returncode,
                stdout=err.stdout,
                stderr=err.stderr,
                changed=False,
            )
        else:
            module.fail_json(msg=str(err), changed=False)

    delay = 1
    err = None
    # We are going to potentially retry this check because the cluster is in the
    # state of flux.
    for _ in range(5):
        ok, err = check_and_repair_if_possible(poolname)
        if ok:
            module.exit_json(
                **dict(
                    poolname=poolname,
                    resource_group_name=rgname,
                    changed=True,
                )
            )

        # We should try again after a brief delay, because the state of the
        # cluster may be changing.
        if isinstance(err, PoolNotFoundException):
            time.sleep(delay)
            delay += 1
    # If we got here we still have an error.
    module.fail_json(msg=str(err), changed=True)


def main():
    run_module()


if __name__ == "__main__":
    main()
