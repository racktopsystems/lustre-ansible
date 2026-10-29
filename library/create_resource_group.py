#!/usr/bin/env python3
"""Put a ZFS pool under HA control in a resource group of its own.

Pools are never imported by Ansible. A pool that is exported but visible to
both HA nodes is listed by hiavd as unmapped; adding it to a resource group
makes hiavd import it on the resource group's node and move it between the
nodes from then on. The module waits until hiavd reports the pool healthy,
so later tasks find it imported on the resource group's node.

The module only acts on the node it runs on. Whether the HA peer sees the
pool is checked by the playbook (tasks/ha-setup.yml) as an ordinary task on
the peer, and hiavd checks it again when the pool is added, so no node logs
in to its peer.
"""

import json
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from ansible.module_utils.basic import AnsibleModule

DEFAULT_STATEFILE = "/etc/racktop/hiavd/serialized.dat"
HIAVADM_CMD = "/usr/racktop/sbin/hiavadm"
HWADM_LIST_POOLS_CMD = ["/usr/racktop/sbin/hwadm", "-j", "ls", "p"]
HWADM_RESCAN_CMD = ["/usr/racktop/sbin/hwadm", "rescan", "--ep"]
IN_TRANSITION = b"Cluster is currently in transition.\n"
HEALTHY = "Good"


def describe_error(err: Optional[Exception]) -> Any:
    """A JSON-serializable description of an error, for module results."""
    if err is None:
        return None
    if isinstance(err, subprocess.CalledProcessError):
        return {
            "cmd": " ".join(err.cmd),
            "rc": err.returncode,
            "stdout": (err.stdout or b"").decode(errors="replace").strip(),
            "stderr": (err.stderr or b"").decode(errors="replace").strip(),
        }
    return str(err)


def run(cmd: List[str]) -> Tuple[Optional[subprocess.CompletedProcess], Optional[Exception]]:
    try:
        res = subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except (subprocess.CalledProcessError, OSError) as err:
        return None, err
    return res, None


def pool_is_visible(poolname: str) -> Tuple[bool, Optional[Exception]]:
    """Whether this node lists the pool, imported or exported."""
    res, err = run(HWADM_LIST_POOLS_CMD)
    if err:
        return False, err
    pools = json.loads(res.stdout) or []
    return poolname in [pool["Name"] for pool in pools], None


def issue_hwd_refresh() -> Optional[Exception]:
    """Ask hwd to rescan exported pools."""
    _, err = run(HWADM_RESCAN_CMD)
    return err


def wait_until_visible(poolname: str) -> Tuple[bool, List[Any]]:
    """Rescan until the pool is visible, with growing delays (about 10s)."""
    errors = []
    for delay in range(1, 5):
        visible, err = pool_is_visible(poolname)
        if visible:
            return True, errors
        if err:
            errors.append(describe_error(err))
        err = issue_hwd_refresh()
        if err:
            errors.append(describe_error(err))
        time.sleep(delay)
    visible, err = pool_is_visible(poolname)
    if err:
        errors.append(describe_error(err))
    return visible, errors


def hiavadm_retrying(args: List[str], attempts: int = 16) -> Optional[Exception]:
    """Run hiavadm, retrying while the cluster is in transition."""
    err = None
    for delay in range(1, attempts + 1):
        _, err = run([HIAVADM_CMD] + args)
        if err is None:
            return None
        if not (
            isinstance(err, subprocess.CalledProcessError)
            and err.stderr == IN_TRANSITION
        ):
            return err
        time.sleep(delay)
    return err


def get_current_cluster_state() -> Tuple[Dict[str, Any], Optional[Exception]]:
    """Get the current cluster state as a dictionary."""
    res, err = run([HIAVADM_CMD, "i", "dump"])
    if err:
        return {}, err
    return json.loads(res.stdout), None


def find_pool(state: Dict[str, Any], poolname: str) -> Optional[Dict[str, Any]]:
    for rg in state.get("ResourceGroups") or []:
        for pool in rg.get("Pools") or []:
            if pool.get("Name") == poolname:
                return pool
    return None


def wait_until_healthy(poolname: str, timeout: int) -> Tuple[bool, Any]:
    """Wait for hiavd to import the pool on its resource group's node and
    report it healthy, repairing it once if hiavd says that is possible."""
    deadline = time.monotonic() + timeout
    repaired = False
    last: Any = "pool not yet in the cluster state"
    while True:
        state, err = get_current_cluster_state()
        if err:
            last = describe_error(err)
        else:
            pool = find_pool(state, poolname)
            if pool is not None:
                last = {
                    "Status": pool.get("Status"),
                    "StatusDetails": pool.get("StatusDetails"),
                    "Problems": pool.get("Problems"),
                    "Transitioning": pool.get("Transitioning"),
                }
                if pool.get("Status") == HEALTHY and not pool.get("Transitioning"):
                    return True, last
                if (
                    pool.get("Problems")
                    and pool.get("CanRepair")
                    and not pool.get("Transitioning")
                    and not repaired
                ):
                    repaired = True
                    _, err = run([HIAVADM_CMD, "repair"])
                    if err:
                        last = {"repair": describe_error(err), "pool": last}
        if time.monotonic() >= deadline:
            return False, last
        time.sleep(5)


def check_pool_already_in_resource_group(
    poolname: str, statefile: str = DEFAULT_STATEFILE
) -> bool:
    """Checks whether the given pool is already tied to a resource group."""
    # A missing state file means the cluster is not configured, so the pool
    # cannot be in a resource group.
    try:
        with open(statefile, "rb") as fp:
            state = json.loads(fp.read())
    except IOError:
        return False
    cluster = state.get("Cluster") or {}
    pools = cluster.get("Pools") or {}
    group_ids = (cluster.get("ResourceGroups") or {}).keys()
    return any(
        details.get("CachedName") == poolname
        and details.get("ResourceGroupId") in group_ids
        for details in pools.values()
    )


def local_hostname(filename: str = "/etc/hostname") -> str:
    with open(filename, "rt") as fp:
        return fp.read(256).strip()


def run_module():
    module = AnsibleModule(
        argument_spec=dict(
            poolname=dict(type="str", required=True),
            node=dict(type="str", required=False, default=""),
            import_timeout=dict(type="int", required=False, default=300),
        ),
        supports_check_mode=True,
    )
    poolname = module.params["poolname"]

    if check_pool_already_in_resource_group(poolname):
        module.exit_json(
            msg="pool already in a resource group", poolname=poolname, changed=False
        )

    visible, errors = wait_until_visible(poolname)
    if not visible:
        module.fail_json(
            msg=f"pool {poolname} is not visible on this node. Check the pool "
            "name and that the node sees its drives (hwadm ls p).",
            poolname=poolname,
            errors=errors,
            changed=False,
        )

    if module.check_mode:
        module.exit_json(
            msg="resource group would be created", poolname=poolname, changed=True
        )

    try:
        node = module.params["node"] or local_hostname()
    except IOError as err:
        module.fail_json(msg=f"reading this node's hostname: {err}", changed=False)

    # One resource group per pool, named after it: p_ost01 -> RG_ost01,
    # oss01 -> RG_oss01.
    rgname = "RG" + (poolname[1:] if poolname.startswith("p_") else "_" + poolname)

    err = hiavadm_retrying(["u", "r", "-n", node, rgname])
    if err:
        module.fail_json(
            msg=f"creating resource group {rgname} failed",
            error=describe_error(err),
            poolname=poolname,
            changed=False,
        )

    err = hiavadm_retrying(["u", "p", "--add", rgname, poolname])
    if err:
        module.fail_json(
            msg=f"adding pool {poolname} to resource group {rgname} failed",
            error=describe_error(err),
            poolname=poolname,
            resource_group_name=rgname,
            changed=True,
        )

    healthy, status = wait_until_healthy(poolname, module.params["import_timeout"])
    if not healthy:
        module.fail_json(
            msg=f"pool {poolname} was added to resource group {rgname}, but hiavd "
            f"did not report it healthy within {module.params['import_timeout']}s",
            status=status,
            poolname=poolname,
            resource_group_name=rgname,
            changed=True,
        )

    module.exit_json(
        poolname=poolname, resource_group_name=rgname, node=node, status=status, changed=True
    )


def main():
    run_module()


if __name__ == "__main__":
    main()
