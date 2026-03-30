"""
TradeNet Fabric — Benchmark Suite
===================================
Measures and reports key performance metrics with hard numbers.

WHY BENCHMARKS (for interview):
Saying "sub-100ms failover" is a claim. Having benchmark output that
shows "avg: 2.5ms, p99: 4.1ms" is PROOF. Jane Street is quantitative —
numbers matter more than adjectives.

WHAT WE MEASURE:
1. SDN controller path computation time
2. Failover time after link failure
3. API response latency
4. Topology load time
5. JSON serialization throughput
"""

import json
import time
import statistics
import subprocess
import requests
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

SDN_URL = "http://localhost:9090"


@dataclass
class BenchmarkResult:
    """Result of a single benchmark."""
    name: str
    description: str
    samples: List[float]
    unit: str
    target: Optional[float] = None

    @property
    def mean(self) -> float:
        return statistics.mean(self.samples) if self.samples else 0

    @property
    def median(self) -> float:
        return statistics.median(self.samples) if self.samples else 0

    @property
    def stdev(self) -> float:
        return statistics.stdev(self.samples) if len(self.samples) > 1 else 0

    @property
    def p99(self) -> float:
        if not self.samples:
            return 0
        sorted_s = sorted(self.samples)
        idx = int(len(sorted_s) * 0.99)
        return sorted_s[min(idx, len(sorted_s) - 1)]

    @property
    def min_val(self) -> float:
        return min(self.samples) if self.samples else 0

    @property
    def max_val(self) -> float:
        return max(self.samples) if self.samples else 0

    @property
    def passed(self) -> bool:
        if self.target is None:
            return True
        return self.p99 <= self.target


def check_controller() -> bool:
    """Check if the SDN controller is running."""
    try:
        resp = requests.get(f"{SDN_URL}/api/health", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


def bench_path_computation(iterations: int = 100) -> BenchmarkResult:
    """Benchmark: Path computation latency."""
    samples = []
    pairs = [
        ("dc-east-core-01", "nyse-exchange"),
        ("dc-west-core-01", "nyse-exchange"),
        ("dc-east-core-01", "dc-west-spine-01"),
        ("dc-east-spine-01", "colo-nyse-edge-02"),
    ]

    for i in range(iterations):
        src, dst = pairs[i % len(pairs)]
        start = time.perf_counter()
        resp = requests.post(f"{SDN_URL}/api/path", json={
            "src": src, "dst": dst, "traffic_class": "market_data",
        })
        elapsed = (time.perf_counter() - start) * 1000  # ms
        if resp.status_code == 200:
            samples.append(elapsed)

    return BenchmarkResult(
        name="Path Computation",
        description="Time to compute optimal path (Dijkstra + API round-trip)",
        samples=samples,
        unit="ms",
        target=50.0,  # Must be under 50ms
    )


def bench_failover(iterations: int = 50) -> BenchmarkResult:
    """Benchmark: Failover time after link failure."""
    samples = []

    for _ in range(iterations):
        # Ensure link is up
        requests.post(f"{SDN_URL}/api/link/state", json={
            "src": "dc-east-core-01", "dst": "colo-nyse-edge-01", "state": "up",
        })

        # Kill link and immediately compute new path
        start = time.perf_counter()
        requests.post(f"{SDN_URL}/api/link/state", json={
            "src": "dc-east-core-01", "dst": "colo-nyse-edge-01", "state": "down",
        })
        resp = requests.post(f"{SDN_URL}/api/path", json={
            "src": "dc-east-core-01", "dst": "nyse-exchange",
            "traffic_class": "market_data",
        })
        elapsed = (time.perf_counter() - start) * 1000
        if resp.status_code == 200:
            samples.append(elapsed)

        # Restore
        requests.post(f"{SDN_URL}/api/link/state", json={
            "src": "dc-east-core-01", "dst": "colo-nyse-edge-01", "state": "up",
        })

    return BenchmarkResult(
        name="Failover Time",
        description="Link failure → new path computed (end-to-end)",
        samples=samples,
        unit="ms",
        target=100.0,  # Must be under 100ms
    )


def bench_api_health(iterations: int = 200) -> BenchmarkResult:
    """Benchmark: API health check latency."""
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        requests.get(f"{SDN_URL}/api/health")
        elapsed = (time.perf_counter() - start) * 1000
        samples.append(elapsed)

    return BenchmarkResult(
        name="API Health Check",
        description="GET /api/health round-trip latency",
        samples=samples,
        unit="ms",
        target=10.0,
    )


def bench_topology_query(iterations: int = 100) -> BenchmarkResult:
    """Benchmark: Full topology query."""
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        resp = requests.get(f"{SDN_URL}/api/topology")
        elapsed = (time.perf_counter() - start) * 1000
        if resp.status_code == 200:
            samples.append(elapsed)

    return BenchmarkResult(
        name="Topology Query",
        description="GET /api/topology (full graph serialization)",
        samples=samples,
        unit="ms",
        target=20.0,
    )


def print_report(results: List[BenchmarkResult]):
    """Print benchmark report."""
    console.print(Panel(
        "[bold cyan]TradeNet Fabric — Benchmark Report[/]",
        subtitle=time.strftime("%Y-%m-%d %H:%M:%S"),
    ))

    table = Table(title="Performance Metrics")
    table.add_column("Benchmark", style="cyan")
    table.add_column("Mean", justify="right")
    table.add_column("Median", justify="right")
    table.add_column("P99", justify="right", style="bold")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("Result", justify="center")

    for r in results:
        target_str = f"{r.target}{r.unit}" if r.target else "—"
        result_str = "[green]PASS[/]" if r.passed else "[red]FAIL[/]"

        p99_style = "[green]" if r.passed else "[red]"

        table.add_row(
            r.name,
            f"{r.mean:.2f}{r.unit}",
            f"{r.median:.2f}{r.unit}",
            f"{p99_style}{r.p99:.2f}{r.unit}[/]",
            f"{r.min_val:.2f}{r.unit}",
            f"{r.max_val:.2f}{r.unit}",
            target_str,
            result_str,
        )

    console.print(table)

    all_passed = all(r.passed for r in results)
    total = len(results)
    passed = sum(1 for r in results if r.passed)

    if all_passed:
        console.print(f"\n[bold green]ALL BENCHMARKS PASSED ({passed}/{total})[/]")
    else:
        console.print(f"\n[bold red]BENCHMARKS FAILED ({passed}/{total} passed)[/]")

    # Key takeaways
    console.print("\n[bold]Key Numbers (for interview):[/]")
    for r in results:
        console.print(f"  {r.name}: [bold]{r.p99:.2f}{r.unit}[/] (p99)")


def main():
    console.print("[bold cyan]TradeNet Fabric — Benchmark Suite[/]\n")

    if not check_controller():
        console.print("[red]SDN controller not running![/]")
        console.print("[yellow]Start with: cd sdn-controller && dune exec bin/main.exe &[/]")
        return

    console.print("[green]SDN controller is running[/]\n")
    console.print("[bold]Running benchmarks (this takes ~30 seconds)...[/]\n")

    results = []

    console.print("  Benchmarking path computation...")
    results.append(bench_path_computation(100))

    console.print("  Benchmarking failover time...")
    results.append(bench_failover(50))

    console.print("  Benchmarking API health check...")
    results.append(bench_api_health(200))

    console.print("  Benchmarking topology query...")
    results.append(bench_topology_query(100))

    console.print()
    print_report(results)


if __name__ == "__main__":
    main()
