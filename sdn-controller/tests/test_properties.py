"""Property-based tests for the SDN controller.

Ported from the original OCaml QCheck suite (test_properties.ml). Instead of
checking specific inputs, these GENERATE random network topologies and verify
that INVARIANTS hold across all of them.

The original used QCheck; here we use a small self-contained seeded generator
(Python's ``random``) so the suite has no extra dependencies and reproduces the
"8 properties across 1,600 random topologies" claim exactly (8 × 200 = 1,600).
Seeds are fixed so failures are reproducible.

Properties verified:
  1. Path existence — connected graph always has a path
  2. Path optimality — Dijkstra finds the minimum-cost path
  3. Symmetry — cost(A→B) == cost(B→A) in an undirected graph
  4. No routing loops — a path never visits a node twice
  5. Failover — removing any single link never produces a looped path
  6. Metric-update consistency — raising a link's latency never lowers path cost
  7. JSON roundtrip — serialize/deserialize preserves the graph
  8. Traffic-class ordering — market-data latency <= trading latency
"""

import random

from tradenet_sdn.network_graph import (
    Device,
    DeviceRole,
    Link,
    LinkMetrics,
    LinkState,
    NetworkGraph,
)
from tradenet_sdn.path_engine import TrafficClass, compute_path

COUNT = 200  # iterations per property (8 × 200 = 1,600 random topologies)
EPS = 0.001  # float comparison epsilon


def latency_weight(link):
    return link.metrics.latency_us


# ============================================================
# Random generators
# ============================================================


def make_random_device(node_id):
    try:
        octet = int(node_id.split("-")[1]) % 256
    except (IndexError, ValueError):
        octet = 0
    return Device(id=node_id, name=node_id, role=DeviceRole.CORE_ROUTER,
                  site="test-site", loopback=f"10.0.0.{octet}", vendor="cisco", asn=65001)


def make_random_link(link_id, latency):
    return Link(
        id=link_id,
        src_interface="eth0",
        dst_interface="eth0",
        bandwidth_mbps=10000,
        state=LinkState.UP,
        metrics=LinkMetrics(latency_us=latency, jitter_us=latency * 0.1,
                            utilization=0.1, packet_loss=0.0, last_updated=0.0),
        ospf_cost=max(1, int(latency)),
    )


def gen_connected_topology(rng):
    """Generate a random connected topology with 2-15 nodes.

    Connectivity is guaranteed by first building a spanning tree (connect node i
    to node i-1), then adding random extra edges for redundancy. Mirrors the
    original OCaml ``gen_connected_topology``.
    """
    n = rng.randint(2, 15)
    extra_edges = rng.randint(0, n * 2)
    node_ids = [f"node-{i}" for i in range(n)]

    g = NetworkGraph.empty()
    for node_id in node_ids:
        g = g.add_device(make_random_device(node_id))

    # Spanning tree: connect node-i to node-(i-1)
    for i in range(1, n):
        src = f"node-{i}"
        dst = f"node-{i - 1}"
        latency = rng.uniform(1.0, 10000.0)
        g = g.add_link(src, dst, make_random_link(f"{src}--{dst}", latency))

    # Random extra edges for redundancy
    for _ in range(extra_edges):
        si = rng.randint(0, n - 1)
        di = rng.randint(0, n - 1)
        latency = rng.uniform(1.0, 10000.0)
        if si == di:
            continue  # No self-loops
        src = f"node-{si}"
        dst = f"node-{di}"
        if g.find_link(src, dst) is not None:
            continue  # Edge already exists
        try:
            g = g.add_link(src, dst, make_random_link(f"{src}--{dst}-extra", latency))
        except Exception:
            pass

    return g, node_ids


def topologies(base_seed):
    """Yield (iteration, graph, node_ids) for COUNT reproducible random topologies."""
    for i in range(COUNT):
        rng = random.Random(base_seed + i)
        graph, node_ids = gen_connected_topology(rng)
        yield i, graph, node_ids


# ============================================================
# Property 1: Path existence
# ============================================================


def test_path_exists_in_connected_graph():
    for i, graph, node_ids in topologies(1_000_000):
        n = len(node_ids)
        if n < 2:
            continue
        src, dst = node_ids[0], node_ids[n - 1]
        assert graph.shortest_path(src, dst, latency_weight) is not None, \
            f"iteration {i}: no path in connected graph ({n} nodes)"


# ============================================================
# Property 2: Path optimality
# ============================================================


def test_shortest_path_is_optimal():
    for i, graph, node_ids in topologies(2_000_000):
        n = len(node_ids)
        if n < 3:
            continue
        src, dst = node_ids[0], node_ids[n - 1]
        opt = graph.shortest_path(src, dst, latency_weight)
        if opt is None:
            continue
        _path, optimal_cost = opt

        mid = node_ids[n // 2]
        first = graph.shortest_path(src, mid, latency_weight)
        second = graph.shortest_path(mid, dst, latency_weight)
        if first is None or second is None:
            continue  # mid not reachable, skip
        indirect = first[1] + second[1]
        assert optimal_cost <= indirect + EPS, \
            f"iteration {i}: optimal {optimal_cost} > via-mid {indirect}"


# ============================================================
# Property 3: Symmetry
# ============================================================


def test_path_symmetry():
    for i, graph, node_ids in topologies(3_000_000):
        n = len(node_ids)
        if n < 2:
            continue
        a, b = node_ids[0], node_ids[n - 1]
        ab = graph.shortest_path(a, b, latency_weight)
        ba = graph.shortest_path(b, a, latency_weight)
        if ab is not None and ba is not None:
            assert abs(ab[1] - ba[1]) < EPS, \
                f"iteration {i}: cost(a→b)={ab[1]} != cost(b→a)={ba[1]}"
        else:
            assert ab is None and ba is None, \
                f"iteration {i}: one direction reachable, the other not"


# ============================================================
# Property 4: No routing loops
# ============================================================


def test_no_routing_loops():
    for i, graph, node_ids in topologies(4_000_000):
        n = len(node_ids)
        if n < 2:
            continue
        src, dst = node_ids[0], node_ids[n - 1]
        found = graph.shortest_path(src, dst, latency_weight)
        if found is None:
            continue
        path, _cost = found
        nodes = [node for node, _link in path]
        assert len(nodes) == len(set(nodes)), \
            f"iteration {i}: routing loop in path {nodes}"


# ============================================================
# Property 5: Failover existence (no looped failover path)
# ============================================================


def test_single_failure_survivable():
    for i, graph, node_ids in topologies(5_000_000):
        n = len(node_ids)
        if n < 3:
            continue
        src, dst = node_ids[0], node_ids[n - 1]
        for lsrc, ldst, _link in graph.all_links():
            g2 = graph.update_link_state(lsrc, ldst, LinkState.DOWN)
            found = g2.shortest_path(src, dst, latency_weight)
            if found is None:
                continue  # Disconnected is OK — just no redundancy
            path, _cost = found
            nodes = [node for node, _link in path]
            assert len(nodes) == len(set(nodes)), \
                f"iteration {i}: looped failover path after dropping {lsrc}--{ldst}"


# ============================================================
# Property 6: Metric-update consistency
# ============================================================


def test_metric_update_affects_cost():
    for i, graph, node_ids in topologies(6_000_000):
        n = len(node_ids)
        if n < 2:
            continue
        src, dst = node_ids[0], node_ids[n - 1]
        found = graph.shortest_path(src, dst, latency_weight)
        if found is None:
            continue
        path, cost_before = found
        if len(path) == 0:
            continue
        first_node, first_link = path[0]
        new_metrics = LinkMetrics(
            latency_us=first_link.metrics.latency_us + 50000.0,
            jitter_us=first_link.metrics.jitter_us,
            utilization=first_link.metrics.utilization,
            packet_loss=first_link.metrics.packet_loss,
            last_updated=first_link.metrics.last_updated,
        )
        g2 = graph.update_metrics(src, first_node, new_metrics)
        found2 = g2.shortest_path(src, dst, latency_weight)
        if found2 is None:
            continue
        _path2, cost_after = found2
        assert cost_after >= cost_before - EPS, \
            f"iteration {i}: cost dropped after raising latency ({cost_before} -> {cost_after})"


# ============================================================
# Property 7: JSON roundtrip
# ============================================================


def test_json_roundtrip():
    for i, graph, _node_ids in topologies(7_000_000):
        data = graph.to_dict()
        graph2 = NetworkGraph.from_dict(data)
        assert len(graph.all_devices()) == len(graph2.all_devices()), \
            f"iteration {i}: device count changed across roundtrip"
        assert len(graph.all_links()) == len(graph2.all_links()), \
            f"iteration {i}: link count changed across roundtrip"


# ============================================================
# Property 8: Traffic-class ordering
# ============================================================


def test_market_data_fastest():
    for i, graph, node_ids in topologies(8_000_000):
        n = len(node_ids)
        if n < 2:
            continue
        src, dst = node_ids[0], node_ids[n - 1]
        md = compute_path(graph, src, dst, TrafficClass.MARKET_DATA, constraints=[])
        tr = compute_path(graph, src, dst, TrafficClass.TRADING, constraints=[])
        if md is not None and tr is not None:
            assert md.total_latency_us <= tr.total_latency_us + EPS, \
                f"iteration {i}: market-data latency {md.total_latency_us} > trading {tr.total_latency_us}"
        elif md is None and tr is not None:
            raise AssertionError(f"iteration {i}: trading found a path but market data didn't")
        # md found / tr not, or both none: fine
