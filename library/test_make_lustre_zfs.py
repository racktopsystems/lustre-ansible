from subprocess import CalledProcessError
import unittest
from .make_lustre_zfs import execute_cmd, LustreFilesystem


class TestMakeLustreZFSDatasets(unittest.TestCase):
    def test_format_command_output_is_expected(self):
        """Validate output of LustreFilesystem.format_command(...) with known inputs"""
        poolname = "p01"
        inputs = [
            {
                "ost01": {
                    "index": 0,
                    "mkfsopts": {
                        "recordsize": "1M",
                        "compression": "lz4",
                        "mountpoint": "none",
                    },
                    "mgsnode": ["192.168.2.21@o2ib", "192.168.2.23@o2ib"],
                    "servicenode": ["192.168.2.25@o2ib", "192.168.2.27@o2ib"],
                }
            },
            {
                "ost02": {
                    "index": 1,
                    "mkfsopts": {
                        "recordsize": "1M",
                        "compression": "lz4",
                        "mountpoint": "none",
                    },
                    "mgsnode": ["192.168.2.21@o2ib", "192.168.2.23@o2ib"],
                    "servicenode": ["192.168.2.25@o2ib", "192.168.2.27@o2ib"],
                }
            },
            {
                "mgt01": {
                    "index": 0,
                    "mkfsopts": {
                        "recordsize": "128K",
                        "compression": "lz4",
                        "mountpoint": "none",
                    },
                    "mgsnode": ["192.168.2.21@o2ib", "192.168.2.23@o2ib"],
                    "servicenode": ["192.168.2.25@o2ib", "192.168.2.27@o2ib"],
                }
            },
            {
                "mdt02": {
                    "index": 1,
                    "mkfsopts": {
                        "recordsize": "1M",
                        "compression": "lz4",
                        "mountpoint": "none",
                    },
                    "mgsnode": ["192.168.2.21@o2ib", "192.168.2.23@o2ib"],
                    "servicenode": ["192.168.2.25@o2ib", "192.168.2.27@o2ib"],
                }
            },
        ]

        expected_outputs = [
            (
                "mkfs.lustre",
                "--fsname=bsrfs",
                "--ost",
                "--index=0",
                "--mgsnode=192.168.2.21@o2ib",
                "--mgsnode=192.168.2.23@o2ib",
                "--servicenode=192.168.2.25@o2ib",
                "--servicenode=192.168.2.27@o2ib",
                '--mkfsoptions="recordsize=1M -o compression=lz4 -o mountpoint=none"',
                "--backfstype=zfs",
                "p01/ost01",
            ),
            (
                "mkfs.lustre",
                "--fsname=bsrfs",
                "--ost",
                "--index=1",
                "--mgsnode=192.168.2.21@o2ib",
                "--mgsnode=192.168.2.23@o2ib",
                "--servicenode=192.168.2.25@o2ib",
                "--servicenode=192.168.2.27@o2ib",
                '--mkfsoptions="recordsize=1M -o compression=lz4 -o mountpoint=none"',
                "--backfstype=zfs",
                "p01/ost02",
            ),
            (
                "mkfs.lustre",
                "--fsname=bsrfs",
                "--mgt",
                "--servicenode=192.168.2.25@o2ib",
                "--servicenode=192.168.2.27@o2ib",
                '--mkfsoptions="recordsize=128K -o compression=lz4 -o mountpoint=none"',
                "--backfstype=zfs",
                "p01/mgt01",
            ),
            (
                "mkfs.lustre",
                "--fsname=bsrfs",
                "--mdt",
                "--index=1",
                "--mgsnode=192.168.2.21@o2ib",
                "--mgsnode=192.168.2.23@o2ib",
                "--servicenode=192.168.2.25@o2ib",
                "--servicenode=192.168.2.27@o2ib",
                '--mkfsoptions="recordsize=1M -o compression=lz4 -o mountpoint=none"',
                "--backfstype=zfs",
                "p01/mdt02",
            ),
        ]

        for idx, content in enumerate(inputs):
            o = LustreFilesystem(poolname, content)
            self.assertSequenceEqual(o.format_command(), expected_outputs[idx])

    def test_execute_cmd_exception_handling(self):
        """Validate correct exception handling in execute_cmd(...)"""

        def exec_func_raises_exception(cmd, **_):
            raise CalledProcessError(returncode=1, cmd=cmd, output=b"poof!", stderr=b"")

        def exec_func_raises_unhanded_exception(cmd, **_):
            raise ValueError("unspecified error")

        inputs = [
            {
                "data": ["this", "is", "a", "command"],
                "exec_func": exec_func_raises_exception,
                "handled": True,
                "unhandled_exception": None,
            },
            {
                "data": ["this", "is", "a", "command"],
                "exec_func": exec_func_raises_unhanded_exception,
                "handled": False,
                "unhandled_exception": ValueError,
            },
        ]
        for idx, input in enumerate(inputs):
            if input["handled"]:
                res, err = execute_cmd(input["data"], input["exec_func"])
            # Validates a case of an exception which the execute_cmd function
            # is not supposed to handle.
            else:
                with self.assertRaises(input["unhandled_exception"]):
                    res, err = execute_cmd(input["data"], input["exec_func"])
            self.assertIsNone(res)
            self.assertIsNotNone(err)
            self.assertEqual(err.returncode, 1)
            self.assertEqual(err.output, b"poof!")

    def test_missing_index_value(self):
        """Missing index field should default to a sentinel value"""
        inputs = [
            {
                "ost01": {
                    "mkfsopts": {},
                    "mgsnode": [],
                    "servicenode": [],
                }
            },
        ]

        for idx, input in enumerate(inputs):
            c = LustreFilesystem("ptest", input)
            self.assertEqual(c.index, -1)

    def test_fmt_target_type(self):
        """Target type must be correctly detected and formatted based on dataset name"""
        inputs = [
            {
                "ost01": {
                    "index": 0,
                    "mkfsopts": {},
                    "mgsnode": [],
                    "servicenode": [],
                }
            },
            {
                "ost02": {
                    "index": 0,
                    "mkfsopts": {},
                    "mgsnode": [],
                    "servicenode": [],
                }
            },
            {
                "mdt01": {
                    "index": 0,
                    "mkfsopts": {},
                    "mgsnode": [],
                    "servicenode": [],
                }
            },
            {
                "mgt01": {
                    "index": 0,
                    "mkfsopts": {},
                    "mgsnode": [],
                    "servicenode": [],
                }
            },
        ]
        expected_outputs = (
            "--ost",
            "--ost",
            "--mdt",
            "--mgt",
        )
        for idx, input in enumerate(inputs):
            c = LustreFilesystem("ptest", input)
            self.assertEqual(c.fmt_target_type, expected_outputs[idx])

    def test_no_mgs_nodes_in_mgt_mkfs_command(self):
        """Formatted command string for the MGS dataset creation must not include any --mgsnode args"""
        inputs = [
            {
                "mgt01": {
                    "index": 0,
                    "mkfsopts": {
                        "recordsize": "128K",
                        "compression": "lz4",
                        "mountpoint": "none",
                    },
                    "servicenode": ["192.168.2.25@o2ib", "192.168.2.27@o2ib"],
                }
            },
            {
                "mgt01": {
                    "index": 0,
                    "mkfsopts": {
                        "recordsize": "128K",
                        "compression": "lz4",
                        "mountpoint": "none",
                    },
                    "mgsnode": ["192.168.2.21@o2ib", "192.168.2.23@o2ib"],
                    "servicenode": ["192.168.2.25@o2ib", "192.168.2.27@o2ib"],
                }
            },
        ]
        for idx, input in enumerate(inputs):
            c = LustreFilesystem("ptest", input)
            cmd_list = c.format_command()
            for arg in cmd_list:
                self.assertFalse(
                    arg.startswith("--mgsnode"),
                    f"argument[{idx}]: unexpected argument '{arg}'",
                )
