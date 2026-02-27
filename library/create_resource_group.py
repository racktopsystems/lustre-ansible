#!/usr/bin/env python3

import json
import subprocess
import time
from typing import Any, Dict, List, Tuple

from ansible.module_utils.basic import AnsibleModule

DEFAULT_STATEFILE = "/etc/racktop/hiavd/serialized.dat"
HIAVADM_CMD = "/usr/racktop/sbin/hiavadm"
HWADM_LIST_POOLS_CMD = ["/usr/racktop/sbin/hwadm", "-j", "ls", "p"]
HWADM_RESCAN_CMD = ["/usr/racktop/sbin/hwadm", "rescan", "--ep"]


def generate_ssh_cmd_prefix(addr: str, keydir: str) -> List[str]:
    """Generate SSH command prefix for remote execution."""
    return [
        "/bin/ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-i",
        f"{keydir}/id_ed25519",
        addr,
    ]


def ensure_pool_is_visible(
    poolname: str, addr: str = "", keydir: str = "/root/.ssh", locally: bool = True
) -> Tuple[bool, subprocess.CalledProcessError]:
    """Determine whether or not poolname pool is visible on the system, either locally or remotely."""
    cmd = (
        HWADM_LIST_POOLS_CMD
        if locally
        else generate_ssh_cmd_prefix(addr, keydir) + HWADM_LIST_POOLS_CMD
    )
    try:
        res = subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except subprocess.CalledProcessError as err:
        return False, err
    return pool_exists_in_the_result(poolname, res), None


def issue_hwd_refresh(addr: str = "", keydir: str = "/root/.ssh", locally: bool = True):
    """Issue a hardware refresh command, locally or remotely."""
    cmd = (
        HWADM_RESCAN_CMD
        if locally
        else generate_ssh_cmd_prefix(addr, keydir) + HWADM_RESCAN_CMD
    )
    try:
        res = subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except subprocess.CalledProcessError as err:
        return False, err
    # Normally we should only see the rescan message.
    return res.stdout + res.stderr == b"Rescan started.\ncomplete.\n", None


def pool_exists_in_the_result(poolname: str, result) -> bool:
    """Returns True if poolname exists in the result, else False."""
    pools = json.loads(result.stdout)
    poolnames = [pool["Name"] for pool in pools or []]
    return poolname in poolnames


def create_resource_group(
    rgname: str, hostname: str = "", hostname_filename: str = "/etc/hostname"
) -> Tuple[bool, Exception]:
    """Creates a resource group without adding any pools."""
    # We read in the filename from the configuration file on the system if one
    # was not passed in explicitly.
    if not hostname:
        try:
            with open(hostname_filename, "rt") as fp:
                hostname = fp.read(256).rstrip("\n")
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
    """Add a pool to a resource group."""
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
    """Get the current cluster state as a dictionary."""
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
    """Exception for when a pool is not found in the cluster state."""

    pass


class PoolNotRepairableException(Exception):
    """Exception for when a pool is not repairable."""

    pass


def check_and_repair_if_possible(poolname: str) -> Tuple[bool, Exception]:
    """
    Checks the pool for problems and attempts repair if possible.
    Returns (True, None) if healthy or repaired, (False, Exception) otherwise.
    """
    pool_info = dict()
    # FIXME: Add proper error handling
    state, err = get_current_cluster_state()
    if err:
        return False, err
    # Due to the dynamic nature of the environment the structure of the data
    # may be changing at the same time as we query it. Thus, it is possible
    # that cluster state will not contain some or all of the pools.
    pool_info = next(
        (
            pool
            for rg in state.get("ResourceGroups", [])
            for pool in rg.get("Pools", [])
            if pool.get("Name") == poolname
        ),
        None,
    )
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
        return False, PoolNotRepairableException(pool_info["Problems"])
    try:
        subprocess.run(
            [HIAVADM_CMD, "repair"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as err:
        return False, err
    return True, None


def check_pool_already_in_resource_group(
    poolname: str, statefile: str = DEFAULT_STATEFILE
) -> bool:
    """Checks whether the given pool is already tied to a resource group."""
    # Gracefully handle absence of the state file here. If the file is missing
    # assume that pool cannot be in _any_ resource group, since the cluster is
    # not even configured.
    try:
        with open(statefile, "rb") as fp:
            state = json.loads(fp.read())
        cluster = state.get("Cluster", {})
        pools = cluster.get("Pools", {})
        rgs = cluster.get("ResourceGroups", {})
        group_ids = rgs.keys()
        for details in pools.values():
            if (
                details["CachedName"] == poolname
                and details["ResourceGroupId"] in group_ids
            ):
                return True
    except IOError:
        pass  # We fall through to return.
    return False


def increment_missing_pool_count(poolname: str, missing_pools: Dict[str, int]):
    """Increments count for a pool in the dict, adds if not already present."""
    missing_pools[poolname] = missing_pools.get(poolname, 0) + 1


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
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)
    poolname = module.params["poolname"]
    ha_peer_ipaddr = module.params["ha_peer_ipaddr"]
    node = module.params["node"]

    # Don't do anything else if the pool is already part of the resource group.
    if check_pool_already_in_resource_group(poolname):
        module.exit_json(
            msg="pool already in a resource group", poolname=poolname, changed=False
        )

    missing_pools = {}
    local_hw_refresh_errors, remote_hw_refresh_errors = [], []

    # Try to ensure pool is visible locally
    for backoff in range(1, 5):
        ok_on_local, _ = ensure_pool_is_visible(poolname)
        if ok_on_local:
            break
        increment_missing_pool_count(poolname, missing_pools)
        ok, err = issue_hwd_refresh()
        if not ok:
            local_hw_refresh_errors.append(err)
        time.sleep(backoff)

    # Try to ensure pool is visible on peer
    for backoff in range(1, 5):
        ok_on_peer, _ = ensure_pool_is_visible(poolname, ha_peer_ipaddr, locally=False)
        if ok_on_peer:
            break
        increment_missing_pool_count(poolname, missing_pools)
        ok, err = issue_hwd_refresh(addr=ha_peer_ipaddr, locally=False)
        if not ok:
            remote_hw_refresh_errors.append(err)
        time.sleep(backoff)

    # Create a resource group based on the name of the pool.
    rgname = "RG" + poolname[1:]  # Drop leading 'p' from the pool name

    # Try to create the resource group, retrying if cluster is in transition
    for delay in range(1, 17):
        ok, err = (
            create_resource_group(rgname, hostname=node)
            if node
            else create_resource_group(rgname)
        )
        if ok:
            break
        if (
            isinstance(err, subprocess.CalledProcessError)
            and err.stderr == b"Cluster is currently in transition.\n"
        ):
            time.sleep(delay)
            continue
        module.fail_json(
            msg="non-zero exit status"
            if isinstance(err, subprocess.CalledProcessError)
            else str(err),
            missing_pools=missing_pools,
            refresh_errors={
                "local": local_hw_refresh_errors,
                "remote": remote_hw_refresh_errors,
            },
            changed=False,
        )

    # Try to add the pool to the resource group, retrying if cluster is in transition
    for delay in range(1, 17):
        ok, err = add_pool_to_resource_group(rgname, poolname)
        # Pool was added to the resource group successfully.
        if ok:
            break
        if (
            isinstance(err, subprocess.CalledProcessError)
            and err.stderr == b"Cluster is currently in transition.\n"
        ):
            time.sleep(delay)
            continue
        module.fail_json(
            msg="non-zero exist status"
            if isinstance(err, subprocess.CalledProcessError)
            else str(err),
            missing_pools=missing_pools,
            refresh_errors={
                "local": local_hw_refresh_errors,
                "remote": remote_hw_refresh_errors,
            },
            changed=False,
        )

    # We are going to potentially retry this check because the cluster is in the state of flux.
    err = None
    for delay in range(1, 6):
        ok, err = check_and_repair_if_possible(poolname)
        if ok:
            module.exit_json(
                poolname=poolname, resource_group_name=rgname, changed=True
            )
        # We should try again after a brief delay, because the state of the cluster may be changing.
        if isinstance(err, PoolNotFoundException):
            time.sleep(delay)
    # If we got here we still have an error.
    module.fail_json(
        msg=str(err),
        missing_pools=missing_pools,
        refresh_errors={
            "local": local_hw_refresh_errors,
            "remote": remote_hw_refresh_errors,
        },
        changed=True,
    )


def main():
    run_module()


if __name__ == "__main__":
    main()
