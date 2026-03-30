// Simulated topology data matching our real SDN controller output.
// In production, this fetches from the OCaml REST API at localhost:9090.

export interface Device {
  id: string;
  name: string;
  role: string;
  site: string;
  loopback: string;
  vendor: string;
  asn: number;
}

export interface LinkMetrics {
  latency_us: number;
  jitter_us: number;
  utilization: number;
  packet_loss: number;
}

export interface Link {
  src: string;
  dst: string;
  bandwidth_mbps: number;
  state: "up" | "down" | "degraded";
  metrics: LinkMetrics;
  ospf_cost: number;
}

export interface ChaosScenario {
  name: string;
  status: "passed" | "failed" | "running";
  failover_ms: number;
  target_ms: number;
  timestamp: string;
}

export interface BenchmarkResult {
  name: string;
  mean: number;
  p99: number;
  target: number;
  unit: string;
  passed: boolean;
}

export const devices: Device[] = [
  { id: "dc-east-core-01", name: "DC-East Core 01", role: "core_router", site: "dc-east", loopback: "10.1.0.1", vendor: "cisco", asn: 65001 },
  { id: "dc-east-core-02", name: "DC-East Core 02", role: "core_router", site: "dc-east", loopback: "10.1.0.2", vendor: "cisco", asn: 65001 },
  { id: "dc-east-spine-01", name: "DC-East Spine 01", role: "spine_switch", site: "dc-east", loopback: "10.1.0.11", vendor: "arista", asn: 65001 },
  { id: "dc-east-spine-02", name: "DC-East Spine 02", role: "spine_switch", site: "dc-east", loopback: "10.1.0.12", vendor: "arista", asn: 65001 },
  { id: "dc-west-core-01", name: "DC-West Core 01", role: "core_router", site: "dc-west", loopback: "10.2.0.1", vendor: "cisco", asn: 65001 },
  { id: "dc-west-spine-01", name: "DC-West Spine 01", role: "spine_switch", site: "dc-west", loopback: "10.2.0.11", vendor: "arista", asn: 65001 },
  { id: "colo-nyse-edge-01", name: "NYSE Edge 01", role: "edge_router", site: "colo-nyse", loopback: "10.4.0.1", vendor: "juniper", asn: 65001 },
  { id: "colo-nyse-edge-02", name: "NYSE Edge 02", role: "edge_router", site: "colo-nyse", loopback: "10.4.0.2", vendor: "juniper", asn: 65001 },
  { id: "nyse-exchange", name: "NYSE Exchange", role: "exchange_router", site: "nyse", loopback: "198.51.100.1", vendor: "cisco", asn: 11111 },
  { id: "colo-cme-edge-01", name: "CME Edge 01", role: "edge_router", site: "colo-cme", loopback: "10.5.0.1", vendor: "juniper", asn: 65001 },
  { id: "colo-nasdaq-edge-01", name: "NASDAQ Edge 01", role: "edge_router", site: "colo-nasdaq", loopback: "10.6.0.1", vendor: "juniper", asn: 65001 },
  { id: "dr-site-core-01", name: "DR-Site Core 01", role: "core_router", site: "dr-site", loopback: "10.3.0.1", vendor: "cisco", asn: 65001 },
];

export const links: Link[] = [
  { src: "dc-east-core-01", dst: "dc-east-core-02", bandwidth_mbps: 10000, state: "up", metrics: { latency_us: 50, jitter_us: 2, utilization: 0.15, packet_loss: 0 }, ospf_cost: 5 },
  { src: "dc-east-core-01", dst: "dc-east-spine-01", bandwidth_mbps: 10000, state: "up", metrics: { latency_us: 30, jitter_us: 1, utilization: 0.22, packet_loss: 0 }, ospf_cost: 3 },
  { src: "dc-east-core-02", dst: "dc-east-spine-02", bandwidth_mbps: 10000, state: "up", metrics: { latency_us: 30, jitter_us: 1, utilization: 0.18, packet_loss: 0 }, ospf_cost: 3 },
  { src: "dc-east-core-01", dst: "dc-west-core-01", bandwidth_mbps: 10000, state: "up", metrics: { latency_us: 5000, jitter_us: 50, utilization: 0.45, packet_loss: 0 }, ospf_cost: 100 },
  { src: "dc-west-core-01", dst: "dc-west-spine-01", bandwidth_mbps: 10000, state: "up", metrics: { latency_us: 30, jitter_us: 1, utilization: 0.12, packet_loss: 0 }, ospf_cost: 3 },
  { src: "dc-east-core-01", dst: "colo-nyse-edge-01", bandwidth_mbps: 10000, state: "up", metrics: { latency_us: 200, jitter_us: 5, utilization: 0.60, packet_loss: 0 }, ospf_cost: 20 },
  { src: "dc-east-core-02", dst: "colo-nyse-edge-02", bandwidth_mbps: 10000, state: "up", metrics: { latency_us: 200, jitter_us: 5, utilization: 0.55, packet_loss: 0 }, ospf_cost: 20 },
  { src: "colo-nyse-edge-01", dst: "colo-nyse-edge-02", bandwidth_mbps: 10000, state: "up", metrics: { latency_us: 10, jitter_us: 0.5, utilization: 0.08, packet_loss: 0 }, ospf_cost: 1 },
  { src: "colo-nyse-edge-01", dst: "nyse-exchange", bandwidth_mbps: 10000, state: "up", metrics: { latency_us: 5, jitter_us: 0.2, utilization: 0.75, packet_loss: 0 }, ospf_cost: 1 },
  { src: "dc-east-core-01", dst: "colo-cme-edge-01", bandwidth_mbps: 10000, state: "up", metrics: { latency_us: 350, jitter_us: 8, utilization: 0.42, packet_loss: 0 }, ospf_cost: 35 },
  { src: "dc-east-core-01", dst: "colo-nasdaq-edge-01", bandwidth_mbps: 10000, state: "up", metrics: { latency_us: 180, jitter_us: 4, utilization: 0.38, packet_loss: 0 }, ospf_cost: 18 },
  { src: "dc-east-core-01", dst: "dr-site-core-01", bandwidth_mbps: 10000, state: "up", metrics: { latency_us: 8000, jitter_us: 80, utilization: 0.10, packet_loss: 0 }, ospf_cost: 150 },
];

export const chaosResults: ChaosScenario[] = [
  { name: "Link Failure — DC-East to NYSE", status: "passed", failover_ms: 2.5, target_ms: 100, timestamp: "2026-03-30T09:55:40Z" },
  { name: "Link Failure — Inter-DC WAN", status: "passed", failover_ms: 2.0, target_ms: 500, timestamp: "2026-03-30T09:55:40Z" },
  { name: "BGP Hijack — NYSE Prefix", status: "passed", failover_ms: 1.4, target_ms: 5000, timestamp: "2026-03-30T09:55:40Z" },
];

export const benchmarks: BenchmarkResult[] = [
  { name: "Path Computation", mean: 0.86, p99: 1.52, target: 50, unit: "ms", passed: true },
  { name: "Failover Time", mean: 1.66, p99: 1.98, target: 100, unit: "ms", passed: true },
  { name: "API Health Check", mean: 0.79, p99: 0.94, target: 10, unit: "ms", passed: true },
  { name: "Topology Query", mean: 0.83, p99: 1.14, target: 20, unit: "ms", passed: true },
];

export const optimalPath = {
  src: "dc-east-core-01",
  dst: "nyse-exchange",
  hops: ["dc-east-core-01", "colo-nyse-edge-01", "nyse-exchange"],
  total_latency_us: 205,
  hop_count: 2,
};

export const sitePositions: Record<string, { x: number; y: number; label: string; color: string }> = {
  "dc-east": { x: 200, y: 120, label: "DC-East (Primary)", color: "#3b82f6" },
  "dc-west": { x: 200, y: 380, label: "DC-West (Secondary)", color: "#8b5cf6" },
  "dr-site": { x: 500, y: 380, label: "DR-Site", color: "#6b7280" },
  "colo-nyse": { x: 500, y: 60, label: "Colo-NYSE", color: "#22c55e" },
  "colo-cme": { x: 700, y: 180, label: "Colo-CME", color: "#f59e0b" },
  "colo-nasdaq": { x: 700, y: 320, label: "Colo-NASDAQ", color: "#06b6d4" },
  "nyse": { x: 700, y: 60, label: "NYSE Exchange", color: "#ef4444" },
};
