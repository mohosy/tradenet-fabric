"""
TradeNet Fabric — RPKI Validator
=================================
Validates BGP route announcements against RPKI (Resource Public Key
Infrastructure) to protect against BGP hijacks.

WHAT IS RPKI (for interview):
BGP has NO built-in authentication. When a router announces "I can reach
198.51.100.0/24", there's no proof that's true. RPKI adds a cryptographic
layer:
1. IP address holders publish ROA records (Route Origin Authorizations)
   that say "AS 11111 is authorized to announce 198.51.100.0/24"
2. RPKI validators download and verify these ROA records
3. Routers query the validator before accepting BGP announcements
4. If the announcement doesn't match any ROA → INVALID → reject it

WHY RPKI MATTERS FOR TRADING (for interview):
In 2018, a BGP hijack rerouted Amazon Route 53 DNS through a Russian ISP,
stealing $150K in cryptocurrency. For a trading firm:
- A hijacked market data route → attacker sees your trading signals
- A hijacked exchange route → trades go to the wrong destination
- Even a brief hijack during market hours → missed trades, losses

RPKI is the defense. Jane Street peers at multiple exchanges — they
absolutely care about route origin validation.

ARCHITECTURE:
- We run Routinator (NLnet Labs' RPKI validator) locally
- Routers are configured as RTR (RPKI-to-Router) protocol clients
- This script manages ROA records and validates announcements
- Integration with chaos framework for BGP hijack testing
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime

from rich.console import Console
from rich.table import Table

console = Console()


class RPKIStatus(Enum):
    """RPKI validation states (RFC 6811)."""
    VALID = "valid"          # ROA exists and matches
    INVALID = "invalid"      # ROA exists but doesn't match (HIJACK!)
    NOT_FOUND = "not_found"  # No ROA exists (unknown)


@dataclass
class ROA:
    """Route Origin Authorization — the core RPKI data structure.

    A ROA says: "AS {asn} is authorized to originate {prefix},
    up to a maximum prefix length of {max_length}."

    For example: ROA(prefix="198.51.100.0/24", max_length=24, asn=11111)
    means "only AS 11111 can announce 198.51.100.0/24, and no more-specific
    prefixes like /25 are authorized."
    """
    prefix: str              # e.g., "198.51.100.0/24"
    max_length: int          # Maximum allowed prefix length
    asn: int                 # Authorized origin AS number
    trust_anchor: str = ""   # Which trust anchor signed this ROA
    not_before: str = ""     # Validity start
    not_after: str = ""      # Validity end


@dataclass
class BGPAnnouncement:
    """A BGP route announcement to be validated."""
    prefix: str              # Announced prefix
    origin_asn: int          # Origin AS number
    as_path: str = ""        # Full AS path
    next_hop: str = ""       # BGP next hop
    source_peer: str = ""    # Which peer sent this
    timestamp: float = 0.0   # When we received it


@dataclass
class ValidationResult:
    """Result of validating a BGP announcement against RPKI."""
    announcement: BGPAnnouncement
    status: RPKIStatus
    matching_roa: Optional[ROA] = None
    reason: str = ""
    validated_at: float = 0.0


@dataclass
class RPKIAlert:
    """Alert generated when an INVALID announcement is detected."""
    announcement: BGPAnnouncement
    expected_asn: int        # What the ROA says the origin should be
    actual_asn: int          # What the announcement says
    severity: str = "critical"
    message: str = ""
    timestamp: float = 0.0


class RPKIValidator:
    """Local RPKI validator for TradeNet Fabric.

    In production, this would connect to Routinator or similar.
    For our lab, we maintain a local ROA database matching our
    simulated exchanges.
    """

    def __init__(self):
        self.roa_database: Dict[str, List[ROA]] = {}
        self.validation_history: List[ValidationResult] = []
        self.alerts: List[RPKIAlert] = []
        self._load_roa_database()

    def _load_roa_database(self):
        """Load ROA records for our simulated topology.

        In production, ROAs are downloaded from the five Regional
        Internet Registries (RIRs) via RPKI repositories. For our
        lab, we define them statically to match our topology.
        """
        # NYSE exchange ROAs
        self._add_roa(ROA(
            prefix="198.51.100.0/24",
            max_length=24,
            asn=11111,  # NYSE's ASN
            trust_anchor="ARIN",
        ))

        # CME exchange ROAs
        self._add_roa(ROA(
            prefix="203.0.113.0/24",
            max_length=24,
            asn=22222,  # CME's ASN
            trust_anchor="ARIN",
        ))

        # NASDAQ exchange ROAs
        self._add_roa(ROA(
            prefix="192.0.2.0/24",
            max_length=24,
            asn=33333,  # NASDAQ's ASN
            trust_anchor="ARIN",
        ))

        # Our own prefixes (if we advertised any externally)
        self._add_roa(ROA(
            prefix="10.0.0.0/8",
            max_length=32,
            asn=65001,  # Our internal ASN
            trust_anchor="internal",
        ))

        console.print(f"[dim]Loaded {sum(len(v) for v in self.roa_database.values())} ROA records[/]")

    def _add_roa(self, roa: ROA):
        """Add a ROA to the local database."""
        if roa.prefix not in self.roa_database:
            self.roa_database[roa.prefix] = []
        self.roa_database[roa.prefix].append(roa)

    def _prefix_matches(self, announced: str, roa_prefix: str, max_length: int) -> bool:
        """Check if an announced prefix is covered by a ROA.

        A ROA for 198.51.100.0/24 with max_length=24 covers:
        - 198.51.100.0/24 exactly ← VALID
        - 198.51.100.0/25 ← INVALID (more specific than max_length)

        A ROA for 10.0.0.0/8 with max_length=32 covers:
        - 10.0.0.0/8 through 10.x.x.x/32 ← all VALID
        """
        import ipaddress
        try:
            announced_net = ipaddress.ip_network(announced, strict=False)
            roa_net = ipaddress.ip_network(roa_prefix, strict=False)

            # The announced prefix must be within the ROA prefix
            if not announced_net.subnet_of(roa_net):
                return False

            # The announced prefix length must be <= max_length
            if announced_net.prefixlen > max_length:
                return False

            return True
        except ValueError:
            return False

    def validate(self, announcement: BGPAnnouncement) -> ValidationResult:
        """Validate a BGP announcement against the ROA database.

        This implements the algorithm from RFC 6811:
        1. Find all ROAs that cover the announced prefix
        2. If ANY ROA matches both prefix AND origin ASN → VALID
        3. If ROAs exist for the prefix but NONE match the ASN → INVALID
        4. If no ROAs exist for the prefix at all → NOT_FOUND

        INVALID is the dangerous state — it means someone is announcing
        a prefix they're not authorized to announce. This is a hijack.
        """
        result = ValidationResult(
            announcement=announcement,
            status=RPKIStatus.NOT_FOUND,
            validated_at=time.time(),
        )

        # Find all ROAs that could cover this prefix
        matching_roas = []
        for roa_prefix, roas in self.roa_database.items():
            for roa in roas:
                if self._prefix_matches(announcement.prefix, roa_prefix, roa.max_length):
                    matching_roas.append(roa)

        if not matching_roas:
            result.status = RPKIStatus.NOT_FOUND
            result.reason = "No ROA found covering this prefix"
            self.validation_history.append(result)
            return result

        # Check if any matching ROA authorizes this origin ASN
        for roa in matching_roas:
            if roa.asn == announcement.origin_asn:
                result.status = RPKIStatus.VALID
                result.matching_roa = roa
                result.reason = f"ROA matches: AS{roa.asn} authorized for {roa.prefix}"
                self.validation_history.append(result)
                return result

        # ROAs exist but none match the origin ASN → INVALID (hijack!)
        result.status = RPKIStatus.INVALID
        result.matching_roa = matching_roas[0]  # Show what SHOULD be the origin
        result.reason = (
            f"HIJACK DETECTED: AS{announcement.origin_asn} is NOT authorized "
            f"to originate {announcement.prefix}. "
            f"Expected origin: AS{matching_roas[0].asn}"
        )

        # Generate alert
        alert = RPKIAlert(
            announcement=announcement,
            expected_asn=matching_roas[0].asn,
            actual_asn=announcement.origin_asn,
            severity="critical",
            message=result.reason,
            timestamp=time.time(),
        )
        self.alerts.append(alert)

        self.validation_history.append(result)
        return result

    def print_status(self):
        """Print the current RPKI validation status."""
        console.print("\n[bold cyan]RPKI Validation Status[/]")
        console.print("[bold cyan]======================[/]\n")

        # ROA database
        roa_table = Table(title="ROA Database")
        roa_table.add_column("Prefix", style="cyan")
        roa_table.add_column("Max Length")
        roa_table.add_column("Authorized ASN", style="green")
        roa_table.add_column("Trust Anchor")

        for prefix, roas in sorted(self.roa_database.items()):
            for roa in roas:
                roa_table.add_row(
                    roa.prefix,
                    str(roa.max_length),
                    f"AS{roa.asn}",
                    roa.trust_anchor,
                )

        console.print(roa_table)

        # Recent validations
        if self.validation_history:
            val_table = Table(title="\nRecent Validations")
            val_table.add_column("Prefix", style="cyan")
            val_table.add_column("Origin ASN")
            val_table.add_column("Status", style="bold")
            val_table.add_column("Reason")

            for result in self.validation_history[-10:]:
                status_style = {
                    RPKIStatus.VALID: "[green]VALID[/]",
                    RPKIStatus.INVALID: "[red]INVALID[/]",
                    RPKIStatus.NOT_FOUND: "[yellow]NOT FOUND[/]",
                }[result.status]

                val_table.add_row(
                    result.announcement.prefix,
                    f"AS{result.announcement.origin_asn}",
                    status_style,
                    result.reason[:60],
                )

            console.print(val_table)

        # Alerts
        if self.alerts:
            console.print(f"\n[bold red]ALERTS: {len(self.alerts)} hijack attempts detected![/]")
            for alert in self.alerts:
                console.print(
                    f"  [red]HIJACK[/] {alert.announcement.prefix} "
                    f"from AS{alert.actual_asn} (expected AS{alert.expected_asn})"
                )


def demo():
    """Demo the RPKI validator with legitimate and hijack scenarios."""
    console.print("[bold cyan]TradeNet Fabric — RPKI Validator Demo[/]")
    console.print("[bold cyan]=====================================[/]\n")

    validator = RPKIValidator()

    # Legitimate announcements
    console.print("[bold]Testing legitimate announcements...[/]\n")

    legit_announcements = [
        BGPAnnouncement(prefix="198.51.100.0/24", origin_asn=11111, source_peer="NYSE"),
        BGPAnnouncement(prefix="203.0.113.0/24", origin_asn=22222, source_peer="CME"),
        BGPAnnouncement(prefix="192.0.2.0/24", origin_asn=33333, source_peer="NASDAQ"),
    ]

    for ann in legit_announcements:
        result = validator.validate(ann)
        status = "[green]VALID[/]" if result.status == RPKIStatus.VALID else "[red]INVALID[/]"
        console.print(f"  {ann.prefix} from AS{ann.origin_asn}: {status}")

    # Hijack attempts
    console.print("\n[bold]Simulating BGP hijack attempts...[/]\n")

    hijack_announcements = [
        BGPAnnouncement(
            prefix="198.51.100.0/24", origin_asn=99999,
            source_peer="transit-a",
            as_path="99999",
        ),
        BGPAnnouncement(
            prefix="203.0.113.0/24", origin_asn=88888,
            source_peer="transit-b",
            as_path="88888",
        ),
    ]

    for ann in hijack_announcements:
        result = validator.validate(ann)
        status = "[green]VALID[/]" if result.status == RPKIStatus.VALID else "[red]INVALID[/]"
        console.print(f"  {ann.prefix} from AS{ann.origin_asn}: {status}")
        if result.status == RPKIStatus.INVALID:
            console.print(f"    [red]{result.reason}[/]")

    # Print full status
    validator.print_status()


if __name__ == "__main__":
    demo()
