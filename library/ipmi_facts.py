#!/usr/bin/env python3

import os
import subprocess

from ansible.module_utils.basic import AnsibleModule


def extract_ip_address(output):
    for line in output.splitlines():
        if line.startswith("IP Address ") and not "Source" in line:
            return line.split(":")[1][1:]


def main():
    module = AnsibleModule(argument_spec={}, supports_check_mode=True)
    try:
        if not os.path.exists("/dev/ipmi0"):
            facts = {"ipmi_ip_address": "0.0.0.0", "ipmi_present": False}
            module.exit_json(changed=False, ansible_facts=facts)
        # Run the command
        res = subprocess.check_output(
            "/usr/bin/ipmitool lan print 3".split(), universal_newlines=True
        )
        # Parse and return structured data
        ip_address = extract_ip_address(res)
        facts = {"ipmi_ip_address": ip_address, "ipmi_present": False}
        module.exit_json(changed=False, ansible_facts=facts)
    except subprocess.CalledProcessError as e:
        module.fail_json(msg=f"Command failed: {e}")
    except Exception as e:
        module.fail_json(msg=f"Error: {str(e)}")


if __name__ == "__main__":
    main()
