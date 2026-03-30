"""
TradeNet Fabric — Firewall Zone & Rule Generator
==================================================
Auto-generates zone-based firewall rules from topology definitions.

WHY AUTO-GENERATION (for interview):
Hand-writing firewall rules is error-prone and doesn't scale.
With 6 sites, 4 security zones, and bidirectional policies,
that's 12+ policy sets to maintain. Instead, we:
1. Define zones in YAML (declarative)
2. Define policies in YAML (what's allowed between zones)
3. Generate vendor-specific firewall rules automatically
4. Validate rules in CI before deployment

This is automation-first thinking. Jane Street automates as much
as possible because automation reduces error rates.

WHY ZONE-BASED INSTEAD OF ACLs (for interview):
- ACLs are per-interface, per-direction. To allow return traffic,
  you need matching rules in both directions. Easy to forget.
- Zone-based firewalls are STATEFUL: allow outbound → return
  traffic is automatically permitted (connection tracking).
- Zones are architectural: "trading zone talks to exchange zone"
  is a policy. "permit tcp 10.1.0.0/16 10.4.0.0/16 eq 443 in
  on GigabitEthernet0/1" is an implementation detail.
"""

import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class SecurityZone:
    """A logical security zone in the network."""
    name: str
    description: str
    sites: List[str]         # Which sites belong to this zone
    trust_level: int         # 0 = untrusted, 100 = most trusted
    allowed_services: List[str] = field(default_factory=list)


@dataclass
class ZonePolicy:
    """Policy defining what traffic is allowed between two zones."""
    from_zone: str
    to_zone: str
    action: str              # "permit" or "deny"
    applications: List[str]  # e.g., ["bgp", "market-data", "ssh"]
    logging: bool = True
    description: str = ""


@dataclass
class GeneratedRule:
    """A vendor-specific firewall rule ready for deployment."""
    vendor: str
    device: str
    rule_text: str
    zone_policy: str         # Which policy generated this rule
    sequence: int


# ============================================================
# Zone Definitions for TradeNet Fabric
# ============================================================

ZONES = [
    SecurityZone(
        name="trading",
        description="Trading systems and market data consumers",
        sites=["dc-east", "dc-west", "dr-site"],
        trust_level=90,
        allowed_services=["ssh", "netconf", "snmp", "ntp", "bgp", "ospf", "bfd"],
    ),
    SecurityZone(
        name="exchange",
        description="Exchange colocation connectivity (NYSE, CME, NASDAQ)",
        sites=["colo-nyse", "colo-cme", "colo-nasdaq"],
        trust_level=50,
        allowed_services=["bgp", "bfd", "market-data"],
    ),
    SecurityZone(
        name="management",
        description="Out-of-band management network",
        sites=["dc-east", "dc-west"],  # Management only in DCs
        trust_level=100,
        allowed_services=["ssh", "netconf", "snmp", "https", "ntp"],
    ),
    SecurityZone(
        name="internet",
        description="External internet via transit providers",
        sites=["transit"],
        trust_level=0,
        allowed_services=["bgp"],
    ),
]

# ============================================================
# Zone Policies — The Security Architecture
# ============================================================

POLICIES = [
    # Trading → Exchange: Allow market data and BGP
    ZonePolicy(
        from_zone="trading", to_zone="exchange",
        action="permit",
        applications=["bgp", "bfd", "market-data"],
        description="Trading systems can reach exchanges for market data and BGP",
    ),
    # Exchange → Trading: Allow market data inbound and BGP
    ZonePolicy(
        from_zone="exchange", to_zone="trading",
        action="permit",
        applications=["bgp", "bfd", "market-data"],
        description="Exchanges send market data to trading systems",
    ),
    # Management → Trading: Full access for network management
    ZonePolicy(
        from_zone="management", to_zone="trading",
        action="permit",
        applications=["ssh", "netconf", "snmp", "https", "ping"],
        description="Management can access trading infrastructure",
    ),
    # Management → Exchange: Full access for network management
    ZonePolicy(
        from_zone="management", to_zone="exchange",
        action="permit",
        applications=["ssh", "netconf", "snmp", "https", "ping"],
        description="Management can access exchange edge devices",
    ),
    # Trading → Internet: Limited (DNS, NTP only)
    ZonePolicy(
        from_zone="trading", to_zone="internet",
        action="permit",
        applications=["dns", "ntp"],
        description="Trading systems can reach internet for DNS/NTP only",
    ),
    # Internet → Trading: DENY ALL (critical security boundary)
    ZonePolicy(
        from_zone="internet", to_zone="trading",
        action="deny",
        applications=[],
        logging=True,
        description="Internet cannot reach trading systems — ever",
    ),
    # Internet → Exchange: DENY ALL
    ZonePolicy(
        from_zone="internet", to_zone="exchange",
        action="deny",
        applications=[],
        logging=True,
        description="Internet cannot reach exchange colocations",
    ),
    # Exchange → Internet: DENY
    ZonePolicy(
        from_zone="exchange", to_zone="internet",
        action="deny",
        applications=[],
        description="Exchange traffic never goes to internet",
    ),
]

# Application port mappings
APP_PORTS = {
    "bgp": {"protocol": "tcp", "port": 179},
    "bfd": {"protocol": "udp", "port": 3784},
    "ssh": {"protocol": "tcp", "port": 22},
    "netconf": {"protocol": "tcp", "port": 830},
    "snmp": {"protocol": "udp", "port": 161},
    "https": {"protocol": "tcp", "port": 443},
    "ntp": {"protocol": "udp", "port": 123},
    "dns": {"protocol": "udp", "port": 53},
    "ping": {"protocol": "icmp", "port": 0},
    "market-data": {"protocol": "udp", "port": "30001-30010"},
}


class FirewallGenerator:
    """Generates vendor-specific firewall rules from zone policies."""

    def __init__(self):
        self.zones = {z.name: z for z in ZONES}
        self.policies = POLICIES
        self.generated_rules: List[GeneratedRule] = []

    def generate_junos_rules(self, device: str) -> str:
        """Generate Juniper Junos security zone configuration.

        Juniper SRX is our edge firewall platform — this is where
        zone-based policies are actually enforced.
        """
        config_lines = ["security {", "    policies {"]

        for policy in self.policies:
            config_lines.append(
                f"        /* {policy.description} */"
            )
            config_lines.append(
                f"        from-zone {policy.from_zone} to-zone {policy.to_zone} {{"
            )

            if policy.action == "permit" and policy.applications:
                for app in policy.applications:
                    app_info = APP_PORTS.get(app, {})
                    proto = app_info.get("protocol", "tcp")
                    port = app_info.get("port", "any")

                    rule_name = f"allow-{app}"
                    config_lines.append(f"            policy {rule_name} {{")
                    config_lines.append(f"                match {{")
                    config_lines.append(f"                    source-address any;")
                    config_lines.append(f"                    destination-address any;")
                    if app in ("bgp", "ssh", "netconf", "https"):
                        config_lines.append(f"                    application junos-{app};")
                    else:
                        config_lines.append(f"                    application {app};")
                    config_lines.append(f"                }}")
                    config_lines.append(f"                then {{")
                    config_lines.append(f"                    permit;")
                    if policy.logging:
                        config_lines.append(f"                    log {{ session-init; }}")
                    config_lines.append(f"                }}")
                    config_lines.append(f"            }}")

            # Always add a default deny at the end of each zone pair
            config_lines.append(f"            policy default-deny {{")
            config_lines.append(f"                match {{")
            config_lines.append(f"                    source-address any;")
            config_lines.append(f"                    destination-address any;")
            config_lines.append(f"                    application any;")
            config_lines.append(f"                }}")
            config_lines.append(f"                then {{")
            config_lines.append(f"                    deny;")
            config_lines.append(f"                    log {{ session-init; }}")
            config_lines.append(f"                }}")
            config_lines.append(f"            }}")
            config_lines.append(f"        }}")

        config_lines.append("    }")
        config_lines.append("}")
        return "\n".join(config_lines)

    def generate_summary(self):
        """Print a summary of the zone security architecture."""
        console.print("[bold cyan]TradeNet Fabric — Firewall Zone Architecture[/]")
        console.print("[bold cyan]=============================================[/]\n")

        # Zone table
        zone_table = Table(title="Security Zones")
        zone_table.add_column("Zone", style="cyan")
        zone_table.add_column("Trust Level")
        zone_table.add_column("Sites")
        zone_table.add_column("Description")

        for zone in ZONES:
            trust_style = (
                "[green]" if zone.trust_level >= 80 else
                "[yellow]" if zone.trust_level >= 40 else
                "[red]"
            )
            zone_table.add_row(
                zone.name,
                f"{trust_style}{zone.trust_level}[/]",
                ", ".join(zone.sites),
                zone.description,
            )
        console.print(zone_table)

        # Policy matrix
        console.print()
        policy_table = Table(title="Zone Policy Matrix")
        policy_table.add_column("From \\ To", style="bold")
        for zone in ZONES:
            policy_table.add_column(zone.name)

        for from_zone in ZONES:
            row = []
            for to_zone in ZONES:
                if from_zone.name == to_zone.name:
                    row.append("[dim]—[/]")
                    continue
                matching = [p for p in self.policies
                            if p.from_zone == from_zone.name
                            and p.to_zone == to_zone.name]
                if matching:
                    p = matching[0]
                    if p.action == "permit":
                        apps = ", ".join(p.applications[:3])
                        row.append(f"[green]ALLOW[/]\n{apps}")
                    else:
                        row.append("[red]DENY[/]")
                else:
                    row.append("[red]DENY[/]\n(implicit)")
            policy_table.add_row(from_zone.name, *row)

        console.print(policy_table)

        # Stats
        total_permit = sum(1 for p in self.policies if p.action == "permit")
        total_deny = sum(1 for p in self.policies if p.action == "deny")
        console.print(f"\n  Policies: {total_permit} permit, {total_deny} explicit deny")
        console.print(f"  Implicit deny on all unmatched zone pairs")

        # Generate sample Junos config
        console.print(f"\n[bold]Sample Junos Firewall Config (colo-nyse-edge-01):[/]")
        config = self.generate_junos_rules("colo-nyse-edge-01")
        # Print first 30 lines
        for line in config.split("\n")[:30]:
            console.print(f"  [dim]{line}[/]")
        console.print(f"  [dim]... ({len(config.split(chr(10)))} total lines)[/]")


if __name__ == "__main__":
    gen = FirewallGenerator()
    gen.generate_summary()
