#!/usr/bin/env python3
import hashlib
import os

from ansible.module_utils.basic import AnsibleModule


def replace_name_and_device(lines: list, device: str) -> list:
    new_lines = []
    for line in lines:
        if line.startswith("NAME"):
            new_lines.append(f"NAME={device}\n")
        elif line.startswith("DEVICE"):
            new_lines.append(f"DEVICE={device}\n")
        else:
            new_lines.append(line)
    return new_lines


def compute_digest(path: str) -> str:
    try:
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read(4096))
            return digest.hexdigest()
    except IOError:
        return ""


def tokenize_config_file(path: str) -> [list, Exception]:
    lines = []
    try:
        with open(path, "rt") as f:
            lines = f.readlines()
    except IOError as e:
        return list(), e
    return lines, None


def write_new_config_file(path: str, device: str, dest: str):
    tokens, e = tokenize_config_file(path)
    if e:
        return False, ("nodigest", "nodigest"), e
    new_tokens = replace_name_and_device(tokens, device)
    original_content = "".join(tokens)
    new_content = "".join(new_tokens)
    original_digest = hashlib.sha256(original_content.encode()).hexdigest()
    new_digest = hashlib.sha256(new_content.encode()).hexdigest()
    if original_digest == new_digest:
        return False, (new_digest, original_digest), None
    # Content changed
    try:
        with open(dest, "wt") as f:
            # If this fails an exception will be raised, which should cause the
            # module to fail.
            _ = f.write(new_content)
            return True, (new_digest, original_digest), None
    except IOError as e:
        return False, (new_digest, original_digest), e


def copy_file(dest: str, src: str) -> (bool, Exception):
    try:
        dest_f = open(dest, "wb")
        src_f = open(src, "rb")
        while True:
            data = src_f.read(4096)
            if not data:
                break
            dest_f.write(data)
    except IOError as e:
        return False, e
    dest_f.close()
    src_f.close()
    return True, None


def fail_module(module, msg: str, err: Exception):
    module.fail_json(
        **dict(
            msg=msg,
            changed=False,
            errmsg=err.strerror,
            errno=err.errno,
            filename=err.filename,
        )
    )


def run_module():
    module_args = dict(
        old_device=dict(type="str", required=True),
        new_device=dict(type="str", required=True),
        dest=dict(type="str", required=False),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=False)

    old_device_name = module.params["old_device"]
    new_device_name = module.params["new_device"]

    src = f"/etc/sysconfig/network-scripts/ifcfg-{old_device_name}"
    dest = f"/etc/sysconfig/network-scripts/ifcfg-{new_device_name}"

    # Change destination filename if it is being explicitly specified.
    if module.params["dest"]:
        dest = module.params["dest"]

    tmp_dest = os.path.join("/tmp", new_device_name)

    changed, digests, err = write_new_config_file(src, new_device_name, tmp_dest)

    if err:
        fail_module(
            module,
            f"ensure {old_device_name} and {new_device_name} device names are correct and destination if set is writeable",
            err,
        )

    # If the destination file exists, check that it contains effectively the
    # same content as the source file _after_ making changes.
    if os.path.exists(dest):
        existing_dest_digest = compute_digest(dest)

        # We don't need to do anything if the destination exists and content matches.
        if existing_dest_digest == digests[0]:
            module.exit_json(
                **dict(
                    msg="destination exists and content matches desired state",
                    dest=dest,
                    changed=False,
                ),
            )

    if changed:
        ok, err = copy_file(dest, tmp_dest)
        if not ok:
            fail_module(module, f"failed copying from {tmp_dest} to {dest}", err)

    module.exit_json(
        **dict(dest=dest, changed=changed),
    )


def main():
    run_module()


if __name__ == "__main__":
    main()
