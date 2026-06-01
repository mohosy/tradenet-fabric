"""TradeNet Fabric — SDN Controller entry point.

Run with:  python3 -m tradenet_sdn   (from the sdn-controller/ directory)

This:
  1. Builds the demo network topology
  2. Computes a couple of demo optimal paths (to verify the engine works)
  3. Starts the REST API server on port 9090
"""

from __future__ import annotations

from .demo_topology import build_demo_topology
from .path_engine import TrafficClass, compute_path
from . import server


def _print_path_demo(graph, src: str, dst: str, label: str, show_bottleneck: bool) -> None:
    result = compute_path(graph, src, dst, TrafficClass.MARKET_DATA, constraints=[])
    if result is None:
        print("  No path found!")
        return
    print(f"  {label} (Market Data):")
    print(f"    Latency: {result.total_latency_us:.1f} μs")
    print(f"    Hops: {result.hop_count}")
    if show_bottleneck:
        print(f"    Bottleneck BW: {result.bottleneck_bandwidth} Mbps")
    path_str = "".join(f"{node} → " for node, _link in result.path)
    print(f"    Path: {path_str}(destination)")


def main() -> None:
    print("TradeNet Fabric — SDN Controller")
    print("================================\n")

    graph = build_demo_topology()
    devices = graph.all_devices()
    links = graph.all_links()
    print(f"Topology loaded: {len(devices)} devices, {len(links)} links\n")

    print("Computing optimal paths...")
    _print_path_demo(graph, "dc-east-core-01", "nyse-exchange",
                     "DC-East → NYSE Exchange", show_bottleneck=True)
    print()
    _print_path_demo(graph, "dc-west-core-01", "nyse-exchange",
                     "DC-West → NYSE Exchange", show_bottleneck=False)
    print()

    server.init(graph)
    print("Starting API server on port 9090...")
    print("Endpoints:")
    print("  GET  /api/health     — Health check")
    print("  GET  /api/topology   — Full network graph")
    print("  GET  /api/devices    — List all devices")
    print("  GET  /api/links      — List all links with metrics")
    print("  POST /api/path       — Compute optimal path")
    print("  POST /api/link/state — Update link state (chaos)")
    print()
    server.start(port=9090)


if __name__ == "__main__":
    main()
