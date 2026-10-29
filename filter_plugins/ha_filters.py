"""Jinja filters for the HA tasks."""

import json


def hwadm_pool_names(stdout):
    """Names of the pools in `hwadm -j ls p` output; [] when the output is
    empty or not JSON (hwadm failed), so a caller reports the pools missing
    rather than failing to parse."""
    try:
        pools = json.loads(stdout or "null")
    except ValueError:
        return []
    return [p.get("Name") for p in pools or [] if isinstance(p, dict)]


class FilterModule:
    def filters(self):
        return {"hwadm_pool_names": hwadm_pool_names}
