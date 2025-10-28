#!/usr/bin/env python3

import json
import subprocess

from ansible.module_utils.basic import AnsibleModule


# @dataclass
class Registration:
    def __init__(self, version: int, customer: str, serial: str, created: str):
        self.version = version
        self.customer = customer
        self.serial = serial
        self.created = created


def get_system_registration(output: str):
    try:
        decoded = json.loads(output)
        return (
            Registration(
                decoded["Version"],
                decoded["Customer"],
                decoded["Serial"],
                decoded["Created"],
            ),
            None,
        )
    except json.decoder.JSONDecodeError as e:
        return Registration(-1, "", "", ""), e.msg


def main():
    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    try:
        # Run the command
        res = subprocess.check_output(
            "bsradm -j per view".split(),
            # Send STDERR to STDOUT to handle the system unregistered case.
            # In this case the JSON object with an error and lack of
            # registration indication is written to STDERR instead of STDOUT.
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        # Parse and return structured data
        registration, msg = get_system_registration(res)
        # If there is a message, we encountered an error decoding JSON data.
        if msg:
            module.fail_json(msg=f"Error: {msg}")

        facts = {
            "persona": {
                "version": registration.version,
                "customer": registration.customer,
                "serial": registration.serial,
                "created": registration.created,
            },
            "system_is_registered": True,
        }
        module.exit_json(changed=False, ansible_facts=facts)
    except subprocess.CalledProcessError:
        module.exit_json(
            changed=False,
            ansible_facts={
                "persona": {
                    "version": -1,
                    "customer": "na",
                    "serial": "na",
                    "created": "na",
                },
                "system_is_registered": False,
            },
        )
        # module.fail_json(msg=f"Command failed: {e}")
    except Exception as e:
        module.fail_json(msg=f"Error: {str(e)}")


if __name__ == "__main__":
    main()
