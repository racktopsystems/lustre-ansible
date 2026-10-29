"""Jinja filters for LNET network and Multi-Rail peer configuration.

LNET names instance 0 of a network two ways: "o2ib" and "o2ib0" are the same
network, and "10.0.0.1@o2ib" and "10.0.0.1@o2ib0" the same NID. lnetctl, and
so lustreadm, report the short form. Everything here compares in that
canonical form.

A peer is written the way `lustreadm lnet --peer` takes it: its primary NID
followed by its other NIDs, comma-separated, e.g.
"10.0.0.2@o2ib,10.1.0.2@o2ib1".
"""

import re

_TRAILING_NUM = re.compile(r"^(.*?)(\d*)$")


def lnet_net_name(name):
    """Canonical form of a network name: "o2ib0" -> "o2ib", "o2ib1" stays."""
    name = str(name)
    net_type, num = _TRAILING_NUM.match(name).groups()
    if not net_type:
        return name
    if not num or int(num) == 0:
        return net_type
    return "%s%d" % (net_type, int(num))


def lnet_nid(nid):
    """Canonical form of a NID: "10.0.0.1@o2ib0" -> "10.0.0.1@o2ib"."""
    nid = str(nid).strip()
    addr, sep, net = nid.partition("@")
    if not sep:
        return nid
    return addr + "@" + lnet_net_name(net)


def lnet_nid_net(nid):
    """Canonical network name a NID is on: "10.0.0.1@o2ib0" -> "o2ib"."""
    return lnet_net_name(str(nid).partition("@")[2])


def _nids(value):
    """NIDs of one node or peer, from a list or a comma-separated string."""
    if isinstance(value, str):
        value = value.split(",")
    return [lnet_nid(n) for n in value if str(n).strip()]


def lnet_node(nids):
    """One node or peer as lustreadm takes it: canonical NIDs, comma-joined,
    in order, without duplicates."""
    seen, out = set(), []
    for nid in _nids(nids):
        if nid not in seen:
            seen.add(nid)
            out.append(nid)
    return ",".join(out)


def lnet_nids_of(nets):
    """All NIDs of a host, in LNET order, from its lustreadm lnet list
    output (a list of networks, or None when it has none)."""
    out = []
    for net in nets or []:
        out.extend(lnet_nid(n) for n in net.get("NIDs") or [])
    return out


def lnet_peer_plan(server_nids, self_host, local_nets, extra_peers=None):
    """Plan the configured peers of one host.

    server_nids maps each Lustre server to its NIDs in LNET order, so its
    first NID is its primary NID. Every server other than self_host becomes
    a Multi-Rail peer carrying all of its NIDs. Its primary NID is its own
    primary NID when this host is on that network, else its first NID on a
    network this host has, since a peer is configured under the network of
    its primary NID. extra_peers adds peers that are not Lustre servers
    (clients, routers), each as "primary,nid,...".

    Returns {"peers": {net: [peer, ...]}, "unreachable": [name, ...]}, with
    an entry in "peers" for every local network, so a network whose peers
    should all go is listed with an empty list.
    """
    nets = [lnet_net_name(n) for n in local_nets]
    peers = {n: [] for n in nets}
    unreachable = []

    candidates = []
    for host in sorted(server_nids):
        if host != self_host:
            candidates.append((host, _nids(server_nids[host]), True))
    for spec in extra_peers or []:
        candidates.append((str(spec), _nids(spec), False))

    planned = set()
    for name, nids, reorder in candidates:
        if not nids:
            unreachable.append(name)
            continue
        primary = nids[0]
        if lnet_nid_net(primary) not in peers:
            local = [n for n in nids if lnet_nid_net(n) in peers]
            # A peer given explicitly keeps the primary NID it was given.
            if not reorder or not local:
                unreachable.append(name)
                continue
            primary = local[0]
        if primary in planned:
            continue  # listed both as a server and as an extra peer
        planned.add(primary)
        rest = [n for n in nids if n != primary]
        peers[lnet_nid_net(primary)].append(lnet_node([primary] + rest))

    for net in peers:
        peers[net].sort()
    return {"peers": peers, "unreachable": unreachable}


def lnet_peers_differ(current, desired):
    """Whether the configured peers of a network (lustreadm lnet list
    "Peers") differ from the desired peer strings. Peers found by discovery
    and not configured are ignored, as lustred leaves them to LNET."""
    have = {}
    for p in current or []:
        if p.get("Configured"):
            nids = set(_nids(p.get("NIDs") or [])) | {lnet_nid(p["PrimaryNID"])}
            have[lnet_nid(p["PrimaryNID"])] = nids
    want = {}
    for spec in desired or []:
        nids = _nids(spec)
        want[nids[0]] = set(nids)
    return have != want


class FilterModule:
    def filters(self):
        return {
            "lnet_net_name": lnet_net_name,
            "lnet_nid": lnet_nid,
            "lnet_nid_net": lnet_nid_net,
            "lnet_node": lnet_node,
            "lnet_nids_of": lnet_nids_of,
            "lnet_peer_plan": lnet_peer_plan,
            "lnet_peers_differ": lnet_peers_differ,
        }
