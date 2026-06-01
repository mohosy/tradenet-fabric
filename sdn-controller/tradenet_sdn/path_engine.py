"""Path Computation Engine.

Sits between the raw graph and the policy engine. It provides high-level routing
decisions by combining graph algorithms with trading-network-specific concerns.

Design notes (ported from the original OCaml implementation):

  1. Path computation is separated from the graph module: the graph is a general
     data structure, but path computation is domain-specific. The graph doesn't
     know about "trading traffic" vs "management traffic" — this module does.

  2. Different traffic classes have different optimization objectives, expressed
     as different weight functions:
       - Market data needs minimum latency
       - Trading needs minimum latency + low jitter
       - Bulk transfers need maximum available bandwidth
       - Management traffic just needs reliability

  3. Constraints (avoid link/site, max latency/hops) are supported because real
     traffic engineering isn't just "shortest path" — it's "shortest path that
     also satisfies these business requirements." Per-link constraints are
     enforced by inflating a violating link's weight to infinity; whole-path
     constraints (max latency/hops, avoid site) are checked after computation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union

from .network_graph import Link, LinkState, NetworkGraph, Path, WeightFn


# ============================================================
# Traffic classes
# ============================================================


class TrafficClass(str, Enum):
    """Determines how path computation is weighted. The string value is the API form."""

    MARKET_DATA = "market_data"    # Minimum latency — every microsecond matters
    TRADING = "trading"            # Minimum latency + low jitter
    BULK_TRANSFER = "bulk_transfer"  # Maximum available bandwidth
    MANAGEMENT = "management"      # Maximum reliability (avoid degraded/lossy links)


# ============================================================
# Constraints
# ============================================================


@dataclass(frozen=True)
class AvoidLink:
    """Don't use the link between these two devices."""

    src: str
    dst: str


@dataclass(frozen=True)
class AvoidSite:
    """Don't route through this site."""

    site: str


@dataclass(frozen=True)
class PreferSite:
    """Prefer paths through this site (a bonus, never a hard violation)."""

    site: str


@dataclass(frozen=True)
class MaxLatency:
    """Total path latency must be under this (microseconds)."""

    max_us: float


@dataclass(frozen=True)
class MaxHops:
    """Maximum number of hops."""

    max_hops: int


PathConstraint = Union[AvoidLink, AvoidSite, PreferSite, MaxLatency, MaxHops]


# ============================================================
# Result
# ============================================================


@dataclass(frozen=True)
class PathResult:
    """Result of a path computation."""

    path: Path                  # Ordered list of (device_id, link) pairs
    total_latency_us: float     # Sum of link latencies along the path
    total_cost: float           # Computed cost (depends on weight function used)
    hop_count: int              # Number of hops
    bottleneck_bandwidth: int   # Minimum-bandwidth link on the path (Mbps)


# ============================================================
# Weight functions
#
# These define what "optimal" means for each traffic class. Traditional routing
# (OSPF, BGP) uses static metrics; our SDN controller uses LIVE metrics (actual
# latency, actual utilization), so the "best" path changes with conditions.
# ============================================================


def market_data_weight(link: Link) -> float:
    """Market data: pure latency optimization. Every microsecond is money."""
    if link.state == LinkState.DOWN:
        return math.inf  # Can't use down links
    if link.state == LinkState.DEGRADED:
        return link.metrics.latency_us * 2.0  # Heavy penalty
    return link.metrics.latency_us


def trading_weight(link: Link) -> float:
    """Trading: latency + jitter penalty. Predictable latency means predictable fills."""
    if link.state == LinkState.DOWN:
        return math.inf
    base = link.metrics.latency_us + link.metrics.jitter_us * 3.0
    if link.state == LinkState.DEGRADED:
        return base * 2.0
    return base


def bulk_transfer_weight(link: Link) -> float:
    """Bulk transfers: prefer the fattest, least-utilized pipes."""
    if link.state == LinkState.DOWN:
        return math.inf
    if link.state == LinkState.DEGRADED:
        return math.inf  # Don't put bulk traffic on degraded links
    available = link.bandwidth_mbps * (1.0 - link.metrics.utilization)
    if available <= 0.0:
        return math.inf
    return 1000.0 / available  # Inverse: more available BW = lower cost


def management_weight(link: Link) -> float:
    """Management: prefer reliable links. We care about not dropping packets."""
    if link.state == LinkState.DOWN:
        return math.inf
    if link.state == LinkState.DEGRADED:
        return 1000.0  # Heavy penalty but still usable
    return 1.0 + link.metrics.packet_loss * 100.0


_WEIGHT_FOR_CLASS = {
    TrafficClass.MARKET_DATA: market_data_weight,
    TrafficClass.TRADING: trading_weight,
    TrafficClass.BULK_TRANSFER: bulk_transfer_weight,
    TrafficClass.MANAGEMENT: management_weight,
}


def weight_for_class(traffic_class: TrafficClass) -> WeightFn:
    """Select the appropriate weight function for a traffic class."""
    return _WEIGHT_FOR_CLASS[traffic_class]


# ============================================================
# Constrained path computation
# ============================================================


def apply_constraints(
    constraints: list[PathConstraint], base_weight: WeightFn
) -> WeightFn:
    """Wrap ``base_weight`` so links violating a per-link constraint cost infinity.

    Only :class:`AvoidLink` is enforceable per-link. Site/latency/hop constraints
    are checked after the path is computed (see :func:`compute_path`).
    """

    def weighted(link: Link) -> float:
        base = base_weight(link)
        if math.isinf(base):
            return base  # Already unusable
        for c in constraints:
            if isinstance(c, AvoidLink):
                if link.id in (f"{c.src}--{c.dst}", f"{c.dst}--{c.src}"):
                    return math.inf
        return base

    return weighted


def _bottleneck_bandwidth(path: Path) -> int:
    """Minimum bandwidth along the path; 0 for an empty path."""
    return min((link.bandwidth_mbps for _node, link in path), default=0)


def _total_latency(path: Path) -> float:
    return sum(link.metrics.latency_us for _node, link in path)


def compute_path(
    graph: NetworkGraph,
    src: str,
    dst: str,
    traffic_class: TrafficClass,
    constraints: Optional[list[PathConstraint]] = None,
) -> Optional[PathResult]:
    """Compute the optimal path for a traffic class, subject to constraints.

    Returns ``None`` if no path exists or the best path violates a whole-path
    constraint.
    """
    constraints = constraints or []
    base_weight = weight_for_class(traffic_class)
    weight = apply_constraints(constraints, base_weight)

    found = graph.shortest_path(src, dst, weight)
    if found is None:
        return None  # No path exists

    path, total_cost = found
    result = PathResult(
        path=path,
        total_latency_us=_total_latency(path),
        total_cost=total_cost,
        hop_count=len(path),
        bottleneck_bandwidth=_bottleneck_bandwidth(path),
    )

    # Check whole-path constraints that can't be expressed per-link.
    for c in constraints:
        if isinstance(c, MaxLatency):
            if result.total_latency_us > c.max_us:
                return None
        elif isinstance(c, MaxHops):
            if result.hop_count > c.max_hops:
                return None
        elif isinstance(c, AvoidSite):
            for node_id, _link in path:
                dev = graph.find_device(node_id)
                if dev is not None and dev.site == c.site:
                    return None
    return result


def compute_routing_table(
    graph: NetworkGraph, src: str, traffic_class: TrafficClass
) -> list[tuple[str, PathResult]]:
    """Compute paths from ``src`` to ALL destinations: a routing table."""
    weight = weight_for_class(traffic_class)
    table: list[tuple[str, PathResult]] = []
    for dst, path, total_cost in graph.all_shortest_paths(src, weight):
        table.append(
            (
                dst,
                PathResult(
                    path=path,
                    total_latency_us=_total_latency(path),
                    total_cost=total_cost,
                    hop_count=len(path),
                    bottleneck_bandwidth=_bottleneck_bandwidth(path),
                ),
            )
        )
    return table
