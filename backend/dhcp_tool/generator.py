"""Deterministic, allowlisted ISC DHCPv4 configuration generator.

No user-provided text is ever emitted as a raw directive.
"""

import ipaddress
import re


class ConfigurationError(ValueError):
    """Invalid configuration; message identifies the offending field."""


_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,62}\Z", re.ASCII)
_DOMAIN = re.compile(
    r"(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\Z",
    re.ASCII,
)
_MAC = re.compile(r"[0-9a-fA-F]{2}([:\-])[0-9a-fA-F]{2}(?:\1[0-9a-fA-F]{2}){4}\Z", re.ASCII)
_PROFILES = {"R81.10", "R82.10"}


def _fields(data, allowed, path):
    if not isinstance(data, dict):
        raise ConfigurationError(f"{path}: expected object")
    unknown = data.keys() - allowed
    if unknown:
        raise ConfigurationError(f"{path}: unsupported fields: {', '.join(sorted(unknown))}")


def _items(data, key, path):
    value = data.get(key, [])
    if not isinstance(value, list):
        raise ConfigurationError(f"{path}.{key}: expected list")
    return value


def _name(value, field):
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ConfigurationError(f"{field}: invalid identifier")
    return value


def _address(value, field):
    if not isinstance(value, str):
        raise ConfigurationError(f"{field}: invalid IPv4 address")
    try:
        return ipaddress.IPv4Address(value)
    except (ValueError, TypeError, ipaddress.AddressValueError):
        raise ConfigurationError(f"{field}: invalid IPv4 address") from None


def _network(value, field):
    if not isinstance(value, str):
        raise ConfigurationError(f"{field}: invalid or unsupported CIDR")
    try:
        network = ipaddress.IPv4Network(value, strict=True)
        if network.prefixlen >= 31:
            raise ValueError("/31 and /32 not supported")
        return network
    except (ValueError, TypeError):
        raise ConfigurationError(f"{field}: invalid or unsupported CIDR") from None


def _lease(value, field):
    if type(value) is not int or value <= 0 or value > 2147483647:
        raise ConfigurationError(f"{field}: lease time must be a positive integer")
    return value


def _mac(value, field):
    if not isinstance(value, str) or not _MAC.fullmatch(value):
        raise ConfigurationError(f"{field}: invalid MAC address")
    return value.replace("-", ":").lower()


def _options(data, path):
    lines = []
    for key, directive in (
        ("default_lease_time", "default-lease-time"),
        ("max_lease_time", "max-lease-time"),
    ):
        if data.get(key) is not None:
            lines.append(f"{directive} {_lease(data[key], path + '.' + key)};")
    if data.get("default_lease_time") is not None and data.get("max_lease_time") is not None:
        if data["default_lease_time"] > data["max_lease_time"]:
            raise ConfigurationError(f"{path}: default lease exceeds maximum lease")
    if data.get("domain") is not None:
        domain = data["domain"]
        if not isinstance(domain, str) or not _DOMAIN.fullmatch(domain):
            raise ConfigurationError(f"{path}.domain: invalid domain")
        lines.append(f'option domain-name "{domain}";')
    if data.get("dns") is not None:
        dns = data["dns"]
        if not isinstance(dns, list) or not 1 <= len(dns) <= 3:
            raise ConfigurationError(f"{path}.dns: expected 1 to 3 DNS addresses")
        lines.append(
            "option domain-name-servers "
            + ", ".join(str(_address(ip, path + ".dns")) for ip in dns)
            + ";"
        )
    return lines


def _active(item):
    value = item.get("active", True)
    if type(value) is not bool:
        raise ConfigurationError("active: expected boolean")
    return value


def render(config):
    """Validate and render an entire config to stable ASCII bytes; never partially render."""
    _fields(
        config,
        {"firewall", "profile", "default_lease_time", "max_lease_time", "domain", "dns", "subnets"},
        "configuration",
    )
    firewall = _name(config.get("firewall"), "firewall")
    profile = config.get("profile")
    if not isinstance(profile, str) or profile not in _PROFILES:
        raise ConfigurationError("profile: unsupported Gaia profile")
    global_options = _options(config, "global")
    subnets = config.get("subnets")
    if isinstance(subnets, list):
        for index, subnet in enumerate(subnets):
            if not isinstance(subnet, dict):
                raise ConfigurationError(f"subnets[{index}]: expected object")
    if not isinstance(subnets, list) or not any(_active(s) for s in subnets):
        raise ConfigurationError("subnets: at least one active subnet required")

    networks = []
    used_macs = set()
    used_ips = set()
    used_ids = set()
    blocks = []
    hosts = []
    for index, subnet in enumerate(subnets):
        path = f"subnets[{index}]"
        _fields(
            subnet,
            {
                "cidr",
                "gateway",
                "interface_address",
                "pools",
                "reservations",
                "active",
                "default_lease_time",
                "max_lease_time",
                "domain",
                "dns",
                "gaia_host_name_fallback",
            },
            path,
        )
        if not _active(subnet):
            continue
        network = _network(subnet.get("cidr"), path + ".cidr")
        if any(network.overlaps(previous) for previous in networks):
            raise ConfigurationError(path + ".cidr: overlapping active subnets")
        networks.append(network)
        forbidden = {network.network_address, network.broadcast_address}
        gateway = subnet.get("gateway")
        if gateway is not None:
            gateway = _address(gateway, path + ".gateway")
            if gateway not in network or gateway in forbidden:
                raise ConfigurationError(path + ".gateway: outside usable subnet")
            forbidden.add(gateway)
        interfaces = subnet.get("interface_address")
        if interfaces is not None:
            interfaces = interfaces if isinstance(interfaces, list) else [interfaces]
            if not 1 <= len(interfaces) <= 64:
                raise ConfigurationError(path + ".interface_address: expected 1 to 64 addresses")
            seen_interfaces = set()
            for value in interfaces:
                field = path + ".interface_address"
                interface = _address(value, field)
                if interface not in network or interface in {
                    network.network_address,
                    network.broadcast_address,
                }:
                    raise ConfigurationError(field + ": outside usable subnet")
                if interface in seen_interfaces:
                    raise ConfigurationError(field + ": duplicate interface address")
                seen_interfaces.add(interface)
                forbidden.add(interface)
        options = _options(subnet, path)
        if (subnet.get("default_lease_time") or config.get("default_lease_time")) and (
            subnet.get("max_lease_time") or config.get("max_lease_time")
        ):
            default = subnet.get("default_lease_time") or config.get("default_lease_time")
            maximum = subnet.get("max_lease_time") or config.get("max_lease_time")
            if default > maximum:
                raise ConfigurationError(path + ": effective default lease exceeds maximum lease")
        host_name_fallback = subnet.get("gaia_host_name_fallback", False)
        if type(host_name_fallback) is not bool:
            raise ConfigurationError(path + ".gaia_host_name_fallback: expected boolean")
        if host_name_fallback:
            options.append(
                'option host-name = pick(option host-name,\n  concat("dhcp-", binary-to-ascii(10, 8, "-", leased-address)));'
            )
        if gateway is not None:
            options.append(f"option routers {gateway};")
        pools = []
        for pool_index, pool in enumerate(_items(subnet, "pools", path)):
            field = f"{path}.pools[{pool_index}]"
            _fields(pool, {"start", "end", "active"}, field)
            if not _active(pool):
                continue
            start = _address(pool.get("start"), field + ".start")
            end = _address(pool.get("end"), field + ".end")
            if start > end or start not in network or end not in network:
                raise ConfigurationError(field + ": invalid range")
            if any(start <= address <= end for address in forbidden):
                raise ConfigurationError(field + ": range includes reserved address")
            if any(start <= old_end and old_start <= end for old_start, old_end in pools):
                raise ConfigurationError(field + ": overlapping pools")
            pools.append((start, end))
        lines = [f"subnet {network.network_address} netmask {network.netmask} {{"]
        lines.extend("  " + line.replace("\n", "\n  ") for line in options)
        lines.extend(f"  range {start} {end};" for start, end in sorted(pools))
        lines.append("}")
        blocks.append((int(network.network_address), network.prefixlen, "\n".join(lines)))

        for reservation_index, reservation in enumerate(_items(subnet, "reservations", path)):
            field = f"{path}.reservations[{reservation_index}]"
            _fields(reservation, {"id", "mac", "ip", "active"}, field)
            if not _active(reservation):
                continue
            host_id = _name(reservation.get("id"), field + ".id")
            mac = _mac(reservation.get("mac"), field + ".mac")
            ip = _address(reservation.get("ip"), field + ".ip")
            if (
                ip not in network
                or ip in forbidden
                or any(start <= ip <= end for start, end in pools)
                or ip in used_ips
            ):
                raise ConfigurationError(field + ".ip: unavailable or duplicate address")
            if mac in used_macs:
                raise ConfigurationError(field + ".mac: duplicate MAC")
            if host_id in used_ids:
                raise ConfigurationError(field + ".id: duplicate host identifier")
            used_ips.add(ip)
            used_macs.add(mac)
            used_ids.add(host_id)
            hosts.append(
                (
                    host_id,
                    f"host {host_id} {{\n  hardware ethernet {mac};\n  fixed-address {ip};\n}}",
                )
            )

    header = (
        f"# Generated DHCPv4 configuration for {firewall} (Gaia {profile})\n"
        "# Do not edit this artifact; changes belong in the configuration editor."
    )
    parts = [header, "ddns-update-style none;"]
    if global_options:
        parts.append("\n".join(global_options))
    parts.extend(block for _, _, block in sorted(blocks))
    parts.extend(block for _, block in sorted(hosts))
    return ("\n\n".join(parts) + "\n").encode("ascii")


def validate_configuration(config, *, complete=True):
    """Shared MVP validation: draft editing may temporarily omit active pools.

    Inactive data still has to be well formed. The low-level render() retains
    its earlier non-MVP capabilities; application operations use render_mvp().
    """
    _fields(
        config,
        {"firewall", "profile", "default_lease_time", "max_lease_time", "domain", "dns", "subnets"},
        "configuration",
    )
    _name(config.get("firewall"), "firewall")
    profile = config.get("profile")
    if not isinstance(profile, str) or profile not in _PROFILES:
        raise ConfigurationError("profile: unsupported Gaia profile")
    _options(config, "global")
    subnets = config.get("subnets")
    if not isinstance(subnets, list):
        raise ConfigurationError("subnets: expected list")
    used_names, used_macs = set(), set()
    for index, subnet in enumerate(subnets):
        path = f"subnets[{index}]"
        if not isinstance(subnet, dict):
            raise ConfigurationError(path + ": expected object")
        enabled = _active(subnet)
        pools = _items(subnet, "pools", path)
        reservations = _items(subnet, "reservations", path)
        if len(pools) > 1:
            raise ConfigurationError(path + ".pools: MVP allows one pool per subnet")
        for kind, rows in [("pools", pools), ("reservations", reservations)]:
            for child_index, row in enumerate(rows):
                if not isinstance(row, dict):
                    raise ConfigurationError(f"{path}.{kind}[{child_index}]: expected object")
                _active(row)
        # Use the same domain rules even when a subnet or child is inactive.
        isolated = {
            **subnet,
            "active": True,
            "pools": [{**row, "active": True} for row in pools],
            "reservations": [{**row, "active": True} for row in reservations],
        }
        try:
            render({**config, "subnets": [isolated]})
        except ConfigurationError as exc:
            raise ConfigurationError(str(exc).replace("subnets[0]", path, 1)) from None
        for row in reservations:
            mac = _mac(row.get("mac"), path + ".reservations.mac")
            if row["id"] in used_names or mac in used_macs:
                raise ConfigurationError(path + ".reservations: duplicate name or MAC")
            used_names.add(row["id"])
            used_macs.add(mac)
        if complete and enabled and (len(pools) != 1 or not _active(pools[0])):
            raise ConfigurationError(path + ".pools: one active pool required for MVP")
    if complete or any(_active(row) for row in subnets):
        render(config)


def render_mvp(config):
    """Render only a complete configuration in the agreed Gaia MVP scope."""
    validate_configuration(config, complete=True)
    return render(config)
