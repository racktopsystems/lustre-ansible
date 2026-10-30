"""Jinja filters that let the HA tasks leave hiavd's files alone unless the
inventory really asks for a change.

hiavd rewrites its own files: hiavd.conf (with its own header and any keys
it adds) and identifiers.dat (where it also keeps this node's keypair). A
byte-for-byte comparison with the Ansible template therefore always differs,
and rewriting the files restarts hiavd and, for identifiers.dat, throws away
the node's identity. These filters compare what matters instead.
"""

import json
import re

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    tomllib = None


def _scalar(text):
    text = text.strip()
    if text in ("true", "false"):
        return text == "true"
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1]
    try:
        return json.loads(text)  # "strings", numbers, [arrays]
    except ValueError:
        return text


def _parse_simple(text):
    """Enough TOML for hiavd.conf: comments, key = value, [table] and
    [[array of tables]], for Pythons without tomllib."""
    root, current = {}, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\[\[\s*([^\]]+?)\s*\]\]$", line)
        if m:
            current = {}
            root.setdefault(m.group(1), []).append(current)
            continue
        m = re.match(r"^\[\s*([^\]]+?)\s*\]$", line)
        if m:
            current = root.setdefault(m.group(1), {})
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError("cannot parse line: %r" % raw)
        (current if current is not None else root)[key.strip()] = _scalar(value)
    return root


def hiavd_conf_parse(text):
    """Parse hiavd.conf (TOML) into a dict."""
    text = text or ""
    if tomllib is not None:
        return tomllib.loads(text)
    return _parse_simple(text)


def _nodes(conf, keys):
    nodes = [{k: n.get(k) for k in keys} for n in conf.get("ClusterNodes") or []]
    return sorted(nodes, key=lambda n: (str(n.get("Guid")), str(n.get("Name"))))


def hiavd_conf_differs(current, desired):
    """Whether the hiavd.conf on the node (current text, '' if missing)
    differs from the rendered template (desired text) in any setting the
    template sets. Comments and header lines, the order of the cluster
    nodes, and settings hiavd adds that the template does not set are
    ignored. A missing or unreadable file differs."""
    want = hiavd_conf_parse(desired)
    try:
        have = hiavd_conf_parse(current)
    except ValueError:
        return True
    if not have:
        return True
    for key, value in want.items():
        if key == "ClusterNodes":
            keys = sorted({k for n in value for k in n})
            if _nodes(have, keys) != _nodes(want, keys):
                return True
        elif have.get(key) != value:
            return True
    return False


def hiavd_ids_plan(current, cluster_id, cluster_guid, force=False):
    """Decide what to do with identifiers.dat.

    The cluster IDs must never change once a cluster exists (hiavd and the
    NFS server rely on them), and hiavd keeps the node's keypair in the same
    file. So the file is written only when it has no cluster IDs yet (it is
    missing, or hiavd created it with only the keypair), or when `force` is
    set; either way every other field, the keypair included, is kept.

    Returns {"write": bool, "content": str, "mismatch": bool}, where
    mismatch reports existing IDs that differ from the computed ones.
    """
    try:
        ids = json.loads(current) if (current or "").strip() else {}
    except ValueError:
        ids = {}
    if not isinstance(ids, dict):
        ids = {}
    have_ids = bool(ids.get("ClusterId")) and bool(ids.get("ClusterGuid"))
    mismatch = have_ids and (
        int(ids["ClusterId"]) != int(cluster_id)
        or str(ids["ClusterGuid"]).lower() != str(cluster_guid).lower()
    )
    write = (not have_ids) or (bool(force) and mismatch)
    merged = dict(ids)
    if write:
        merged["ClusterId"] = int(cluster_id)
        merged["ClusterGuid"] = str(cluster_guid)
    # The field order and compact form hiavd itself writes.
    order = ["ClusterId", "ClusterGuid", "PrivateKey", "PublicKey"]
    ordered = {k: merged[k] for k in order if k in merged}
    ordered.update({k: v for k, v in merged.items() if k not in ordered})
    return {
        "write": write,
        "content": json.dumps(ordered, separators=(",", ":")),
        "mismatch": bool(mismatch),
    }


class FilterModule:
    def filters(self):
        return {
            "hiavd_conf_differs": hiavd_conf_differs,
            "hiavd_ids_plan": hiavd_ids_plan,
        }
