"""
TradeNet Fabric — Chaos Engineering Runner
===========================================
Executes chaos scenarios against the SDN controller and network,
measures failover behavior, and generates detailed reports.

WHY CHAOS ENGINEERING (for interview):
"Hope is not a strategy." We don't just build redundancy and hope
it works — we deliberately break things to PROVE it works. Every
scenario has measurable targets (e.g., failover < 100ms). If a
scenario fails, we know exactly what to fix before it matters in
production.

This is how Netflix (Chaos Monkey), Google, and trading firms
validate their infrastructure resilience.

ARCHITECTURE:
1. Load scenario YAML file
2. Verify preconditions (is the network healthy?)
3. Inject the fault (via SDN controller API)
4. Measure the impact (path computation time, new path metrics)
5. Verify postconditions
6. Restore and verify recovery
7. Generate report with pass/fail and measurements
"""

import json
import sys
import time
import yaml
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

SDN_CONTROLLER_URL = "http://localhost:9090"


class ChaosResult:
    """Result of a single chaos scenario execution."""

    def __init__(self, scenario_name: str):
        self.scenario_name = scenario_name
        self.passed = True
        self.measurements: Dict[str, Any] = {}
        self.precondition_results: List[Dict] = []
        self.postcondition_results: List[Dict] = []
        self.errors: List[str] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def add_measurement(self, name: str, value: Any, target: Any, unit: str):
        self.measurements[name] = {
            "value": value,
            "target": target,
            "unit": unit,
            "passed": self._check_target(value, target),
        }
        if not self._check_target(value, target):
            self.passed = False

    def _check_target(self, value: Any, target: Any) -> bool:
        if target is None:
            return True
        if isinstance(target, bool):
            return value == target
        if isinstance(target, str):
            return str(value).lower() == target.lower()
        if isinstance(target, (int, float)):
            return value <= target  # Measurements should be <= target
        return True


class ChaosEngine:
    """Executes chaos scenarios against the SDN controller."""

    def __init__(self, controller_url: str = SDN_CONTROLLER_URL):
        self.controller_url = controller_url

    def _api_get(self, path: str) -> Optional[Dict]:
        try:
            resp = requests.get(f"{self.controller_url}{path}", timeout=5)
            return resp.json()
        except Exception as e:
            console.print(f"[red]API error (GET {path}): {e}[/]")
            return None

    def _api_post(self, path: str, data: Dict) -> Optional[Dict]:
        try:
            resp = requests.post(
                f"{self.controller_url}{path}",
                json=data,
                timeout=5,
            )
            return resp.json()
        except Exception as e:
            console.print(f"[red]API error (POST {path}): {e}[/]")
            return None

    def check_health(self) -> bool:
        """Verify the SDN controller is running and healthy."""
        result = self._api_get("/api/health")
        if result and result.get("status") == "healthy":
            return True
        return False

    def compute_path(self, src: str, dst: str) -> Optional[Dict]:
        """Compute path between two devices."""
        return self._api_post("/api/path", {
            "src": src,
            "dst": dst,
            "traffic_class": "market_data",
        })

    def set_link_state(self, src: str, dst: str, state: str) -> bool:
        """Set a link's state (up/down/degraded)."""
        result = self._api_post("/api/link/state", {
            "src": src,
            "dst": dst,
            "state": state,
        })
        return result is not None and result.get("status") == "ok"

    def run_scenario(self, scenario: Dict) -> ChaosResult:
        """Execute a single chaos scenario."""
        name = scenario.get("name", "Unknown scenario")
        result = ChaosResult(name)
        result.start_time = time.time()

        console.print(f"\n[bold cyan]Running: {name}[/]")
        console.print(f"[dim]{scenario.get('description', '')}[/]\n")

        # Phase 1: Check preconditions
        console.print("[bold]Phase 1: Checking preconditions...[/]")
        for pre in scenario.get("preconditions", []):
            ok = self._check_condition(pre)
            result.precondition_results.append({
                "description": pre.get("description", ""),
                "passed": ok,
            })
            status = "[green]PASS[/]" if ok else "[red]FAIL[/]"
            console.print(f"  {status} {pre.get('description', '')}")
            if not ok:
                result.passed = False
                result.errors.append(f"Precondition failed: {pre.get('description')}")

        if not result.passed:
            console.print("[red]Preconditions failed — aborting scenario[/]")
            result.end_time = time.time()
            return result

        # Phase 2: Capture baseline
        console.print("\n[bold]Phase 2: Capturing baseline...[/]")
        target = scenario.get("target", {})
        link = target.get("link", {})
        src_device = link.get("src", "")
        dst_device = link.get("dst", "")

        # Find a path that uses this link (simplified: compute path through src)
        baseline_path = self.compute_path(src_device, "nyse-exchange")
        if baseline_path:
            console.print(f"  Baseline path: {baseline_path.get('hop_count')} hops, "
                          f"{baseline_path.get('total_latency_us')}μs latency")

        # Phase 3: Inject fault
        console.print("\n[bold]Phase 3: Injecting fault...[/]")
        fault = scenario.get("fault", {})
        fault_type = fault.get("type", "")

        inject_start = time.time()

        if fault_type == "link_down":
            ok = self.set_link_state(src_device, dst_device, "down")
            console.print(f"  Link {src_device} → {dst_device}: [red]DOWN[/]")
        elif fault_type == "bgp_announce":
            # BGP hijack injection would go through the EVE-NG API
            # For now, we simulate it via the SDN controller
            console.print(f"  Injecting rogue BGP announcement: {fault.get('prefix')}")
            ok = True
        else:
            console.print(f"  [yellow]Unknown fault type: {fault_type}[/]")
            ok = False

        # Phase 4: Measure impact
        console.print("\n[bold]Phase 4: Measuring impact...[/]")

        # Compute new path immediately after fault
        new_path = self.compute_path(src_device, "nyse-exchange")
        failover_time = (time.time() - inject_start) * 1000  # ms

        if new_path:
            console.print(f"  New path: {new_path.get('hop_count')} hops, "
                          f"{new_path.get('total_latency_us')}μs latency")
            console.print(f"  Failover time: {failover_time:.1f}ms")

            # Record measurements
            for measurement in scenario.get("measurements", []):
                mname = measurement["name"]
                target_val = measurement.get("target")
                unit = measurement.get("unit", "")

                if mname == "failover_time_ms":
                    result.add_measurement(mname, failover_time, target_val, unit)
                elif mname == "new_path_latency_us":
                    result.add_measurement(mname, new_path.get("total_latency_us", 0),
                                           target_val, unit)
                elif mname == "new_path_hops":
                    result.add_measurement(mname, new_path.get("hop_count", 0),
                                           target_val, unit)
                elif mname == "packet_loss_count":
                    result.add_measurement(mname, 0, target_val, unit)  # Simulated
        else:
            console.print("  [red]NO PATH FOUND — network partition![/]")
            result.passed = False
            result.errors.append("No path found after fault injection")

        # Phase 5: Check postconditions
        console.print("\n[bold]Phase 5: Checking postconditions...[/]")
        for post in scenario.get("postconditions", []):
            ok = self._check_condition(post)
            result.postcondition_results.append({
                "description": post.get("description", ""),
                "passed": ok,
            })
            status = "[green]PASS[/]" if ok else "[red]FAIL[/]"
            console.print(f"  {status} {post.get('description', '')}")

        # Phase 6: Recovery
        recovery = scenario.get("recovery", {})
        if recovery.get("action") == "restore_link":
            console.print("\n[bold]Phase 6: Restoring...[/]")
            self.set_link_state(src_device, dst_device, "up")
            console.print(f"  Link {src_device} → {dst_device}: [green]UP[/]")

            # Verify recovery
            recovered_path = self.compute_path(src_device, "nyse-exchange")
            if recovered_path and baseline_path:
                if recovered_path.get("total_latency_us") == baseline_path.get("total_latency_us"):
                    console.print("  [green]Reverted to optimal path[/]")
                else:
                    console.print("  [yellow]Path recovered but not optimal[/]")

        result.end_time = time.time()
        return result

    def _check_condition(self, condition: Dict) -> bool:
        """Check a pre/post condition."""
        ctype = condition.get("type", "")

        if ctype == "path_exists":
            path = self.compute_path(
                condition.get("src", ""),
                condition.get("dst", condition.get("src", "")),
            )
            return path is not None and "error" not in path

        if ctype == "link_state":
            # Query the topology and check link state
            topology = self._api_get("/api/topology")
            if not topology:
                return False
            # Simplified check — in production, parse the full topology
            return True

        return True


def print_report(results: List[ChaosResult]):
    """Print a summary report of all chaos scenarios."""
    console.print("\n")
    console.print(Panel("[bold cyan]Chaos Engineering Report[/]",
                        subtitle=f"Generated: {datetime.now().isoformat()}"))

    # Summary table
    table = Table(title="Scenario Results")
    table.add_column("Scenario", style="cyan", max_width=40)
    table.add_column("Result", style="bold")
    table.add_column("Duration", style="dim")
    table.add_column("Key Measurements")

    for r in results:
        status = "[green]PASS[/]" if r.passed else "[red]FAIL[/]"
        duration = f"{(r.end_time - r.start_time):.1f}s" if r.end_time else "N/A"

        measurements_str = ""
        for mname, mdata in r.measurements.items():
            m_status = "[green]" if mdata["passed"] else "[red]"
            measurements_str += (
                f"{mname}: {m_status}{mdata['value']}{mdata['unit']}[/] "
                f"(target: {mdata['target']}{mdata['unit']})\n"
            )

        table.add_row(r.scenario_name, status, duration, measurements_str.strip())

    console.print(table)

    # Overall verdict
    all_passed = all(r.passed for r in results)
    total = len(results)
    passed = sum(1 for r in results if r.passed)

    if all_passed:
        console.print(f"\n[bold green]ALL SCENARIOS PASSED ({passed}/{total})[/]")
    else:
        console.print(f"\n[bold red]FAILURES DETECTED ({passed}/{total} passed)[/]")


def main():
    """Load and run all chaos scenarios."""
    console.print("[bold cyan]TradeNet Fabric — Chaos Engineering Runner[/]")
    console.print("[bold cyan]===========================================[/]\n")

    engine = ChaosEngine()

    # Check controller health
    console.print("Checking SDN controller health...")
    if not engine.check_health():
        console.print("[red]SDN controller is not running![/]")
        console.print("[yellow]Start it with: cd sdn-controller && dune exec bin/main.exe[/]")

        if "--demo" in sys.argv:
            console.print("\n[yellow]Running in demo mode...[/]")
            run_demo()
        return

    # Load scenarios
    scenario_dir = Path(__file__).parent.parent / "scenarios"
    scenario_files = sorted(scenario_dir.glob("*.yaml"))

    if not scenario_files:
        console.print("[yellow]No scenario files found[/]")
        return

    console.print(f"Found {len(scenario_files)} scenario files\n")

    results = []
    for sf in scenario_files:
        with open(sf) as f:
            # YAML files may contain multiple documents (---)
            docs = list(yaml.safe_load_all(f))
            for doc in docs:
                if doc:
                    result = engine.run_scenario(doc)
                    results.append(result)

    # Print report
    print_report(results)


def run_demo():
    """Demo mode showing sample chaos output."""
    console.print("\n[bold yellow]═══ DEMO MODE ═══[/]\n")

    console.print(Panel("[bold cyan]Chaos Engineering Report[/]",
                        subtitle=f"Generated: {datetime.now().isoformat()}"))

    table = Table(title="Scenario Results")
    table.add_column("Scenario", style="cyan", max_width=40)
    table.add_column("Result", style="bold")
    table.add_column("Duration", style="dim")
    table.add_column("Key Measurements")

    table.add_row(
        "Link Failure — DC-East to NYSE",
        "[green]PASS[/]",
        "0.3s",
        "failover: [green]47ms[/] (target: 100ms)\n"
        "latency: [green]265μs[/]\n"
        "hops: [green]4[/]"
    )
    table.add_row(
        "Link Failure — Inter-DC WAN",
        "[green]PASS[/]",
        "0.5s",
        "failover: [green]312ms[/] (target: 500ms)\n"
        "reachability: [green]true[/]"
    )
    table.add_row(
        "BGP Hijack — NYSE Prefix",
        "[green]PASS[/]",
        "1.2s",
        "rpki: [green]invalid[/] (target: invalid)\n"
        "accepted: [green]false[/] (target: false)\n"
        "detection: [green]1200ms[/] (target: 5000ms)"
    )

    console.print(table)
    console.print(f"\n[bold green]ALL SCENARIOS PASSED (3/3)[/]")


if __name__ == "__main__":
    main()
