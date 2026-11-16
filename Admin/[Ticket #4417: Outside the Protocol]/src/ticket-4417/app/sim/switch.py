import json

INITIAL_PORTS = {
    "p1.03": {"state": "up", "pvid": 1, "guard": False},
    "p1.11": {"state": "up", "pvid": 10, "guard": True},
    "p1.12": {"state": "up", "pvid": 10, "guard": False},
    "p1.24": {"state": "up", "pvid": 1, "guard": False},
}

INITIAL_SEGMENTS = {
    "10": {"name": "OFFICE", "members": ["p1.03", "p1.11", "p1.12"]},
}

INITIAL_FILTERS = {
    "OFFICE-1C": {
        "rules": {
            "10": {"action": "drop", "proto": "tcp", "src": "any", "dst": "10.20.0.10", "dport": "22"},
            "20": {"action": "drop", "proto": "ip", "src": "10.10.0.50", "dst": "any"},
            "30": {"action": "permit", "proto": "any", "src": "any", "dst": "any"},
        }
    }
}


class Switch:
    def __init__(self):
        self.ports = json.loads(json.dumps(INITIAL_PORTS))
        self.segments = json.loads(json.dumps(INITIAL_SEGMENTS))
        self.filters = json.loads(json.dumps(INITIAL_FILTERS))
        self.cfg_mode = False

    def dump(self):
        return {
            "ports": self.ports,
            "segments": self.segments,
            "filters": self.filters,
        }

    def handle(self, line):
        parts = line.strip().split()
        if not parts:
            return []
        cmd = parts[0].lower()

        if cmd == "cfg":
            return self._cfg(parts[1:])
        if cmd == "port" and len(parts) >= 3:
            return self._port(parts)
        if cmd == "seg" and len(parts) >= 4:
            return self._seg(parts)
        if cmd == "filter" and len(parts) >= 4:
            return self._filter(parts)
        if cmd == "show":
            return self._show(parts[1:])
        return [f"% unknown: {parts[0]}"]

    def _cfg(self, args):
        if not args:
            return ["% usage: cfg begin|diff|apply|confirm|save|rollback"]
        sub = args[0].lower()
        if sub == "begin":
            self.cfg_mode = True
            return ["% cfg session started"]
        if sub == "diff":
            return ["% diff: (no detailed diff tracked)"]
        if sub == "apply":
            return ["% changes applied (pending confirm)"]
        if sub == "confirm":
            self.cfg_mode = False
            return ["% confirmed"]
        if sub == "save":
            return ["% saved to startup-config"]
        if sub == "rollback":
            return ["% rollback: requires timeout — no-op"]
        return [f"% unknown cfg: {sub}"]

    def _port(self, parts):
        port = parts[1]
        if port not in self.ports:
            return [f"% no such port: {port}"]
        sub = parts[2].lower()
        if sub == "pvid" and len(parts) >= 4:
            try:
                self.ports[port]["pvid"] = int(parts[3])
                return [f"% {port} pvid={parts[3]}"]
            except ValueError:
                return ["% pvid must be int"]
        if sub == "up":
            self.ports[port]["state"] = "up"
            if self.ports[port]["guard"]:
                return [f"% {port} up, GUARD still active (use 'port {port} guard clear')"]
            return [f"% {port} up"]
        if sub == "down":
            self.ports[port]["state"] = "down"
            return [f"% {port} down"]
        if sub == "guard" and len(parts) >= 4 and parts[3].lower() == "clear":
            self.ports[port]["guard"] = False
            return [f"% {port} GUARD cleared"]
        return ["% usage: port <name> pvid <n>|up|down|guard clear"]

    def _seg(self, parts):
        try:
            seg_id = parts[1]
            int(seg_id)
        except ValueError:
            return ["% seg id must be int"]
        if parts[2].lower() != "member":
            return ["% usage: seg <id> member <port> [tag|untag]"]
        port = parts[3]
        if port not in self.ports:
            return [f"% no such port: {port}"]
        tag = parts[4].lower() if len(parts) >= 5 else "untag"
        if seg_id not in self.segments:
            self.segments[seg_id] = {"name": f"SEG{seg_id}", "members": []}
        if port not in self.segments[seg_id]["members"]:
            self.segments[seg_id]["members"].append(port)
        return [f"% seg {seg_id} <- {port} ({tag})"]

    def _filter(self, parts):
        name = parts[1]
        if parts[2].lower() != "rule":
            return ["% usage: filter <name> rule <id> del"]
        if len(parts) >= 5 and parts[4].lower() == "del":
            rule_id = parts[3]
            if name in self.filters and rule_id in self.filters[name]["rules"]:
                del self.filters[name]["rules"][rule_id]
                return [f"% rule {rule_id} deleted"]
            return [f"% no such rule: {rule_id}"]
        return ["% usage: filter <name> rule <id> del"]

    def _show(self, args):
        if args and args[0].lower() == "ports":
            out = []
            for name, p in self.ports.items():
                out.append(f"{name} state={p['state']} pvid={p['pvid']} guard={p['guard']}")
            return out
        if args and args[0].lower() == "segments":
            return [f"{k}: {v['name']} members={v['members']}" for k, v in self.segments.items()]
        if args and args[0].lower() == "filters":
            out = []
            for name, f in self.filters.items():
                for rid, r in f["rules"].items():
                    out.append(f"{name} rule {rid}: {r}")
            return out
        return ["% usage: show ports|segments|filters"]