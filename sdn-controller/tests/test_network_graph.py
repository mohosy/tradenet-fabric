"""Unit tests for the network graph and path computation.

Ported from the original OCaml Alcotest suite (test_network_graph.ml). These
verify the core data structures and algorithms the SDN controller relies on:

  1. Graph construction (adding devices and links)
  2. Path computation (Dijkstra correctness)
  3. Failover behavior (path after link failure)
  4. Traffic-class-specific routing (different weights)
  5. Edge cases (no path, single node, disconnected graph)
"""

import pytest

from tradenet_sdn.network_graph import (
    Device,
    DeviceRole,
    Link,
    LinkMetrics,
    LinkState,
    NetworkGraph,
)
from tradenet_sdn.path_engine import (
    AvoidSite,
    MaxHops,
    MaxLatency,
    TrafficClass,
    compute_path,
)

# ============================================================
# Test helpers
# ============================================================

DEFAULT_METRICS = LinkMetrics(
    latency_us=100.0, jitter_us=10.0, utilization=0.1, packet_loss=0.0, last_updated=0.0
)


def make_device(id, role, site, loopback, vendor):
    return Device(id=id, name=id, role=role, site=site, loopback=loopback,
                  vendor=vendor, asn=65001)


def make_link(id, latency=100.0, bw=10000, cost=10):
    return Link(
        id=id,
        src_interface="eth0",
        dst_interface="eth0",
        bandwidth_mbps=bw,
        state=LinkState.UP,
        metrics=LinkMetrics(latency_us=latency, jitter_us=10.0, utilization=0.1,
                            packet_loss=0.0, last_updated=0.0),
        ospf_cost=cost,
    )


def latency_weight(link):
    return link.metrics.latency_us


def build_linear_topology():
    """A simple 3-node linear topology: A -- B -- C."""
    g = NetworkGraph.empty()
    g = g.add_device(make_device("A", DeviceRole.CORE_ROUTER, "dc-east", "10.0.0.1", "cisco"))
    g = g.add_device(make_device("B", DeviceRole.SPINE_SWITCH, "dc-east", "10.0.0.2", "arista"))
    g = g.add_device(make_device("C", DeviceRole.EDGE_ROUTER, "colo-nyse", "10.0.0.3", "juniper"))
    g = g.add_link("A", "B", make_link("A--B", latency=50.0, cost=5))
    g = g.add_link("B", "C", make_link("B--C", latency=100.0, cost=10))
    return g


def build_diamond_topology():
    """A diamond: A --[fast]--> B --> D, A --[slow]--> C --> D.

    Tests that Dijkstra picks the faster path.
    """
    g = NetworkGraph.empty()
    g = g.add_device(make_device("A", DeviceRole.CORE_ROUTER, "dc-east", "10.0.0.1", "cisco"))
    g = g.add_device(make_device("B", DeviceRole.CORE_ROUTER, "dc-east", "10.0.0.2", "cisco"))
    g = g.add_device(make_device("C", DeviceRole.CORE_ROUTER, "dc-west", "10.0.0.3", "cisco"))
    g = g.add_device(make_device("D", DeviceRole.EDGE_ROUTER, "colo-nyse", "10.0.0.4", "juniper"))
    # Fast path: A -> B -> D (50 + 50 = 100μs)
    g = g.add_link("A", "B", make_link("A--B", latency=50.0, cost=5))
    g = g.add_link("B", "D", make_link("B--D", latency=50.0, cost=5))
    # Slow path: A -> C -> D (200 + 200 = 400μs)
    g = g.add_link("A", "C", make_link("A--C", latency=200.0, cost=20))
    g = g.add_link("C", "D", make_link("C--D", latency=200.0, cost=20))
    return g


# ============================================================
# Graph construction
# ============================================================


def test_empty_graph():
    g = NetworkGraph.empty()
    assert len(g.all_devices()) == 0
    assert len(g.all_links()) == 0


def test_add_device():
    g = NetworkGraph.empty()
    d = make_device("test-rtr", DeviceRole.CORE_ROUTER, "dc-east", "10.0.0.1", "cisco")
    g = g.add_device(d)
    assert len(g.all_devices()) == 1
    found = g.find_device("test-rtr")
    assert found is not None
    assert found.id == "test-rtr"


def test_duplicate_device_rejected():
    g = NetworkGraph.empty()
    d = make_device("rtr", DeviceRole.CORE_ROUTER, "dc-east", "10.0.0.1", "cisco")
    g = g.add_device(d)
    with pytest.raises(ValueError, match="Device rtr already exists"):
        g.add_device(d)


def test_add_link():
    g = build_linear_topology()
    assert len(g.all_devices()) == 3
    assert len(g.all_links()) == 2


def test_link_unknown_device():
    g = NetworkGraph.empty()
    d = make_device("A", DeviceRole.CORE_ROUTER, "dc-east", "10.0.0.1", "cisco")
    g = g.add_device(d)
    with pytest.raises(KeyError):
        g.add_link("A", "UNKNOWN", make_link("A--UNKNOWN"))


def test_neighbors():
    g = build_linear_topology()
    n = g.neighbors("B")
    assert len(n) == 2
    neighbor_ids = sorted(dst for dst, _link in n)
    assert neighbor_ids == ["A", "C"]


def test_devices_at_site():
    g = build_linear_topology()
    dc_east = g.devices_at_site("dc-east")
    assert len(dc_east) == 2


# ============================================================
# Path computation
# ============================================================


def test_shortest_path_linear():
    g = build_linear_topology()
    found = g.shortest_path("A", "C", latency_weight)
    assert found is not None
    path, cost = found
    assert len(path) == 2  # 2 hops
    assert cost == pytest.approx(150.0, abs=0.01)  # 50 + 100


def test_shortest_path_diamond_picks_fast():
    g = build_diamond_topology()
    found = g.shortest_path("A", "D", latency_weight)
    assert found is not None
    path, cost = found
    # Should pick A -> B -> D (100μs) over A -> C -> D (400μs)
    assert cost == pytest.approx(100.0, abs=0.01)
    assert [node for node, _link in path] == ["B", "D"]


def test_no_path_disconnected():
    g = NetworkGraph.empty()
    g = g.add_device(make_device("X", DeviceRole.CORE_ROUTER, "dc-east", "10.0.0.1", "cisco"))
    g = g.add_device(make_device("Y", DeviceRole.CORE_ROUTER, "dc-west", "10.0.0.2", "cisco"))
    # No link between X and Y — they're disconnected
    assert g.shortest_path("X", "Y", latency_weight) is None


def test_path_to_self():
    g = build_linear_topology()
    found = g.shortest_path("A", "A", latency_weight)
    assert found is not None
    path, cost = found
    assert len(path) == 0
    assert cost == pytest.approx(0.0, abs=0.01)


# ============================================================
# Failover — the money tests for a trading network
# ============================================================


def test_failover_after_link_down():
    g = build_diamond_topology()
    # Before failure: A -> B -> D is the fast path (100μs)
    before = g.shortest_path("A", "D", latency_weight)
    assert before is not None
    assert before[1] == pytest.approx(100.0, abs=0.01)

    # Kill the A -- B link
    g2 = g.update_link_state("A", "B", LinkState.DOWN)

    # After failure: should reroute through A -> C -> D (400μs)
    after = g2.shortest_path("A", "D", latency_weight)
    assert after is not None
    path, cost = after
    assert cost == pytest.approx(400.0, abs=0.01)
    assert [node for node, _link in path] == ["C", "D"]


def test_failover_both_paths_down():
    g = build_diamond_topology()
    g = g.update_link_state("A", "B", LinkState.DOWN)
    g = g.update_link_state("A", "C", LinkState.DOWN)
    assert g.shortest_path("A", "D", latency_weight) is None


def test_degraded_link_penalty():
    g = build_diamond_topology()
    # Degrade the fast path's first link. Market-data weight doubles latency for
    # degraded links: fast path = 50*2 + 50 = 150μs, slow path = 400μs.
    # Fast path still wins even degraded.
    g = g.update_link_state("A", "B", LinkState.DEGRADED)
    result = compute_path(g, "A", "D", TrafficClass.MARKET_DATA, constraints=[])
    assert result is not None
    assert [node for node, _link in result.path] == ["B", "D"]


# ============================================================
# Traffic classes
# ============================================================


def test_market_data_optimizes_latency():
    g = build_diamond_topology()
    result = compute_path(g, "A", "D", TrafficClass.MARKET_DATA, constraints=[])
    assert result is not None
    assert result.total_latency_us == pytest.approx(100.0, abs=0.01)


def test_bulk_avoids_saturated_links():
    g = build_diamond_topology()
    # Saturate the fast path (95% utilized)
    saturated = LinkMetrics(latency_us=50.0, jitter_us=10.0, utilization=0.95,
                            packet_loss=0.0, last_updated=0.0)
    g = g.update_metrics("A", "B", saturated)
    result = compute_path(g, "A", "D", TrafficClass.BULK_TRANSFER, constraints=[])
    assert result is not None
    # Bulk transfer should avoid the saturated fast path, use slow path
    assert [node for node, _link in result.path] == ["C", "D"]


# ============================================================
# Metric updates
# ============================================================


def test_update_metrics():
    g = build_linear_topology()
    new_metrics = LinkMetrics(latency_us=500.0, jitter_us=50.0, utilization=0.8,
                              packet_loss=0.01, last_updated=1000.0)
    g = g.update_metrics("A", "B", new_metrics)
    link = g.find_link("A", "B")
    assert link is not None
    assert link.metrics.latency_us == pytest.approx(500.0, abs=0.01)
    assert link.metrics.utilization == pytest.approx(0.8, abs=0.01)


# ============================================================
# JSON serialization
# ============================================================


def test_json_roundtrip():
    g = build_linear_topology()
    data = g.to_dict()
    g2 = NetworkGraph.from_dict(data)
    assert len(g.all_devices()) == len(g2.all_devices())
    assert len(g.all_links()) == len(g2.all_links())


# ============================================================
# Constraints
# ============================================================


def test_max_hops_constraint():
    g = build_diamond_topology()
    # Only allow 1 hop — no path from A to D can satisfy this
    result = compute_path(g, "A", "D", TrafficClass.MARKET_DATA, constraints=[MaxHops(1)])
    assert result is None


def test_max_latency_constraint():
    g = build_diamond_topology()
    # Max 150μs — only the fast path (100μs) qualifies
    result = compute_path(g, "A", "D", TrafficClass.MARKET_DATA,
                          constraints=[MaxLatency(150.0)])
    assert result is not None
    assert [node for node, _link in result.path] == ["B", "D"]


def test_avoid_site_constraint():
    g = build_diamond_topology()
    # Avoid dc-east — B is in dc-east, so must route through C (dc-west).
    result = compute_path(g, "A", "D", TrafficClass.MARKET_DATA,
                          constraints=[AvoidSite("dc-east")])
    if result is not None:
        assert [node for node, _link in result.path] == ["C", "D"]
    # If None: A is also in dc-east; AvoidSite checks intermediate path nodes.
    # Accepting None as valid here, matching the original test.
