"""Network Graph — models the trading firm's network topology as a weighted graph.

This is the core data structure of the SDN controller. Every routing decision
starts here: the topology graph represents all devices (nodes) and links (edges)
with their current metrics (latency, utilization, packet loss).

Why a graph? Networks ARE graphs — routers are nodes, links are edges. Modeling
them explicitly lets us run graph algorithms (Dijkstra) to compute optimal paths,
rather than relying on distributed routing protocols alone.

Design notes (ported from the original OCaml implementation):

  1. The graph is IMMUTABLE. Every "update" returns a NEW graph and leaves the
     original untouched. This is critical for concurrent access: the telemetry
     collector can update metrics while the path-computation engine reads the
     graph, without locks or races. In Python the GIL makes the ref-swap atomic;
     the immutable snapshot means a reader always sees a consistent graph.

  2. We keep two maps:
       devices:   id -> Device
       adjacency: src_id -> {dst_id -> Link}
     a simple adjacency-list representation. Links are stored in BOTH directions
     because network links are bidirectional.

  3. The weight function for Dijkstra is parameterized — the caller decides what
     "shortest" means (minimum latency, maximum bandwidth, composite cost, ...).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Optional

# ============================================================
# Types
# ============================================================


class DeviceRole(str, Enum):
    """The role a device plays in the topology. The string value is the JSON form."""

    CORE_ROUTER = "core_router"      # Cisco IOSv — backbone/WAN interconnects
    SPINE_SWITCH = "spine_switch"    # Arista vEOS — data center spine
    LEAF_SWITCH = "leaf_switch"      # Arista vEOS — data center leaf
    EDGE_ROUTER = "edge_router"      # Juniper vSRX — colo perimeter with firewall
    TRANSIT_ROUTER = "transit_router"   # External transit provider (simulated)
    EXCHANGE_ROUTER = "exchange_router"  # Exchange-side router (NYSE/CME/NASDAQ)


class LinkState(str, Enum):
    """Current operational state of a link. The string value is the JSON form."""

    UP = "up"              # Link is operational
    DOWN = "down"          # Link is down (failure or admin shutdown)
    DEGRADED = "degraded"  # Link is up but experiencing issues


@dataclass(frozen=True)
class Device:
    """A network device (node in the graph)."""

    id: str           # Unique identifier, e.g. "dc-east-core-rtr-01"
    name: str         # Human-readable name
    role: DeviceRole  # What role this device plays
    site: str         # Which site it belongs to
    loopback: str     # Loopback IP address (used for BGP peering)
    vendor: str       # "cisco", "arista", or "juniper"
    asn: int          # BGP AS number


@dataclass(frozen=True)
class LinkMetrics:
    """Real-time metrics for a link, updated by the telemetry collector."""

    latency_us: float    # One-way latency in microseconds
    jitter_us: float     # Jitter (latency variance) in microseconds
    utilization: float   # Link utilization as a fraction [0.0, 1.0]
    packet_loss: float   # Packet loss rate as a fraction [0.0, 1.0]
    last_updated: float  # Unix timestamp of last metric update


@dataclass(frozen=True)
class Link:
    """A network link (edge in the graph)."""

    id: str               # Unique link identifier
    src_interface: str    # Source interface name, e.g. "GigabitEthernet0/1"
    dst_interface: str    # Destination interface name
    bandwidth_mbps: int   # Link bandwidth in Mbps
    state: LinkState      # Current operational state
    metrics: LinkMetrics  # Current real-time metrics
    ospf_cost: int        # OSPF cost assigned to this link


# A path is an ordered list of (device_id, link) pairs from source to
# destination (the source itself is not included). A weight function maps a
# link to a float cost.
Path = list[tuple[str, Link]]
WeightFn = Callable[[Link], float]


# ============================================================
# Graph
# ============================================================


class NetworkGraph:
    """An immutable weighted graph of devices and links.

    Construct with :meth:`empty` and use the functional-update methods
    (``add_device``, ``add_link``, ``update_metrics``, ``update_link_state``),
    each of which returns a NEW graph and leaves ``self`` unchanged.
    """

    __slots__ = ("_devices", "_adjacency")

    def __init__(
        self,
        devices: Optional[dict[str, Device]] = None,
        adjacency: Optional[dict[str, dict[str, Link]]] = None,
    ) -> None:
        # These dicts are treated as immutable; functional updates copy-on-write.
        self._devices: dict[str, Device] = devices if devices is not None else {}
        self._adjacency: dict[str, dict[str, Link]] = (
            adjacency if adjacency is not None else {}
        )

    # ----- Construction -----------------------------------------------------

    @staticmethod
    def empty() -> "NetworkGraph":
        """Create an empty network graph."""
        return NetworkGraph({}, {})

    def add_device(self, device: Device) -> "NetworkGraph":
        """Add a device. Returns the updated graph.

        Raises ``ValueError`` if a device with the same ID already exists.
        """
        if device.id in self._devices:
            raise ValueError(f"Device {device.id} already exists")
        new_devices = dict(self._devices)
        new_devices[device.id] = device
        new_adjacency = dict(self._adjacency)
        new_adjacency[device.id] = {}
        return NetworkGraph(new_devices, new_adjacency)

    def add_link(self, src: str, dst: str, link: Link) -> "NetworkGraph":
        """Add a link between two devices. Both devices must already exist.

        Raises ``KeyError`` if either device ID is unknown. The link is stored
        in both directions because network links are bidirectional.
        """
        if src not in self._devices:
            raise KeyError(src)
        if dst not in self._devices:
            raise KeyError(dst)
        new_adjacency = dict(self._adjacency)
        src_adj = dict(new_adjacency[src])
        src_adj[dst] = link
        new_adjacency[src] = src_adj
        dst_adj = dict(new_adjacency[dst])
        dst_adj[src] = link
        new_adjacency[dst] = dst_adj
        return NetworkGraph(dict(self._devices), new_adjacency)

    # ----- Queries ----------------------------------------------------------

    def find_device(self, device_id: str) -> Optional[Device]:
        """Look up a device by ID. Returns ``None`` if not found."""
        return self._devices.get(device_id)

    def find_link(self, src: str, dst: str) -> Optional[Link]:
        """Look up a link between two devices. Returns ``None`` if none exists."""
        adj = self._adjacency.get(src)
        if adj is None:
            return None
        return adj.get(dst)

    def all_devices(self) -> list[Device]:
        """All devices in the graph, ordered by device id (like the OCaml Map)."""
        return [self._devices[k] for k in sorted(self._devices)]

    def all_links(self) -> list[tuple[str, str, Link]]:
        """All links as (src, dst, link).

        Each undirected link is reported once (the pair with ``src < dst``) so we
        don't double-count the bidirectional storage. Ordering matches the
        original OCaml ``all_links`` (ascending fold, prepended → reversed).
        """
        acc: list[tuple[str, str, Link]] = []
        for src in sorted(self._adjacency):
            adj = self._adjacency[src]
            for dst in sorted(adj):
                if src < dst:
                    acc.append((src, dst, adj[dst]))
        acc.reverse()
        return acc

    def neighbors(self, device_id: str) -> list[tuple[str, Link]]:
        """Neighbors of a device, reachable via an Up or Degraded link.

        Down links are effectively non-existent for routing.
        """
        adj = self._adjacency.get(device_id)
        if adj is None:
            return []
        return [
            (dst, link)
            for dst, link in sorted(adj.items())
            if link.state in (LinkState.UP, LinkState.DEGRADED)
        ]

    def devices_at_site(self, site: str) -> list[Device]:
        """All devices at a specific site."""
        return [d for d in self.all_devices() if d.site == site]

    # ----- Metric / state updates (functional, return new graphs) -----------

    def _update_link(
        self, src: str, dst: str, transform: Callable[[Link], Link]
    ) -> "NetworkGraph":
        """Apply ``transform`` to the link in BOTH directions, returning a new graph."""
        new_adjacency = dict(self._adjacency)
        for a, b in ((src, dst), (dst, src)):
            adj = new_adjacency.get(a)
            if adj is not None and b in adj:
                inner = dict(adj)
                inner[b] = transform(inner[b])
                new_adjacency[a] = inner
        return NetworkGraph(dict(self._devices), new_adjacency)

    def update_metrics(
        self, src: str, dst: str, metrics: LinkMetrics
    ) -> "NetworkGraph":
        """Update the metrics for a specific link (used by the telemetry collector)."""
        return self._update_link(src, dst, lambda link: replace(link, metrics=metrics))

    def update_link_state(
        self, src: str, dst: str, new_state: LinkState
    ) -> "NetworkGraph":
        """Update the state of a link (e.g. when the chaos framework kills a link)."""
        return self._update_link(src, dst, lambda link: replace(link, state=new_state))

    # ----- Path computation (Dijkstra) --------------------------------------

    def shortest_path(
        self, src: str, dst: str, weight: WeightFn
    ) -> Optional[tuple[Path, float]]:
        """Shortest path between two devices using Dijkstra's algorithm.

        The ``weight`` function determines what "shortest" means. Returns
        ``None`` if no path exists (network partition); otherwise
        ``(path, total_weight)`` where ``path`` is the ordered list of
        (device_id, link) pairs from source to destination.
        """
        # prev[node] = (prev_node, link_used_to_reach_node)
        prev: dict[str, tuple[str, Link]] = {}
        dist: dict[str, float] = {src: 0.0}
        visited: set[str] = set()
        # Heap entries are (distance, node). Lazy deletion: stale entries are
        # skipped when popped if the node was already visited.
        pq: list[tuple[float, str]] = [(0.0, src)]

        while pq:
            current_dist, current = heapq.heappop(pq)
            if current == dst:
                return self._reconstruct(prev, dst), current_dist
            if current in visited:
                continue
            visited.add(current)
            for neighbor, link in self.neighbors(current):
                new_dist = current_dist + weight(link)
                if new_dist < dist.get(neighbor, float("inf")):
                    dist[neighbor] = new_dist
                    prev[neighbor] = (current, link)
                    heapq.heappush(pq, (new_dist, neighbor))
        return None  # No path exists — network partition

    def all_shortest_paths(
        self, src: str, weight: WeightFn
    ) -> list[tuple[str, Path, float]]:
        """Shortest paths from ``src`` to every reachable device (a routing table)."""
        prev: dict[str, tuple[str, Link]] = {}
        dist: dict[str, float] = {src: 0.0}
        visited: set[str] = set()
        pq: list[tuple[float, str]] = [(0.0, src)]
        results: list[tuple[str, Path, float]] = []

        while pq:
            current_dist, current = heapq.heappop(pq)
            if current in visited:
                continue
            visited.add(current)
            if current != src:
                results.append((current, self._reconstruct(prev, current), current_dist))
            for neighbor, link in self.neighbors(current):
                new_dist = current_dist + weight(link)
                if new_dist < dist.get(neighbor, float("inf")):
                    dist[neighbor] = new_dist
                    prev[neighbor] = (current, link)
                    heapq.heappush(pq, (new_dist, neighbor))
        return results

    @staticmethod
    def _reconstruct(prev: dict[str, tuple[str, Link]], node: str) -> Path:
        """Walk ``prev`` back from ``node`` to the source, building the forward path."""
        path: Path = []
        while node in prev:
            prev_node, link = prev[node]
            path.append((node, link))
            node = prev_node
        path.reverse()
        return path

    # ----- Serialization ----------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize the graph to a JSON-ready dict (for the REST API / dashboard)."""
        return {
            "devices": [device_to_dict(d) for d in self.all_devices()],
            "links": [
                {"src": src, "dst": dst, "link": link_to_dict(link)}
                for src, dst, link in self.all_links()
            ],
        }

    @staticmethod
    def from_dict(data: dict) -> "NetworkGraph":
        """Deserialize a graph from a dict (inverse of :meth:`to_dict`).

        Raises ``ValueError`` if the structure is malformed.
        """
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object for graph")
        devices_json = data.get("devices")
        links_json = data.get("links")
        if not isinstance(devices_json, list):
            raise ValueError("Expected array for devices")
        if not isinstance(links_json, list):
            raise ValueError("Expected array for links")

        graph = NetworkGraph.empty()
        for d in devices_json:
            graph = graph.add_device(device_from_dict(d))
        for entry in links_json:
            if not isinstance(entry, dict):
                raise ValueError("Expected JSON object for link entry")
            src = entry.get("src")
            dst = entry.get("dst")
            if not isinstance(src, str) or not isinstance(dst, str):
                raise ValueError("Link entry missing src/dst")
            graph = graph.add_link(src, dst, link_from_dict(entry.get("link")))
        return graph


# ============================================================
# JSON helpers (module-level, mirroring the OCaml *_to_yojson / *_of_yojson)
# ============================================================


def device_to_dict(d: Device) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "role": d.role.value,
        "site": d.site,
        "loopback": d.loopback,
        "vendor": d.vendor,
        "asn": d.asn,
    }


def metrics_to_dict(m: LinkMetrics) -> dict:
    return {
        "latency_us": m.latency_us,
        "jitter_us": m.jitter_us,
        "utilization": m.utilization,
        "packet_loss": m.packet_loss,
        "last_updated": m.last_updated,
    }


def link_to_dict(link: Link) -> dict:
    return {
        "id": link.id,
        "src_interface": link.src_interface,
        "dst_interface": link.dst_interface,
        "bandwidth_mbps": link.bandwidth_mbps,
        "state": link.state.value,
        "metrics": metrics_to_dict(link.metrics),
        "ospf_cost": link.ospf_cost,
    }


def device_from_dict(data: dict) -> Device:
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object for device")
    try:
        return Device(
            id=str(data["id"]),
            name=str(data["name"]),
            role=DeviceRole(data["role"]),
            site=str(data["site"]),
            loopback=str(data["loopback"]),
            vendor=str(data["vendor"]),
            asn=int(data["asn"]),
        )
    except KeyError as exc:
        raise ValueError(f"Missing field: {exc.args[0]}") from exc
    except ValueError as exc:
        raise ValueError(f"Invalid device: {exc}") from exc


def metrics_from_dict(data: dict) -> LinkMetrics:
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object for metrics")
    try:
        return LinkMetrics(
            latency_us=float(data["latency_us"]),
            jitter_us=float(data["jitter_us"]),
            utilization=float(data["utilization"]),
            packet_loss=float(data["packet_loss"]),
            last_updated=float(data["last_updated"]),
        )
    except KeyError as exc:
        raise ValueError(f"Missing field: {exc.args[0]}") from exc


def link_from_dict(data: dict) -> Link:
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object for link")
    try:
        return Link(
            id=str(data["id"]),
            src_interface=str(data["src_interface"]),
            dst_interface=str(data["dst_interface"]),
            bandwidth_mbps=int(data["bandwidth_mbps"]),
            state=LinkState(data["state"]),
            metrics=metrics_from_dict(data["metrics"]),
            ospf_cost=int(data["ospf_cost"]),
        )
    except KeyError as exc:
        raise ValueError(f"Missing field: {exc.args[0]}") from exc
