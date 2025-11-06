#!/usr/bin/env python3
import uuid

from ansible.module_utils.basic import AnsibleModule


FNV_32_PRIME = 0x01000193
FNV1A_32_INIT = 0x811C9DC5


def byte_xor(ba1, ba2):
    return bytes(a ^ b for a, b in zip(ba1, ba2))


def fnva(data, hval_init, fnv_prime, fnv_size):
    """
    Alternative FNV hash algorithm used in FNV-1a.
    """
    assert isinstance(data, bytes)

    hval = hval_init
    for byte in data:
        hval = hval ^ byte
        hval = (hval * fnv_prime) % fnv_size
    return hval


def fnv1a_32(data, hval_init=FNV1A_32_INIT):
    """
    Returns the 32 bit FNV-1a hash value for the given data.
    """
    return fnva(data, hval_init, FNV_32_PRIME, 2**32)


def main():
    module_args = dict(
        uuid1=dict(type="str", required=True),
        uuid2=dict(type="str", required=True),
    )

    module = AnsibleModule(argument_spec=module_args, supports_check_mode=False)

    uuid_1 = module.params["uuid1"]
    uuid_2 = module.params["uuid2"]

    uuid_1_as_bytes = uuid.UUID(uuid_1).bytes
    uuid_2_as_bytes = uuid.UUID(uuid_2).bytes

    xored_uuid_as_bytes = byte_xor(uuid_1_as_bytes, uuid_2_as_bytes)
    fnv_hash = fnv1a_32(xored_uuid_as_bytes)
    new_uuid = uuid.UUID(bytes=xored_uuid_as_bytes)

    results = {"guid_hash": fnv_hash, "guid": new_uuid.__str__()}
    module.exit_json(changed=False, **results)


if __name__ == "__main__":
    main()
