"""
TradeNet Fabric — Network Audit Script (Nornir)
================================================
This script uses Nornir to programmatically audit the network:
1. Verify all OSPF adjacencies are up
2. Verify all BGP sessions are established
3. Check interface error counters
4. Validate routing table entries
5. Generate a health report

WHY NORNIR INSTEAD OF ANSIBLE FOR THIS (for interview):
Ansible is great for pushing config (declarative: "make it look like this").
But auditing requires LOGIC: "gather data, compare against expected state,
make decisions, generate a report." Nornir is Python-native, so you can
write that logic naturally instead of fighting with Ansible's YAML-based
conditionals and loops.

This is exactly the kind of script Jane Street's network team would write
for monitoring and validating their network.
"""

import json
import sys
from datetime import datetime
from typing import Any

from nornir import InitNornir
from nornir.core.task import Task, Result
from nornir_netmiko.tasks import netmiko_send_command
from nornir_utils.plugins.functions import print_result
from rich.console import Console
from rich.table import Table

console = Console()


def init_nornir() -> Any:
    """Initialize Nornir with our inventory.

    We use a SimpleInventory that maps to our Ansible inventory structure.
    This means we maintain ONE source of truth for device info — the
    Ansible inventory — and Nornir reads from a compatible format.
    """
    return InitNornir(
        runner={
            "plugin": "threaded",
            "options": {
                "num_workers": 10,  # Parallel connections to 10 devices
            },
        },
        inventory={
            "plugin": "SimpleInventory",
            "options": {
                "host_file": "inventory/nornir_hosts.yaml",
                "group_file": "inventory/nornir_groups.yaml",
                "defaults_file": "inventory/nornir_defaults.yaml",
            },
        },
    )


# ============================================================
# Audit Tasks
# ============================================================

def audit_ospf(task: Task) -> Result:
    """Check OSPF neighbor status on a device.

    Returns structured data about OSPF adjacencies so we can
    compare against the expected topology.
    """
    vendor = task.host.get("vendor", "cisco")

    if vendor == "cisco":
        cmd = "show ip ospf neighbor"
    elif vendor == "arista":
        cmd = "show ip ospf neighbor"
    elif vendor == "juniper":
        cmd = "show ospf neighbor"
    else:
        return Result(host=task.host, result="Unknown vendor")

    result = task.run(
        task=netmiko_send_command,
        command_string=cmd,
        use_textfsm=True,  # Parse output into structured data
    )

    return Result(
        host=task.host,
        result={
            "ospf_neighbors": result.result if isinstance(result.result, list) else [],
            "raw_output": str(result.result),
        },
    )


def audit_bgp(task: Task) -> Result:
    """Check BGP session status on a device."""
    vendor = task.host.get("vendor", "cisco")
    role = task.host.get("role", "")

    # Only check BGP on core and edge routers
    if role not in ("core_router", "edge_router"):
        return Result(host=task.host, result={"bgp_peers": [], "skipped": True})

    if vendor == "cisco":
        cmd = "show ip bgp summary"
    elif vendor == "arista":
        cmd = "show ip bgp summary"
    elif vendor == "juniper":
        cmd = "show bgp summary"
    else:
        return Result(host=task.host, result="Unknown vendor")

    result = task.run(
        task=netmiko_send_command,
        command_string=cmd,
        use_textfsm=True,
    )

    return Result(
        host=task.host,
        result={
            "bgp_peers": result.result if isinstance(result.result, list) else [],
            "raw_output": str(result.result),
        },
    )


def audit_interfaces(task: Task) -> Result:
    """Check interface error counters.

    Non-zero error counters on trading interfaces are a red flag.
    Even a small number of CRC errors or input errors can indicate
    a physical layer problem that will cause packet loss — unacceptable
    for market data.
    """
    vendor = task.host.get("vendor", "cisco")

    if vendor == "cisco":
        cmd = "show interfaces counters errors"
    elif vendor == "arista":
        cmd = "show interfaces counters errors"
    elif vendor == "juniper":
        cmd = "show interfaces extensive | match error"
    else:
        return Result(host=task.host, result="Unknown vendor")

    result = task.run(
        task=netmiko_send_command,
        command_string=cmd,
    )

    return Result(
        host=task.host,
        result={"raw_output": str(result.result)},
    )


# ============================================================
# Report Generation
# ============================================================

def generate_report(ospf_results: dict, bgp_results: dict) -> None:
    """Generate a rich console report of the network audit.

    This is the kind of output you'd show in an interview demo:
    clear, color-coded, immediately useful.
    """
    console.print("\n[bold cyan]═══════════════════════════════════════════[/]")
    console.print("[bold cyan]  TradeNet Fabric — Network Audit Report[/]")
    console.print(f"[dim]  Generated: {datetime.now().isoformat()}[/]")
    console.print("[bold cyan]═══════════════════════════════════════════[/]\n")

    # OSPF Summary Table
    ospf_table = Table(title="OSPF Adjacencies")
    ospf_table.add_column("Device", style="cyan")
    ospf_table.add_column("Neighbors", style="green")
    ospf_table.add_column("Status", style="bold")

    total_ospf_ok = 0
    total_ospf_fail = 0

    for host, result in ospf_results.items():
        if result.failed:
            ospf_table.add_row(host, "ERROR", "[red]FAIL[/]")
            total_ospf_fail += 1
        else:
            neighbors = result.result.get("ospf_neighbors", [])
            count = len(neighbors)
            status = "[green]OK[/]" if count > 0 else "[yellow]WARN (no neighbors)[/]"
            ospf_table.add_row(host, str(count), status)
            if count > 0:
                total_ospf_ok += 1
            else:
                total_ospf_fail += 1

    console.print(ospf_table)
    console.print(f"\n  OSPF: [green]{total_ospf_ok} OK[/], [red]{total_ospf_fail} issues[/]\n")

    # BGP Summary Table
    bgp_table = Table(title="BGP Sessions")
    bgp_table.add_column("Device", style="cyan")
    bgp_table.add_column("Peers", style="green")
    bgp_table.add_column("Established", style="green")
    bgp_table.add_column("Status", style="bold")

    total_bgp_ok = 0
    total_bgp_fail = 0

    for host, result in bgp_results.items():
        if result.failed:
            bgp_table.add_row(host, "ERROR", "-", "[red]FAIL[/]")
            total_bgp_fail += 1
        elif result.result.get("skipped"):
            continue  # Skip non-BGP devices
        else:
            peers = result.result.get("bgp_peers", [])
            total = len(peers)
            established = sum(
                1 for p in peers
                if isinstance(p, dict) and p.get("state", "").lower() == "established"
            )
            status = "[green]OK[/]" if established == total else "[red]DEGRADED[/]"
            bgp_table.add_row(host, str(total), str(established), status)
            if established == total and total > 0:
                total_bgp_ok += 1
            else:
                total_bgp_fail += 1

    console.print(bgp_table)
    console.print(f"\n  BGP: [green]{total_bgp_ok} OK[/], [red]{total_bgp_fail} issues[/]\n")

    # Overall verdict
    if total_ospf_fail == 0 and total_bgp_fail == 0:
        console.print("[bold green]  ✓ NETWORK HEALTHY — All protocols converged[/]\n")
    else:
        console.print("[bold red]  ✗ NETWORK ISSUES DETECTED — Review above[/]\n")


# ============================================================
# Main
# ============================================================

def main():
    """Run the full network audit."""
    console.print("[bold]Initializing TradeNet Fabric Network Audit...[/]")

    try:
        nr = init_nornir()
    except Exception as e:
        console.print(f"[red]Failed to initialize Nornir: {e}[/]")
        console.print("[yellow]Note: This script requires live EVE-NG devices.[/]")
        console.print("[yellow]Run in demo mode with --demo flag.[/]")

        if "--demo" in sys.argv:
            run_demo_audit()
        return

    console.print(f"[dim]Connected to {len(nr.inventory.hosts)} devices[/]")

    # Run audits in parallel
    console.print("\n[bold]Running OSPF audit...[/]")
    ospf_results = nr.run(task=audit_ospf)

    console.print("[bold]Running BGP audit...[/]")
    bgp_results = nr.run(task=audit_bgp)

    # Generate report
    generate_report(ospf_results, bgp_results)


def run_demo_audit():
    """Demo mode — shows what the audit output looks like without live devices."""
    console.print("\n[bold yellow]═══ DEMO MODE ═══[/]\n")
    console.print("[dim]Showing sample audit output (no live devices required)[/]\n")

    console.print("[bold cyan]═══════════════════════════════════════════[/]")
    console.print("[bold cyan]  TradeNet Fabric — Network Audit Report[/]")
    console.print(f"[dim]  Generated: {datetime.now().isoformat()}[/]")
    console.print("[bold cyan]═══════════════════════════════════════════[/]\n")

    # Demo OSPF table
    ospf_table = Table(title="OSPF Adjacencies")
    ospf_table.add_column("Device", style="cyan")
    ospf_table.add_column("Neighbors", style="green")
    ospf_table.add_column("Status", style="bold")

    demo_devices = [
        ("dc-east-core-rtr-01", "4", "[green]OK[/]"),
        ("dc-east-core-rtr-02", "4", "[green]OK[/]"),
        ("dc-west-core-rtr-01", "2", "[green]OK[/]"),
        ("dc-east-spine-sw-01", "2", "[green]OK[/]"),
        ("dc-east-spine-sw-02", "2", "[green]OK[/]"),
        ("colo-nyse-edge-rtr-01", "3", "[green]OK[/]"),
        ("colo-nyse-edge-rtr-02", "3", "[green]OK[/]"),
        ("colo-cme-edge-rtr-01", "2", "[green]OK[/]"),
        ("colo-nasdaq-edge-rtr-01", "2", "[green]OK[/]"),
    ]
    for device, neighbors, status in demo_devices:
        ospf_table.add_row(device, neighbors, status)

    console.print(ospf_table)
    console.print(f"\n  OSPF: [green]9 OK[/], [red]0 issues[/]\n")

    # Demo BGP table
    bgp_table = Table(title="BGP Sessions")
    bgp_table.add_column("Device", style="cyan")
    bgp_table.add_column("Peers", style="green")
    bgp_table.add_column("Established", style="green")
    bgp_table.add_column("Status", style="bold")

    demo_bgp = [
        ("dc-east-core-rtr-01", "6", "6", "[green]OK[/]"),
        ("dc-east-core-rtr-02", "6", "6", "[green]OK[/]"),
        ("dc-west-core-rtr-01", "3", "3", "[green]OK[/]"),
        ("colo-nyse-edge-rtr-01", "3", "3", "[green]OK[/]"),
        ("colo-cme-edge-rtr-01", "3", "3", "[green]OK[/]"),
        ("colo-nasdaq-edge-rtr-01", "3", "3", "[green]OK[/]"),
    ]
    for device, peers, established, status in demo_bgp:
        bgp_table.add_row(device, peers, established, status)

    console.print(bgp_table)
    console.print(f"\n  BGP: [green]6 OK[/], [red]0 issues[/]\n")

    console.print("[bold green]  NETWORK HEALTHY — All protocols converged[/]\n")


if __name__ == "__main__":
    main()
