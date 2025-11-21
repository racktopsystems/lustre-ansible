#!/usr/bin/env python3

import os
import subprocess
from typing import Any, Dict, List

from ansible.module_utils.basic import AnsibleModule


class InvalidNumberOfKeys(Exception):
    pass


class MissingPoolException(Exception):
    pass


class LustreFilesystem:
    def __init__(self, poolname: str, mapping: Dict[str, Any], fsname="bsrfs"):
        if len(mapping) > 1:
            raise InvalidNumberOfKeys(f"dict must have one key/value pair: '{mapping}'")

        key = mapping.__iter__().__next__()
        settings = mapping[key]

        self._poolname: str = poolname
        self._fsname: str = fsname
        self._data: Dict[str, Any] = mapping
        self._dataset_name: str = key
        if len(self._dataset_name) < 5:
            raise ValueError("dataset name cannot be shorter than 5 symbols")
        self._index: int = settings.get("index", -1)  # set -1 as a sentinel
        self._mgsnode: List[str] = settings.get("mgsnode")
        self._mkfsopts: Dict[str, str] = settings["mkfsopts"]
        self._servicenode: List[str] = settings["servicenode"]

    @property
    def dataset_name(self) -> str:
        return self._dataset_name

    @property
    def index(self) -> int:
        return self._index

    @property
    def target_type(self) -> str:
        target_types = set(["ost", "mgt", "mdt"])
        prefix = self._dataset_name[:3]
        if prefix not in target_types:
            raise ValueError(
                f"cannot determine target type from name: '{self._dataset_name}'"
            )
        return prefix

    @property
    def fmt_target_type(self) -> str:
        return f"--{self.target_type}"

    @property
    def fmt_mkfsoptions(self) -> str:
        opts = " -o ".join([f"{k}={v}" for k, v in self._mkfsopts.items()])
        return f"{opts}"

    def fmt_servicenode(self):
        for n in self._servicenode:
            yield f"--servicenode={n}"

    def fmt_mgsnode(self):
        if not self._mgsnode:
            return
        for n in self._mgsnode:
            if self.target_type == "ost" or self.target_type == "mdt":
                yield f"--mgsnode={n}"
            else:
                break

    def format_command(
        self, echo: bool = False, reformat: bool = False, dryrun: bool = False
    ) -> List[str]:
        return [
            elem
            for elem in (
                "echo" if echo else None,
                "mkfs.lustre",
                "--reformat" if reformat else None,
                "--dryrun" if dryrun else None,
                "--fsname=" + self._fsname,
                self.fmt_target_type,
                (
                    ("--index=" + str(self._index))
                    if self.target_type == "ost"
                    or self.target_type == "mdt"
                    and self._index != -1
                    else None
                ),
                *self.fmt_mgsnode(),
                *self.fmt_servicenode(),
                "--mkfsoptions=" + self.fmt_mkfsoptions,
                "--backfstype=zfs",
                os.path.join(self._poolname, self._dataset_name),
            )
            if elem is not None
        ]


def filesystems(poolname: str) -> List[str]:
    # libzfs_core delivered via python3-pyzfs 2.1.15-2.el8 does not, for
    # whatever reason suppoprt seemingly basic operations like listing children.
    # For this reason we are exec'ing `zfs` command instead of relying on
    # libzfs_core.
    datasets = (
        subprocess.check_output(["zfs", "list", "-r", "-H", "-o", "name", poolname])
        .decode()
        .split()
    )
    return datasets


def execute_cmd(cmd: List[str], run_cmd_func=subprocess.check_output):
    """
    Wrapper function for subprocess.check_output; allows for simplified testing
    of commands by swapping out the function passed in via `run_cmd_func`.
    """
    try:
        return (
            run_cmd_func(
                cmd,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            ),
            None,
        )
    except subprocess.CalledProcessError as err:
        return None, err


def main():
    module_args = dict(
        poolname=dict(type="str", required=True),
        details=dict(type="list", required=True),
        dryrun=dict(type="bool", required=False),
        echo=dict(type="bool", required=False),
        reformat=dict(type="bool", required=False),
    )

    module = AnsibleModule(argument_spec=module_args)
    details: Any = module.params["details"]
    dryrun = module.params["dryrun"] or False
    echo = module.params["echo"] or False
    poolname: str = module.params["poolname"]
    reformat = module.params["reformat"] or False

    results = []
    # List of all filesystems on the system, including the top-level, i.e.
    # p<something>, e.g. `p01`.
    existing_filesystems = filesystems(poolname)

    # Check if the pool exists on this system.
    if poolname not in existing_filesystems:
        raise MissingPoolException(f"poolname {poolname} missing")

    for dataset in details:
        o = LustreFilesystem(poolname, dataset)
        # Check if the dataset already exists, meaning it was created
        # previously.
        if os.path.join(poolname, o.dataset_name) in existing_filesystems:
            continue

        # Generate the command line to be passed to `subprocess.check_output`.
        cmd = o.format_command(echo, reformat, dryrun)

        # Execute generated command and add its result to the list of results.
        # We do this for each filesystem that must be created.
        output, err = execute_cmd(cmd)

        # On error we terminate the module and return the error.
        if err:
            module.fail_json(
                changed=False,
                msg=err.stdout,
                command=" ".join(err.cmd),
                retcode=err.returncode,
                args=err.args[1],
            )

        results.append(output)

    # Once we are done processing all datasets we exit returning results.
    unchanged = any([dryrun, echo, len(results) == 0])
    module.exit_json(changed=not unchanged, results=results)


if __name__ == "__main__":
    main()
