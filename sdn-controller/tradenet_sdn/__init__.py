"""TradeNet Fabric — SDN Controller (Python).

A software-defined networking controller that models a trading firm's network as
an immutable weighted graph, computes optimal paths with Dijkstra weighted by
live metrics, and exposes a REST API consumed by the dashboard, chaos framework,
and benchmark suite.

Public modules:
  - :mod:`tradenet_sdn.network_graph` — graph data structure + Dijkstra + JSON
  - :mod:`tradenet_sdn.path_engine`   — traffic classes, constraints, path results
  - :mod:`tradenet_sdn.server`        — Flask REST API
  - :mod:`tradenet_sdn.demo_topology` — the demo trading-firm topology
"""

from .network_graph import (
    Device,
    DeviceRole,
    Link,
    LinkMetrics,
    LinkState,
    NetworkGraph,
)
from .path_engine import (
    AvoidLink,
    AvoidSite,
    MaxHops,
    MaxLatency,
    PathResult,
    PreferSite,
    TrafficClass,
    compute_path,
    compute_routing_table,
)

__all__ = [
    "Device",
    "DeviceRole",
    "Link",
    "LinkMetrics",
    "LinkState",
    "NetworkGraph",
    "TrafficClass",
    "PathResult",
    "AvoidLink",
    "AvoidSite",
    "PreferSite",
    "MaxLatency",
    "MaxHops",
    "compute_path",
    "compute_routing_table",
]

__version__ = "1.0.0"
