import json

INITIAL_ZONES = {
    "any": {"members": ["eth0", "eth2"], "default": "permit"},
    "office": {"members": [], "default": "drop"},
}

INITIAL_POLICIES = {
    "OFFICE-1C": {"rules": [], "applied": False},
}


class Firewall:
    def __init__(self):
        self.zones = json.loads(json.dumps(INITIAL_ZONES))
        self.policies = json.loads(json.dumps(INITIAL_POLICIES))

    def dump(self):
        return {"zones": self.zones, "policies": self.policies}

    def handle(self, line):
        parts = line.strip().split()
        if not parts:
            return []
        cmd = parts[0].lower()

        if cmd == "cfg":
            return self._cfg(parts[1:])
        if cmd == "zone" and len(parts) >= 4:
            return self._zone(parts)
        if cmd == "policy" and len(parts) >= 3:
            return self._policy(parts)
        if cmd == "show":
            return self._show(parts[1:])
        return [f"% unknown: {parts[0]}"]

    def _cfg(self, args):
        if not args:
            return ["% usage: cfg begin|apply|confirm|save|diff|rollback"]
        sub = args[0].lower()
        if sub == "begin":
            return ["% cfg session started"]
        if sub == "diff":
            return ["% diff: (no detailed diff tracked)"]
        if sub == "apply":
            return ["% changes applied (pending confirm)"]
        if sub == "confirm":
            return ["% confirmed"]
        if sub == "save":
            return ["% saved to startup-config"]
        if sub == "rollback":
            return ["% rollback: requires timeout — no-op"]
        return [f"% unknown cfg: {sub}"]

    def _zone(self, parts):
        name = parts[1]
        if parts[2].lower() != "member":
            return ["% usage: zone <name> member <eth>"]
        member = parts[3]
        if name not in self.zones:
            self.zones[name] = {"members": [], "default": "drop"}
        for zname, z in self.zones.items():
            if member in z["members"]:
                z["members"].remove(member)
        if member not in self.zones[name]["members"]:
            self.zones[name]["members"].append(member)
        return [f"% zone {name} += {member}"]

    def _policy(self, parts):
        name = parts[1]
        sub = parts[2].lower() if len(parts) >= 3 else ""
        if name not in self.policies:
            self.policies[name] = {"rules": [], "applied": False}
        pol = self.policies[name]

        if sub == "apply":
            pol["applied"] = True
            return [f"% policy {name} applied"]

        if sub == "rule":
            if len(parts) < 7:
                return ["% usage: policy <name> rule <num> <action> <proto> <src> -> <dst> [dport <n>]"]
            try:
                rule_num = int(parts[3])
            except ValueError:
                return ["% rule num must be int"]
            action = parts[4]
            proto = parts[5]
            src = parts[6]
            dst = "any"
            if "->" in parts:
                idx = parts.index("->")
                if idx + 1 < len(parts):
                    dst = parts[idx + 1]
            dport = None
            if "dport" in parts:
                i = parts.index("dport")
                if i + 1 < len(parts):
                    dport = parts[i + 1]
            rule = {"num": rule_num, "action": action,
                    "proto": proto, "src": src, "dst": dst}
            if dport:
                rule["dport"] = dport
            pol["rules"].append(rule)
            return [f"% rule {rule_num} added to policy {name}"]

        if sub == "default":
            return [f"% policy {name} default set (stub)"]

        return ["% usage: policy <name> apply|rule|default"]

    def _show(self, args):
        if args and args[0].lower() == "zones":
            return [f"{k}: members={v['members']} default={v['default']}"
                    for k, v in self.zones.items()]
        if args and args[0].lower() == "policies":
            return [
                f"{k}: applied={v['applied']} rules={len(v['rules'])}"
                for k, v in self.policies.items()
            ]
        return ["% usage: show zones|policies"]