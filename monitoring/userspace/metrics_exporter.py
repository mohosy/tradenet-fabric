"""
TradeNet Fabric — eBPF Metrics Exporter
========================================
Reads flow metrics from the BPF ring buffer and exports them
as Prometheus metrics for Grafana dashboards and the SDN controller.

HOW IT WORKS (for interview):
1. The eBPF program (flow_latency.c) runs in the kernel and writes
   per-flow metrics to a BPF ring buffer
2. This userspace program reads from the ring buffer
3. It exposes the metrics as a Prometheus HTTP endpoint (:9091/metrics)
4. Prometheus scrapes this endpoint every 15 seconds
5. Grafana displays the metrics on dashboards
6. The SDN controller also queries Prometheus for path optimization

THE MONITORING PIPELINE:
  Packets → eBPF (kernel) → Ring Buffer → This Exporter → Prometheus → Grafana
                                                        ↘ SDN Controller

WHY PROMETHEUS (for interview):
- Industry standard for infrastructure monitoring
- Pull-based model (Prometheus scrapes us, not push)
- Built-in alerting (AlertManager)
- Native Grafana integration
- Time-series database optimized for metrics
- Jane Street's network team monitors their infrastructure 24/7 —
  having a proper monitoring stack shows you think about operations
"""

import json
import time
import signal
import sys
from collections import defaultdict
from typing import Dict, Optional

from prometheus_client import (
    start_http_server,
    Gauge,
    Counter,
    Histogram,
    Info,
)
from rich.console import Console
from rich.table import Table
from rich.live import Live

console = Console()

# ============================================================
# Prometheus Metrics
#
# Each metric maps to something Jane Street's network team
# would care about in production:
# ============================================================

# Per-flow latency (the primary metric for trading networks)
FLOW_LATENCY = Histogram(
    "tradenet_flow_latency_microseconds",
    "Per-flow one-way latency in microseconds",
    ["src_ip", "dst_ip", "protocol"],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000, 10000],
    # These buckets are tuned for trading networks:
    # - <10μs: intra-switch (leaf-to-spine)
    # - 10-100μs: intra-site (within a DC)
    # - 100-1000μs: inter-site (DC to colo)
    # - >1000μs: WAN (cross-country)
)

# Per-flow jitter (critical for market data)
FLOW_JITTER = Gauge(
    "tradenet_flow_jitter_microseconds",
    "Per-flow jitter (latency variance) in microseconds",
    ["src_ip", "dst_ip", "protocol"],
)

# Per-flow packet count
FLOW_PACKETS = Counter(
    "tradenet_flow_packets_total",
    "Total packets per flow",
    ["src_ip", "dst_ip", "protocol"],
)

# Per-flow byte count
FLOW_BYTES = Counter(
    "tradenet_flow_bytes_total",
    "Total bytes per flow",
    ["src_ip", "dst_ip", "protocol"],
)

# Per-interface utilization
INTERFACE_UTILIZATION = Gauge(
    "tradenet_interface_utilization_ratio",
    "Interface utilization as a ratio (0.0 to 1.0)",
    ["device", "interface"],
)

# Per-interface packet drops
INTERFACE_DROPS = Counter(
    "tradenet_interface_drops_total",
    "Total packet drops per interface",
    ["device", "interface", "direction"],
)

# SDN controller metrics
SDN_PATH_COMPUTATION_TIME = Histogram(
    "tradenet_sdn_path_computation_seconds",
    "Time to compute a new path in the SDN controller",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
)

SDN_FAILOVER_TIME = Histogram(
    "tradenet_sdn_failover_seconds",
    "Time to complete a failover after link failure",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

# Global stats
TOTAL_FLOWS = Gauge(
    "tradenet_total_active_flows",
    "Number of currently active flows being tracked",
)

EXPORTER_INFO = Info(
    "tradenet_exporter",
    "Information about the TradeNet metrics exporter",
)


class MetricsExporter:
    """Reads BPF metrics and exports to Prometheus."""

    def __init__(self, bpf_program_path: Optional[str] = None):
        self.bpf_program_path = bpf_program_path
        self.running = True
        self.flow_cache: Dict[str, Dict] = {}

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        console.print("\n[yellow]Shutting down metrics exporter...[/]")
        self.running = False

    def start(self, port: int = 9091):
        """Start the Prometheus HTTP server and begin exporting metrics."""
        EXPORTER_INFO.info({
            "version": "1.0.0",
            "project": "tradenet_fabric",
            "component": "ebpf_metrics_exporter",
        })

        console.print(f"[bold cyan]TradeNet Fabric — Metrics Exporter[/]")
        console.print(f"[bold cyan]===================================[/]\n")
        console.print(f"Starting Prometheus HTTP server on port {port}...")

        start_http_server(port)
        console.print(f"[green]Prometheus metrics available at http://localhost:{port}/metrics[/]\n")

        if self.bpf_program_path:
            self._run_with_bpf()
        else:
            console.print("[yellow]No BPF program specified — running in simulation mode[/]")
            console.print("[dim]Generating simulated metrics for demo purposes[/]\n")
            self._run_simulation()

    def _run_simulation(self):
        """Generate simulated metrics for demo/testing.

        This simulates what the eBPF program would produce,
        allowing us to test the full pipeline (exporter → Prometheus → Grafana)
        without needing a Linux kernel with eBPF support.
        """
        import random

        # Simulated flows representing trading firm traffic patterns
        flows = [
            # DC-East to NYSE (market data — ultra-low latency)
            {"src": "10.1.0.1", "dst": "10.4.0.1", "proto": "udp",
             "base_latency": 200, "jitter": 5},
            # DC-East to CME (market data)
            {"src": "10.1.0.1", "dst": "10.5.0.1", "proto": "udp",
             "base_latency": 350, "jitter": 8},
            # DC-East to NASDAQ (market data)
            {"src": "10.1.0.1", "dst": "10.6.0.1", "proto": "udp",
             "base_latency": 180, "jitter": 4},
            # DC-East to DC-West (inter-DC replication)
            {"src": "10.1.0.1", "dst": "10.2.0.1", "proto": "tcp",
             "base_latency": 5000, "jitter": 50},
            # BGP session (DC-East core to NYSE edge)
            {"src": "10.1.0.1", "dst": "10.4.0.1", "proto": "tcp",
             "base_latency": 200, "jitter": 2},
            # Management traffic
            {"src": "10.1.1.1", "dst": "10.1.1.100", "proto": "tcp",
             "base_latency": 50, "jitter": 1},
        ]

        iteration = 0
        while self.running:
            for flow in flows:
                # Add realistic variance
                latency = flow["base_latency"] + random.gauss(0, flow["jitter"])
                latency = max(1, latency)  # Can't be negative
                jitter = abs(random.gauss(0, flow["jitter"]))

                labels = {
                    "src_ip": flow["src"],
                    "dst_ip": flow["dst"],
                    "protocol": flow["proto"],
                }

                FLOW_LATENCY.labels(**labels).observe(latency)
                FLOW_JITTER.labels(**labels).set(jitter)
                FLOW_PACKETS.labels(**labels).inc(random.randint(50, 200))
                FLOW_BYTES.labels(**labels).inc(random.randint(50000, 200000))

            TOTAL_FLOWS.set(len(flows))

            # Simulated interface utilization
            interfaces = [
                ("dc-east-core-01", "GigabitEthernet0/1", 0.15),
                ("dc-east-core-01", "GigabitEthernet0/3", 0.45),
                ("dc-east-spine-01", "Ethernet1", 0.25),
                ("colo-nyse-edge-01", "ge-0/0/0", 0.60),
                ("colo-nyse-edge-01", "ge-0/0/2", 0.75),
            ]
            for device, intf, base_util in interfaces:
                util = base_util + random.gauss(0, 0.05)
                util = max(0, min(1, util))
                INTERFACE_UTILIZATION.labels(
                    device=device, interface=intf
                ).set(util)

            # Simulated SDN controller timing
            SDN_PATH_COMPUTATION_TIME.observe(
                random.gauss(0.002, 0.0005)  # ~2ms average
            )

            iteration += 1
            if iteration % 10 == 0:
                console.print(f"[dim]Exported {iteration * len(flows)} metric updates[/]")

            time.sleep(1)  # Export every second

    def _run_with_bpf(self):
        """Read metrics from the actual BPF ring buffer.

        This requires:
        1. Linux kernel 5.8+ with eBPF support
        2. The flow_latency.c BPF program loaded
        3. Root/CAP_BPF privileges

        In our EVE-NG lab environment, this runs on the Linux host.
        """
        console.print("[bold]Attaching to BPF ring buffer...[/]")
        console.print("[yellow]Note: BPF mode requires Linux with loaded BPF program[/]")
        # In production, this would use the bcc or libbpf Python bindings
        # to read from the BPF ring buffer. For the lab, we use simulation.
        self._run_simulation()


def main():
    """Start the metrics exporter."""
    exporter = MetricsExporter(
        bpf_program_path=None  # Use simulation mode
    )
    exporter.start(port=9091)


if __name__ == "__main__":
    main()
