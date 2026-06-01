"""REST API Server.

Exposes the SDN controller's state and path computation over HTTP, using Flask.

The API serves two consumers:
  1. The dashboard (real-time network visualization)
  2. External tools/scripts (chaos framework, benchmarks)

JSON is emitted with :func:`json.dumps` (compact, key order preserved) rather
than Flask's ``jsonify`` so the wire format matches the original OCaml/Yojson
controller exactly — the chaos and benchmark scripts depend on these shapes.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from flask import Flask, Response, request

from . import network_graph
from .network_graph import NetworkGraph
from .path_engine import TrafficClass, compute_path


# ============================================================
# Controller state
#
# The graph is immutable; we swap the reference atomically when telemetry
# updates arrive. A reader always sees a complete, consistent snapshot.
# ============================================================


class ControllerState:
    def __init__(self) -> None:
        self.graph: NetworkGraph = NetworkGraph.empty()
        self.last_update: float = 0.0


state = ControllerState()


def init(graph: NetworkGraph) -> None:
    """Initialize the controller with a network graph."""
    state.graph = graph
    state.last_update = time.time()


def update_graph(graph: NetworkGraph) -> None:
    """Replace the graph (called by the telemetry collector / chaos framework)."""
    state.graph = graph
    state.last_update = time.time()


# ============================================================
# JSON helper — compact, key-order-preserving, no trailing newline
# ============================================================


def _json(payload, status: int = 200) -> Response:
    body = json.dumps(payload, separators=(",", ":"))
    return Response(body, status=status, mimetype="application/json")


# ============================================================
# Flask app + routes
# ============================================================

app = Flask(__name__)


@app.after_request
def _cors(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.get("/api/health")
def handle_health() -> Response:
    """Health check endpoint."""
    return _json({
        "status": "healthy",
        "last_update": state.last_update,
        "device_count": len(state.graph.all_devices()),
        "link_count": len(state.graph.all_links()),
    })


@app.get("/api/topology")
def handle_topology() -> Response:
    """Return the full network graph as JSON (used by the dashboard)."""
    return _json(state.graph.to_dict())


@app.get("/api/devices")
def handle_devices() -> Response:
    """List all network devices."""
    return _json([network_graph.device_to_dict(d) for d in state.graph.all_devices()])


@app.get("/api/devices/<device_id>")
def handle_device(device_id: str) -> Response:
    """Get a specific device by ID."""
    device = state.graph.find_device(device_id)
    if device is None:
        return _json({"error": "Device not found"}, status=404)
    return _json(network_graph.device_to_dict(device))


@app.get("/api/links")
def handle_links() -> Response:
    """List all network links with current metrics."""
    return _json([
        {"src": src, "dst": dst, "link": network_graph.link_to_dict(link)}
        for src, dst, link in state.graph.all_links()
    ])


@app.post("/api/path")
def handle_path() -> Response:
    """Compute the optimal path between two devices.

    Body: {"src": "...", "dst": "...", "traffic_class": "market_data"}
    """
    body = _parse_json_body()
    if body is None:
        return _json({"error": "Invalid request body"}, status=400)

    src = body.get("src")
    dst = body.get("dst")
    if not isinstance(src, str) or not isinstance(dst, str):
        return _json({"error": "Invalid request body"}, status=400)

    traffic_class = _parse_traffic_class(body.get("traffic_class"))

    result = compute_path(state.graph, src, dst, traffic_class, constraints=[])
    if result is None:
        return _json({"error": "No path found"}, status=404)

    return _json({
        "path": [
            {"node": node, "link": network_graph.link_to_dict(link)}
            for node, link in result.path
        ],
        "total_latency_us": result.total_latency_us,
        "total_cost": result.total_cost,
        "hop_count": result.hop_count,
        "bottleneck_bandwidth_mbps": result.bottleneck_bandwidth,
    })


@app.post("/api/link/state")
def handle_link_state() -> Response:
    """Update a link's state (used by the chaos framework).

    Body: {"src": "...", "dst": "...", "state": "down"}
    """
    body = _parse_json_body()
    if body is None:
        return _json({"error": "Invalid request body"}, status=400)

    src = body.get("src")
    dst = body.get("dst")
    state_str = body.get("state")
    if not isinstance(src, str) or not isinstance(dst, str) or not isinstance(state_str, str):
        return _json({"error": "Invalid request body"}, status=400)

    link_state = _parse_link_state(state_str)
    update_graph(state.graph.update_link_state(src, dst, link_state))
    return _json({"status": "ok"})


# ============================================================
# Parsing helpers
# ============================================================


def _parse_json_body() -> Optional[dict]:
    """Parse the request body as a JSON object, or return ``None`` if invalid."""
    try:
        body = request.get_json(force=True, silent=True)
    except Exception:
        return None
    return body if isinstance(body, dict) else None


def _parse_traffic_class(value) -> TrafficClass:
    """Parse a traffic-class string, defaulting to market data (like the OCaml)."""
    try:
        return TrafficClass(value)
    except ValueError:
        return TrafficClass.MARKET_DATA


def _parse_link_state(value: str) -> network_graph.LinkState:
    """Parse a link-state string, defaulting to ``up`` (like the OCaml)."""
    try:
        return network_graph.LinkState(value)
    except ValueError:
        return network_graph.LinkState.UP


def start(port: int = 9090) -> None:
    """Start the API server on the given port."""
    # Quiet Werkzeug's per-request access log: it adds per-request overhead and
    # noise that skews the micro-benchmarks. Warnings and errors still surface.
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    # threaded=True so sequential clients (chaos/benchmark) aren't blocked;
    # use_reloader=False because we start this programmatically from __main__.
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
