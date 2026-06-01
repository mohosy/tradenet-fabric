"""Demo topology builder.

Creates a small version of the trading firm topology for testing and demos.
This mirrors the original OCaml ``build_demo_topology`` exactly — same devices,
links, latencies, and OSPF costs — so the controller behaves identically.

In a full deployment this would be replaced by loading the YAML addressing plan
or discovering topology from live devices.
"""

from __future__ import annotations

import time

from .network_graph import (
    Device,
    DeviceRole,
    Link,
    LinkMetrics,
    LinkState,
    NetworkGraph,
)


def _default_metrics(latency: float) -> LinkMetrics:
    return LinkMetrics(
        latency_us=latency,
        jitter_us=10.0,
        utilization=0.1,
        packet_loss=0.0,
        last_updated=time.time(),
    )


def _make_link(
    link_id: str,
    src_if: str,
    dst_if: str,
    bw: int = 10000,
    cost: int = 10,
    latency: float = 100.0,
) -> Link:
    return Link(
        id=link_id,
        src_interface=src_if,
        dst_interface=dst_if,
        bandwidth_mbps=bw,
        state=LinkState.UP,
        metrics=_default_metrics(latency),
        ospf_cost=cost,
    )


def build_demo_topology() -> NetworkGraph:
    """Build the demo trading-firm topology (9 devices, 9 links)."""
    g = NetworkGraph.empty()

    # --- DC-East devices ---
    g = g.add_device(Device("dc-east-core-01", "DC-East Core Router 01",
                            DeviceRole.CORE_ROUTER, "dc-east", "10.1.0.1", "cisco", 65001))
    g = g.add_device(Device("dc-east-core-02", "DC-East Core Router 02",
                            DeviceRole.CORE_ROUTER, "dc-east", "10.1.0.2", "cisco", 65001))
    g = g.add_device(Device("dc-east-spine-01", "DC-East Spine Switch 01",
                            DeviceRole.SPINE_SWITCH, "dc-east", "10.1.0.11", "arista", 65001))
    g = g.add_device(Device("dc-east-spine-02", "DC-East Spine Switch 02",
                            DeviceRole.SPINE_SWITCH, "dc-east", "10.1.0.12", "arista", 65001))

    # --- DC-West devices ---
    g = g.add_device(Device("dc-west-core-01", "DC-West Core Router 01",
                            DeviceRole.CORE_ROUTER, "dc-west", "10.2.0.1", "cisco", 65001))
    g = g.add_device(Device("dc-west-spine-01", "DC-West Spine Switch 01",
                            DeviceRole.SPINE_SWITCH, "dc-west", "10.2.0.11", "arista", 65001))

    # --- Colo-NYSE devices ---
    g = g.add_device(Device("colo-nyse-edge-01", "NYSE Colo Edge Router 01",
                            DeviceRole.EDGE_ROUTER, "colo-nyse", "10.4.0.1", "juniper", 65001))
    g = g.add_device(Device("colo-nyse-edge-02", "NYSE Colo Edge Router 02",
                            DeviceRole.EDGE_ROUTER, "colo-nyse", "10.4.0.2", "juniper", 65001))

    # --- NYSE Exchange (simulated) ---
    g = g.add_device(Device("nyse-exchange", "NYSE Exchange Router",
                            DeviceRole.EXCHANGE_ROUTER, "nyse", "198.51.100.1", "cisco", 11111))

    # --- DC-East internal links ---
    g = g.add_link("dc-east-core-01", "dc-east-core-02",
                   _make_link("dc-east-core-01--dc-east-core-02",
                              "GigabitEthernet0/1", "GigabitEthernet0/1", latency=50.0, cost=5))
    g = g.add_link("dc-east-core-01", "dc-east-spine-01",
                   _make_link("dc-east-core-01--dc-east-spine-01",
                              "GigabitEthernet0/2", "Ethernet1", latency=30.0, cost=3))
    g = g.add_link("dc-east-core-02", "dc-east-spine-02",
                   _make_link("dc-east-core-02--dc-east-spine-02",
                              "GigabitEthernet0/2", "Ethernet1", latency=30.0, cost=3))

    # --- Inter-site WAN: DC-East <-> DC-West (5ms WAN latency) ---
    g = g.add_link("dc-east-core-01", "dc-west-core-01",
                   _make_link("dc-east-core-01--dc-west-core-01",
                              "GigabitEthernet0/3", "GigabitEthernet0/3",
                              bw=10000, latency=5000.0, cost=100))

    # --- DC-West internal ---
    g = g.add_link("dc-west-core-01", "dc-west-spine-01",
                   _make_link("dc-west-core-01--dc-west-spine-01",
                              "GigabitEthernet0/2", "Ethernet1", latency=30.0, cost=3))

    # --- DC-East <-> Colo-NYSE ---
    g = g.add_link("dc-east-core-01", "colo-nyse-edge-01",
                   _make_link("dc-east-core-01--colo-nyse-edge-01",
                              "GigabitEthernet0/4", "ge-0/0/0", bw=10000, latency=200.0, cost=20))
    g = g.add_link("dc-east-core-02", "colo-nyse-edge-02",
                   _make_link("dc-east-core-02--colo-nyse-edge-02",
                              "GigabitEthernet0/4", "ge-0/0/0", bw=10000, latency=200.0, cost=20))

    # --- Colo-NYSE internal + exchange peering ---
    g = g.add_link("colo-nyse-edge-01", "colo-nyse-edge-02",
                   _make_link("colo-nyse-edge-01--colo-nyse-edge-02",
                              "ge-0/0/1", "ge-0/0/1", latency=10.0, cost=1))
    g = g.add_link("colo-nyse-edge-01", "nyse-exchange",
                   _make_link("colo-nyse-edge-01--nyse-exchange",
                              "ge-0/0/2", "GigabitEthernet0/0",
                              bw=10000, latency=5.0, cost=1))  # Ultra-low latency to exchange

    return g
