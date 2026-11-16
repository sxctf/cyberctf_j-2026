import os

from app.sim.switch import Switch
from app.sim.firewall import Firewall
from app.sim.stubs import is_cisco_stub, is_iptables_stub

SW_PASSWORD = os.environ.get("SW_PASSWORD", "Kr3st-SW-2408")
FW_PASSWORD = os.environ.get("FW_PASSWORD", "Kr3st-FW-2408")

PASS_THROUGH = {"use", "exit", "quit", "help", "?"}


class Session:
    def __init__(self, verify_cb):
        self.switch = Switch()
        self.fw = Firewall()
        self.current = None
        self.authed = {"sw": False, "fw": False}
        self.verify_cb = verify_cb

    def handle_line(self, line):
        raw = line.rstrip("\r\n")
        parts = raw.strip().split()
        if not parts:
            return []
        cmd = parts[0].lower()

        # password gate: allow only escape/help commands
        if self.current and not self.authed[self.current]:
            if cmd not in PASS_THROUGH:
                pwd = raw.strip()
                if self.current == "sw" and pwd == SW_PASSWORD:
                    self.authed["sw"] = True
                    return ["[sw] ok"]
                if self.current == "fw" and pwd == FW_PASSWORD:
                    self.authed["fw"] = True
                    return ["[fw] ok"]
                return ["% bad password"]

        # universal commands
        if cmd == "use":
            if len(parts) < 2:
                return ["% usage: use sw|fw"]
            dev = parts[1].lower()
            if dev in ("sw", "switch"):
                self.current = "sw"
                return ["[sw] ready"] if self.authed["sw"] else ["[sw] password:"]
            if dev in ("fw", "firewall"):
                self.current = "fw"
                return ["[fw] ready"] if self.authed["fw"] else ["[fw] password:"]
            return [f"% unknown device: {dev}"]

        if cmd in ("exit", "quit", "logout"):
            return ["__DISCONNECT__"]

        if cmd in ("help", "?"):
            return ["% help: use sw|fw, admin, exit, ticket 4417 verify"]

        if cmd == "admin":
            if not self.current or not self.authed[self.current]:
                return ["% not authenticated"]
            return self._admin()

        if cmd == "ticket":
            if len(parts) >= 3 and parts[1] == "4417" and parts[2].lower() == "verify":
                return self._verify()
            return ["% usage: ticket 4417 verify"]

        if not self.current:
            return ["% select device first: use sw|fw"]

        # stubs
        if self.current == "fw" and is_iptables_stub(raw):
            return ["% OK (stub, no changes applied)"]
        if self.current == "sw" and is_cisco_stub(raw):
            return ["% OK (stub, no changes applied)"]

        dev = self.switch if self.current == "sw" else self.fw
        return dev.handle(raw)

    def _admin(self):
        return [
            "=== device state ===",
            f"switch ports:  {list(self.switch.ports.keys())}",
            f"switch segs:   {list(self.switch.segments.keys())}",
            f"fw zones:      {list(self.fw.zones.keys())}",
            f"fw policies:   {list(self.fw.policies.keys())}",
        ]

    def _verify(self):
        try:
            result = self.verify_cb(self.switch.dump(), self.fw.dump())
        except Exception as e:
            return [f"% verify error: {e}"]
        if result.get("solved"):
            return ["Проверка... OK", f"Ваш флаг: {result.get('flag')}"]
        return [f"Проверка... FAIL: {result.get('reason', 'unknown')}"]