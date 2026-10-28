import ipaddress


def is_ipv4_cidr(value):
    """True if value is an IPv4 host address with an explicit prefix, e.g. 10.0.0.5/24."""
    if not isinstance(value, str) or value.count("/") != 1:
        return False
    try:
        ipaddress.IPv4Interface(value)
    except ValueError:
        return False
    return True


class TestModule:
    def tests(self):
        return {"ipv4_cidr": is_ipv4_cidr}
