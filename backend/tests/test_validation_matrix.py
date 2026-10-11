import json
from pathlib import Path

import pytest

from dhcp_tool.generator import ConfigurationError, render


@pytest.fixture
def config():
    return {
        "firewall": "fw-test",
        "profile": "R81.10",
        "default_lease_time": 100,
        "max_lease_time": 200,
        "domain": "example.org",
        "dns": ["1.1.1.1"],
        "subnets": [
            {
                "cidr": "192.0.2.0/24",
                "gateway": "192.0.2.1",
                "interface_address": "192.0.2.2",
                "pools": [{"start": "192.0.2.100", "end": "192.0.2.150"}],
                "reservations": [
                    {"id": "host-one", "mac": "AA-BB-CC-DD-EE-01", "ip": "192.0.2.20"}
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    "cidr",
    [
        "192.0.2.1/24",
        "192.0.2.0/31",
        "192.0.2.0/32",
        "192.0.2.0/33",
        "2001:db8::/64",
        "192.0.2.0",
        "",
        None,
        24,
    ],
)
def test_invalid_cidr(config, cidr):
    config["subnets"][0]["cidr"] = cidr
    with pytest.raises(ConfigurationError, match="cidr"):
        render(config)


@pytest.mark.parametrize(
    "address", ["192.0.2.256", "192.0.02.20", "::1", "", None, 123, "198.51.100.20"]
)
def test_invalid_reservation_ipv4(config, address):
    config["subnets"][0]["reservations"][0]["ip"] = address
    with pytest.raises(ConfigurationError, match="ip"):
        render(config)


@pytest.mark.parametrize(
    "mac",
    [
        "",
        None,
        123,
        "00:11:22:33:44",
        "00:11:22:33:44:55:66",
        "00:11-22:33:44:55",
        "gg:11:22:33:44:55",
        "0011.2233.4455",
    ],
)
def test_invalid_mac(config, mac):
    config["subnets"][0]["reservations"][0]["mac"] = mac
    with pytest.raises(ConfigurationError, match="mac"):
        render(config)


@pytest.mark.parametrize("mac", ["AA-BB-CC-DD-EE-01", "AA:BB:CC:DD:EE:01", "aa:bb:cc:dd:ee:01"])
def test_mac_normalization(config, mac):
    config["subnets"][0]["reservations"][0]["mac"] = mac
    assert b"hardware ethernet aa:bb:cc:dd:ee:01;" in render(config)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("192.0.2.150", "192.0.2.100"),
        ("198.51.100.100", "198.51.100.150"),
        ("192.0.2.100", "198.51.100.150"),
        ("192.0.2.0", "192.0.2.10"),
        ("192.0.2.200", "192.0.2.255"),
        ("192.0.2.1", "192.0.2.10"),
        ("192.0.2.2", "192.0.2.10"),
    ],
)
def test_invalid_pool_ranges(config, start, end):
    config["subnets"][0]["pools"] = [{"start": start, "end": end}]
    with pytest.raises(ConfigurationError, match="pools"):
        render(config)


def test_overlapping_pool_boundaries(config):
    config["subnets"][0]["pools"].append({"start": "192.0.2.150", "end": "192.0.2.180"})
    with pytest.raises(ConfigurationError, match="overlapping pools"):
        render(config)


@pytest.mark.parametrize("cidr", ["192.0.2.0/25", "192.0.2.0/24", "192.0.0.0/16"])
def test_overlapping_subnets(config, cidr):
    config["subnets"].append({"cidr": cidr})
    with pytest.raises(ConfigurationError, match="overlapping"):
        render(config)


@pytest.mark.parametrize(
    "address", ["192.0.2.0", "192.0.2.255", "192.0.2.1", "192.0.2.2", "192.0.2.100", "192.0.2.150"]
)
def test_reserved_addresses_and_pool_boundaries_in_reservations(config, address):
    config["subnets"][0]["reservations"][0]["ip"] = address
    with pytest.raises(ConfigurationError, match="reservations.*ip"):
        render(config)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("ip", "192.0.2.20", "duplicate address"),
        ("mac", "aa:bb:cc:dd:ee:01", "duplicate MAC"),
        ("id", "host-one", "duplicate host"),
    ],
)
def test_duplicate_reservations(config, field, value, match):
    row = {"id": "host-two", "mac": "00:11:22:33:44:55", "ip": "192.0.2.21", field: value}
    config["subnets"][0]["reservations"].append(row)
    with pytest.raises(ConfigurationError, match=match):
        render(config)


@pytest.mark.parametrize("field", ["gateway", "interface_address"])
@pytest.mark.parametrize("address", ["192.0.2.0", "192.0.2.255", "198.51.100.1", "::1", "invalid"])
def test_invalid_gateway_and_interface(config, field, address):
    config["subnets"][0][field] = address
    with pytest.raises(ConfigurationError, match=field):
        render(config)


@pytest.mark.parametrize("dns", [[], ["1.1.1.1"] * 4, ["::1"], ["invalid"], "1.1.1.1", [123]])
def test_dns_limits_and_ipv4(config, dns):
    config["dns"] = dns
    with pytest.raises(ConfigurationError, match="dns"):
        render(config)


@pytest.mark.parametrize(
    "domain",
    [
        "",
        "-example.org",
        "example..org",
        "a" * 64 + ".org",
        "a." * 128,
        "example.org#comment",
        'example.org"',
        "example.org\n",
    ],
)
def test_invalid_domains(config, domain):
    config["domain"] = domain
    with pytest.raises(ConfigurationError, match="domain"):
        render(config)


@pytest.mark.parametrize("field", ["default_lease_time", "max_lease_time"])
@pytest.mark.parametrize("value", [0, -1, 2147483648, True, 1.5, "100"])
def test_lease_value_bounds(config, field, value):
    config[field] = value
    with pytest.raises(ConfigurationError, match=field):
        render(config)


def test_effective_inherited_lease_order(config):
    config["subnets"][0]["default_lease_time"] = 300
    with pytest.raises(ConfigurationError, match="lease"):
        render(config)


@pytest.mark.parametrize(
    "payload",
    [
        'host\ninclude "evil";',
        "host#comment",
        'host";',
        "host; deny all;",
        "host\r\n",
        "host/*comment*/",
        "host\x00",
    ],
)
@pytest.mark.parametrize("field", ["firewall", "reservation_id", "domain", "description"])
def test_injection_in_names_and_unrecognized_descriptions(config, field, payload):
    if field == "reservation_id":
        config["subnets"][0]["reservations"][0]["id"] = payload
    elif field == "description":
        config["subnets"][0]["reservations"][0]["description"] = payload
    else:
        config[field] = payload
    with pytest.raises(ConfigurationError):
        render(config)


@pytest.mark.parametrize("profile", ["R81.10", "R82.10"])
def test_mvp_golden_files_and_permutation(config, profile):
    fixtures = Path(__file__).parent / "fixtures"
    source = json.loads((fixtures / "mvp.json").read_text())
    source["profile"] = profile
    expected = (fixtures / f"mvp-{profile}.conf").read_bytes()
    assert render(source) == expected
    source["subnets"].reverse()
    for subnet in source["subnets"]:
        subnet["reservations"].reverse()
    assert render(source) == expected


@pytest.mark.parametrize("location", ["subnet", "pool", "reservation"])
@pytest.mark.parametrize("value", ["false", 0, 1, None])
def test_activation_must_be_boolean(config, location, value):
    row = config["subnets"][0]
    if location == "pool":
        row = row["pools"][0]
    elif location == "reservation":
        row = row["reservations"][0]
    row["active"] = value
    with pytest.raises(ConfigurationError, match="active"):
        render(config)


def test_null_local_lease_options_inherit_globals(config):
    config["subnets"][0].update({"default_lease_time": None, "max_lease_time": None})
    assert b"default-lease-time 100;" in render(config)


@pytest.mark.parametrize("profile", ["R81.10", "R82.10"])
def test_complete_mvp_requires_exactly_one_active_pool(config, profile):
    from dhcp_tool.generator import render_mvp, validate_configuration

    config["profile"] = profile
    for pools in (
        [],
        [{"start": "192.0.2.100", "end": "192.0.2.150", "active": False}],
        [
            {"start": "192.0.2.100", "end": "192.0.2.150"},
            {"start": "192.0.2.160", "end": "192.0.2.180"},
        ],
    ):
        config["subnets"][0]["pools"] = pools
        with pytest.raises(ConfigurationError, match="pools"):
            render_mvp(config)
    config["subnets"][0]["pools"] = []
    validate_configuration(config, complete=False)


def test_complete_mvp_validates_inactive_values_and_rejects_empty(config):
    from dhcp_tool.generator import render_mvp, validate_configuration

    config["subnets"][0]["reservations"][0].update({"active": False, "mac": "broken"})
    with pytest.raises(ConfigurationError, match="mac"):
        render_mvp(config)
    config["subnets"] = []
    with pytest.raises(ConfigurationError, match="subnets"):
        render_mvp(config)
    validate_configuration(config, complete=False)


def test_mvp_omits_inactive_children_and_subnets(config):
    from dhcp_tool.generator import render_mvp

    config["subnets"][0]["reservations"][0]["active"] = False
    config["subnets"].append({"cidr": "198.51.100.0/24", "active": False})
    content = render_mvp(config)
    assert b"host host-one" not in content
    assert b"198.51.100" not in content


@pytest.mark.parametrize("profile", ["R81.10", "R82.10"])
def test_real_isc_parser_accepts_mvp_golden(profile):
    import os

    from dhcp_tool.syntax import check_syntax

    parser = os.environ.get("DHCPD_PARSER_PATH")
    if not parser:
        pytest.skip("No real ISC parser configured")
    content = (Path(__file__).parent / "fixtures" / f"mvp-{profile}.conf").read_bytes()
    assert check_syntax(content, parser_path=parser).status == "syntax_checked"


def test_multiple_interface_addresses_do_not_change_rendered_directives(config):
    expected = render(config)
    config["subnets"][0]["interface_address"] = ["192.0.2.2", "192.0.2.3"]
    assert render(config) == expected


@pytest.mark.parametrize("address", ["192.0.2.2", "192.0.2.3"])
@pytest.mark.parametrize("kind", ["pool", "reservation"])
def test_every_cluster_interface_address_is_protected(config, address, kind):
    subnet = config["subnets"][0]
    subnet["interface_address"] = ["192.0.2.2", "192.0.2.3"]
    if kind == "pool":
        subnet["pools"] = [{"start": address, "end": address}]
    else:
        subnet["reservations"][0]["ip"] = address
    with pytest.raises(ConfigurationError, match="reserved address|reservation"):
        render(config)


@pytest.mark.parametrize(
    "addresses",
    [
        ["192.0.2.2", "198.51.100.3"],
        ["192.0.2.2", "::1"],
        ["192.0.2.2", "192.0.2.255"],
        ["192.0.2.2", "192.0.2.0"],
        ["192.0.2.2", "192.0.2.2"],
        [],
        ["192.0.2.2"] * 65,
    ],
)
def test_invalid_interface_address_lists(config, addresses):
    config["subnets"][0]["interface_address"] = addresses
    with pytest.raises(ConfigurationError, match="interface_address"):
        render(config)
