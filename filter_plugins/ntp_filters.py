"""Jinja filter for tasks/ntp-setup.yml."""

import re

BEGIN = "# BEGIN NTP servers managed by Ansible"
END = "# END NTP servers managed by Ansible"
SOURCE = re.compile(r"^\s*(server|pool)\s")


def chrony_with_servers(current, servers, options="iburst"):
    """chrony.conf text with its time sources replaced.

    Every `server` and `pool` line of `current` is dropped, and a marked
    block with one `server <host> <options>` line per entry of `servers` is
    put at the top. All other lines are kept as they are. The result is the
    same however often it is applied.
    """
    kept = [
        line
        for line in (current or "").splitlines()
        if not SOURCE.match(line) and line.strip() not in (BEGIN, END)
    ]
    while kept and not kept[0].strip():
        kept.pop(0)
    block = [BEGIN]
    block += [" ".join(("server %s %s" % (s, options or "")).split()) for s in servers]
    block.append(END)
    return "\n".join(block + ([""] + kept if kept else [])) + "\n"


class FilterModule:
    def filters(self):
        return {"chrony_with_servers": chrony_with_servers}
