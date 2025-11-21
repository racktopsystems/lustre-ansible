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

    if imported:
        module.exit_json(
            **{
                "message": "pool already imported and online",
                "poolname": poolname,
                "changed": False,
            }
        )

    ok, err = import_pool(poolname)

    if ok:
        module.exit_json(
            **{
                "message": "pool imported successfully",
                "poolname": poolname,
                "changed": True,
            }
        )

    # In practice there is no other possible type. This is being done to ease
    # code autocompletion.
    if isinstance(err, subprocess.CalledProcessError):
        module.fail_json(
            **{
                "msg": "pool import unsuccessful",
                "cmd": err.cmd,
                "returncode": err.returncode,
                "stdout": err.stdout,
                "stderr": err.stderr,
                "changed": False,
            }
        )
    else:
        module.fail_json(
            **{"msg": "pool import could not run", "err": str(err), "changed": False}
        )


def main():
    run_module()


if __name__ == "__main__":
    main()
