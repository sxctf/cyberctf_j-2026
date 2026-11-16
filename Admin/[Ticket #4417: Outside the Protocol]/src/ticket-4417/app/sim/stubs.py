CISCO_PREFIXES = [
    "configure terminal", "conf t", "end", "exit", "write memory", "write",
    "copy running-config startup-config", "show running-config", "show version",
    "show interfaces", "show vlan", "show mac address-table",
    "interface ", "switchport", "switchport access vlan", "switchport mode",
    "switchport trunk", "vlan ", "no shutdown", "shutdown",
    "ip route ", "ip address ", "hostname ", "spanning-tree", "cdp",
    "no ip route ", "banner ", "logging ", "ntp ",
]

IPTABLES_PREFIXES = [
    "iptables", "nft", "ip6tables", "iptables-save", "iptables-restore",
]


def is_cisco_stub(line):
    line = line.strip().lower()
    for p in CISCO_PREFIXES:
        if line == p or line.startswith(p):
            return True
    return False


def is_iptables_stub(line):
    line = line.strip().lower()
    for p in IPTABLES_PREFIXES:
        if line == p or line.startswith(p + " "):
            return True
    return False