#!/usr/bin/env python3

import subprocess
from pathlib import Path
from typing import Tuple

from ansible.module_utils.basic import AnsibleModule


def pool_imported_and_online(poolname: str) -> Tuple[bool, bool]:
    pool_state_path = Path(f"/proc/spl/kstat/zfs/{poolname}/state")
    imported = pool_state_path.exists()
    if not imported:
        return False, False
    buf = b""
    with pool_state_path.open("rb") as fp:
        buf = fp.read(-1)
    return imported, buf[:-1] == b"ONLINE"


def import_pool(poolname: str) -> Tuple[bool, Exception]:
    """Imports the given pool by name."""
    try:
        res = subprocess.run(
            ["/usr/sbin/zpool", "import", "-o", "cachefile=none", poolname],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except subprocess.CalledProcessError as err:
        return False, err
    return True, None


def get_multihost(poolname: str) -> str:
    res = subprocess.run(
        ["/usr/sbin/zpool", "get", "-H", "-o", "value", "multihost", poolname],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return res.stdout.decode().strip()


def disable_multihost(poolname: str):
    subprocess.run(
        ["/usr/sbin/zpool", "set", "multihost=off", poolname],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def fail_cmd(module, msg: str, err: Exception, poolname: str):
    # In practice there is no other possible type. This is being done to ease
    # code autocompletion.
    if isinstance(err, subprocess.CalledProcessError):
        module.fail_json(
            **{
                "msg": msg,
                "poolname": poolname,
                "cmd": err.cmd,
                "returncode": err.returncode,
                "stdout": err.stdout.decode().strip() if err.stdout else "",
                "stderr": err.stderr.decode().strip() if err.stderr else "",
                "changed": False,
            }
        )
    module.fail_json(
        **{"msg": msg, "poolname": poolname, "err": str(err), "changed": False}
    )


def run_module():
    module_args = dict(
        poolname=dict(type="str", required=True),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=True)

    poolname = module.params["poolname"]

    imported, online = pool_imported_and_online(poolname)

    if imported and not online:
        module.fail_json(
            **{
                "msg": "pool already imported but not online",
                "poolname": poolname,
                "changed": False,
            }
        )

    if not imported:
        if module.check_mode:
            module.exit_json(
                **{
                    "message": "pool would be imported and multihost disabled",
                    "poolname": poolname,
                    "changed": True,
                }
            )
        ok, err = import_pool(poolname)
        if not ok:
            fail_cmd(module, "pool import unsuccessful", err, poolname)

    # Pools managed here must never have multihost (MMP) enabled.
    try:
        multihost = get_multihost(poolname)
    except (subprocess.CalledProcessError, OSError) as err:
        fail_cmd(module, "unable to read pool multihost property", err, poolname)

    multihost_changed = multihost != "off"
    if multihost_changed and not module.check_mode:
        try:
            disable_multihost(poolname)
        except (subprocess.CalledProcessError, OSError) as err:
            fail_cmd(module, "unable to disable pool multihost property", err, poolname)

    module.exit_json(
        **{
            "message": "pool imported successfully" if not imported else "pool already imported and online",
            "poolname": poolname,
            "imported": not imported,
            "multihost_disabled": multihost_changed,
            "changed": (not imported) or multihost_changed,
        }
    )


def main():
    run_module()


if __name__ == "__main__":
    main()
