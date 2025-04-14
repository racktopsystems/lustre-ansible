#!/usr/bin/env python3

from ansible.module_utils.basic import AnsibleModule
import base64
import zipfile
import tempfile
import os


def dec_and_extr(module: AnsibleModule):
    """Extracts the required file from the supplied base64 encoded archive."""

    dest = module.params["dest"]
    src = module.params["src"]
    need_file = module.params["file_to_extract"]
    remove_src = module.params["remove_encoded"]
    failed = False
    result = dict(changed=False, message="")

    try:
        # Read encoded content
        with open(src, "rb") as f:
            encoded = f.read()

        # Decode and write to temp file
        decoded = base64.b64decode(encoded)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(decoded)
            tmp_path = tmp.name

        # Extract ZIP contents
        with zipfile.ZipFile(tmp_path, "r") as zip_ref:
            zip_ref.extract(need_file, dest)

        # Cleanup and optional source removal
        os.unlink(tmp_path)
        if remove_src:
            os.remove(src)

        result.update(changed=True, message=f"Decoded and extracted to {dest}")

    except Exception as e:
        failed = True
        result.update(changed=False, message=str(e))

    return result, not failed


def run_module():
    module_args = dict(
        creates=dict(type="str", required=False, default=""),
        src=dict(type="str", required=True),
        dest=dict(type="str", required=True),
        file_to_extract=dict(type="str", required=False, default="licenses.txt"),
        remove_encoded=dict(type="bool", default=False),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=False)

    if module.params["creates"]:
        try:
            _ = os.stat(module.params["creates"])
            result = dict(
                changed=False,
                message=f'File {module.params["creates"]} exists on the destination',
            )
            module.exit_json(**result)
        except IOError:
            pass

    result, ok = dec_and_extr(module)

    if not ok:
        module.fail_json(msg="base64 decode or extraction failed", **result)

    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
