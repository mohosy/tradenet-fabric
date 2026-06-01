"use client";

import { useState, useEffect } from "react";
import {
  devices,
  links,
  chaosResults,
  benchmarks,
  optimalPath,
  sitePositions,
} from "./data";
import type { Link, Device } from "./data";

// ============================================================
// Utility Components
// ============================================================

function StatusDot({ status }: { status: "up" | "down" | "degraded" | "healthy" }) {
  const colors = {
    up: "bg-green-500",
    healthy: "bg-green-500",
    down: "bg-red-500",
    degraded: "bg-amber-500",
  };
  return (
    <span className="relative flex h-2.5 w-2.5">
      <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-40 ${colors[status]}`} />
      <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${colors[status]}`} />
    </span>
  );
}

function MetricCard({
  label,
  value,
  unit,
  subtitle,
  trend,
  color = "blue",
}: {
  label: string;
  value: string;
  unit: string;
  subtitle?: string;
  trend?: "up" | "down" | "stable";
  color?: "blue" | "green" | "amber" | "red" | "purple" | "cyan";
}) {
  const borderColors = {
    blue: "border-blue-500/30 hover:border-blue-500/60",
    green: "border-green-500/30 hover:border-green-500/60",
    amber: "border-amber-500/30 hover:border-amber-500/60",
    red: "border-red-500/30 hover:border-red-500/60",
    purple: "border-purple-500/30 hover:border-purple-500/60",
    cyan: "border-cyan-500/30 hover:border-cyan-500/60",
  };
  const accentColors = {
    blue: "text-blue-400",
    green: "text-green-400",
    amber: "text-amber-400",
    red: "text-red-400",
    purple: "text-purple-400",
    cyan: "text-cyan-400",
  };

  return (
    <div
      className={`rounded-xl border ${borderColors[color]} bg-[var(--bg-card)] p-5 transition-all duration-200 hover:bg-[var(--bg-card-hover)]`}
    >
      <p className="text-xs font-medium tracking-wider uppercase text-[var(--text-muted)] mb-2">
        {label}
      </p>
      <div className="flex items-baseline gap-1.5">
        <span className={`text-3xl font-semibold tabular-nums ${accentColors[color]}`}>
          {value}
        </span>
        <span className="text-sm text-[var(--text-muted)]">{unit}</span>
      </div>
      {subtitle && (
        <p className="mt-1.5 text-xs text-[var(--text-secondary)]">{subtitle}</p>
      )}
    </div>
  );
}

// ============================================================
// Topology Visualization (SVG)
// ============================================================

function TopologyMap({
  activeLink,
  onLinkClick,
}: {
  activeLink: string | null;
  onLinkClick: (id: string) => void;
}) {
  const devicePositions: Record<string, { x: number; y: number }> = {};
  const siteCounts: Record<string, number> = {};

  devices.forEach((d) => {
    const site = sitePositions[d.site];
    if (!site) return;
    if (!siteCounts[d.site]) siteCounts[d.site] = 0;
    const offset = siteCounts[d.site] * 28;
    devicePositions[d.id] = { x: site.x, y: site.y + offset };
    siteCounts[d.site]++;
  });

  const isOnPath = (id: string) => optimalPath.hops.includes(id);

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-4 overflow-hidden">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          Network Topology
        </h3>
        <div className="flex items-center gap-4 text-xs text-[var(--text-muted)]">
          <span className="flex items-center gap-1.5">
            <span className="w-6 h-0.5 bg-green-500 rounded" /> Optimal Path
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-6 h-0.5 bg-[var(--border-accent)] rounded" /> Link
          </span>
        </div>
      </div>
      <svg viewBox="0 0 820 460" className="w-full h-auto">
        {/* Site backgrounds */}
        {Object.entries(sitePositions).map(([site, pos]) => {
          const siteDevices = devices.filter((d) => d.site === site);
          if (siteDevices.length === 0) return null;
          const height = Math.max(60, siteDevices.length * 28 + 24);
          return (
            <g key={`site-${site}`}>
              <rect
                x={pos.x - 60}
                y={pos.y - 24}
                width={120}
                height={height}
                rx={8}
                fill={pos.color + "08"}
                stroke={pos.color + "30"}
                strokeWidth={1}
              />
              <text
                x={pos.x}
                y={pos.y - 10}
                textAnchor="middle"
                className="text-[9px] font-medium"
                fill={pos.color}
              >
                {pos.label}
              </text>
            </g>
          );
        })}

        {/* Links */}
        {links.map((link) => {
          const src = devicePositions[link.src];
          const dst = devicePositions[link.dst];
          if (!src || !dst) return null;
          const id = `${link.src}--${link.dst}`;
          const isActive = activeLink === id;
          const isPath =
            isOnPath(link.src) && isOnPath(link.dst);
          const utilColor =
            link.metrics.utilization > 0.7
              ? "#ef4444"
              : link.metrics.utilization > 0.4
              ? "#f59e0b"
              : "#22c55e";

          return (
            <g
              key={id}
              onClick={() => onLinkClick(id)}
              className="cursor-pointer"
            >
              <line
                x1={src.x}
                y1={src.y + 6}
                x2={dst.x}
                y2={dst.y + 6}
                stroke={
                  link.state === "down"
                    ? "#ef4444"
                    : isPath
                    ? "#22c55e"
                    : isActive
                    ? "#3b82f6"
                    : "#3f3f46"
                }
                strokeWidth={isPath ? 2.5 : isActive ? 2 : 1}
                strokeDasharray={link.state === "down" ? "4,4" : "none"}
                opacity={link.state === "down" ? 0.5 : 1}
              />
              {/* Utilization indicator */}
              <circle
                cx={(src.x + dst.x) / 2}
                cy={(src.y + dst.y) / 2 + 6}
                r={4}
                fill={utilColor}
                opacity={0.8}
              />
              {isActive && (
                <text
                  x={(src.x + dst.x) / 2}
                  y={(src.y + dst.y) / 2 - 4}
                  textAnchor="middle"
                  fill="#a1a1aa"
                  className="text-[8px]"
                >
                  {link.metrics.latency_us}us
                </text>
              )}
            </g>
          );
        })}

        {/* Device nodes */}
        {devices.map((d) => {
          const pos = devicePositions[d.id];
          if (!pos) return null;
          const onPath = isOnPath(d.id);
          const vendorColors: Record<string, string> = {
            cisco: "#3b82f6",
            arista: "#8b5cf6",
            juniper: "#22c55e",
          };
          const color = vendorColors[d.vendor] || "#6b7280";

          return (
            <g key={d.id}>
              <rect
                x={pos.x - 44}
                y={pos.y}
                width={88}
                height={20}
                rx={4}
                fill={onPath ? color + "40" : "#1c1c21"}
                stroke={onPath ? color : color + "60"}
                strokeWidth={onPath ? 1.5 : 0.5}
              />
              <text
                x={pos.x}
                y={pos.y + 13}
                textAnchor="middle"
                fill={onPath ? "#fafafa" : "#a1a1aa"}
                className="text-[8px] font-medium"
                style={{ fontFamily: "'JetBrains Mono', monospace" }}
              >
                {d.id.replace("dc-east-", "").replace("dc-west-", "").replace("colo-", "").replace("-", " ").slice(0, 14)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ============================================================
// Link Detail Panel
// ============================================================

function LinkDetail({ linkId }: { linkId: string | null }) {
  if (!linkId) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5 flex items-center justify-center h-full min-h-[200px]">
        <p className="text-sm text-[var(--text-muted)]">Click a link to view details</p>
      </div>
    );
  }

  const [src, dst] = linkId.split("--");
  const link = links.find(
    (l) => (l.src === src && l.dst === dst) || (l.src === dst && l.dst === src)
  );
  if (!link) return null;

  const utilPct = (link.metrics.utilization * 100).toFixed(1);
  const utilColor =
    link.metrics.utilization > 0.7
      ? "text-red-400"
      : link.metrics.utilization > 0.4
      ? "text-amber-400"
      : "text-green-400";

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{src} &rarr; {dst}</h3>
        <StatusDot status={link.state} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg bg-[var(--bg-primary)] p-3">
          <p className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1">Latency</p>
          <p className="text-lg font-semibold tabular-nums text-blue-400">{link.metrics.latency_us}<span className="text-xs text-[var(--text-muted)] ml-0.5">us</span></p>
        </div>
        <div className="rounded-lg bg-[var(--bg-primary)] p-3">
          <p className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1">Jitter</p>
          <p className="text-lg font-semibold tabular-nums text-purple-400">{link.metrics.jitter_us}<span className="text-xs text-[var(--text-muted)] ml-0.5">us</span></p>
        </div>
        <div className="rounded-lg bg-[var(--bg-primary)] p-3">
          <p className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1">Utilization</p>
          <p className={`text-lg font-semibold tabular-nums ${utilColor}`}>{utilPct}<span className="text-xs text-[var(--text-muted)] ml-0.5">%</span></p>
        </div>
        <div className="rounded-lg bg-[var(--bg-primary)] p-3">
          <p className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1">Bandwidth</p>
          <p className="text-lg font-semibold tabular-nums text-cyan-400">{(link.bandwidth_mbps / 1000).toFixed(0)}<span className="text-xs text-[var(--text-muted)] ml-0.5">Gbps</span></p>
        </div>
      </div>
      <div className="pt-2 border-t border-[var(--border)]">
        <p className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1.5">Utilization</p>
        <div className="w-full h-2 bg-[var(--bg-primary)] rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              link.metrics.utilization > 0.7
                ? "bg-red-500"
                : link.metrics.utilization > 0.4
                ? "bg-amber-500"
                : "bg-green-500"
            }`}
            style={{ width: `${link.metrics.utilization * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Chaos Results Table
// ============================================================

function ChaosPanel() {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5">
      <h3 className="text-sm font-semibold mb-4">Chaos Engineering</h3>
      <div className="space-y-2.5">
        {chaosResults.map((c) => (
          <div
            key={c.name}
            className="flex items-center justify-between rounded-lg bg-[var(--bg-primary)] px-3.5 py-2.5"
          >
            <div className="flex items-center gap-2.5">
              <StatusDot status={c.status === "passed" ? "up" : "down"} />
              <span className="text-xs font-medium">{c.name}</span>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-xs tabular-nums text-green-400 font-mono">
                {c.failover_ms}ms
              </span>
              <span className="text-[10px] text-[var(--text-muted)]">
                / {c.target_ms}ms
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// Benchmark Table
// ============================================================

function BenchmarkPanel() {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5">
      <h3 className="text-sm font-semibold mb-4">Performance Benchmarks</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[var(--border)]">
              <th className="pb-2 text-left font-medium text-[var(--text-muted)]">Metric</th>
              <th className="pb-2 text-right font-medium text-[var(--text-muted)]">Mean</th>
              <th className="pb-2 text-right font-medium text-[var(--text-muted)]">P99</th>
              <th className="pb-2 text-right font-medium text-[var(--text-muted)]">Target</th>
              <th className="pb-2 text-right font-medium text-[var(--text-muted)]">Status</th>
            </tr>
          </thead>
          <tbody>
            {benchmarks.map((b) => (
              <tr key={b.name} className="border-b border-[var(--border)]/50">
                <td className="py-2.5 font-medium">{b.name}</td>
                <td className="py-2.5 text-right tabular-nums text-[var(--text-secondary)] font-mono">
                  {b.mean}{b.unit}
                </td>
                <td className="py-2.5 text-right tabular-nums font-mono font-semibold text-blue-400">
                  {b.p99}{b.unit}
                </td>
                <td className="py-2.5 text-right tabular-nums text-[var(--text-muted)] font-mono">
                  {b.target}{b.unit}
                </td>
                <td className="py-2.5 text-right">
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      b.passed
                        ? "bg-green-500/10 text-green-400"
                        : "bg-red-500/10 text-red-400"
                    }`}
                  >
                    {b.passed ? "PASS" : "FAIL"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================
// Device List
// ============================================================

function DevicePanel() {
  const vendorIcons: Record<string, string> = {
    cisco: "C",
    arista: "A",
    juniper: "J",
  };
  const vendorColors: Record<string, string> = {
    cisco: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    arista: "bg-purple-500/20 text-purple-400 border-purple-500/30",
    juniper: "bg-green-500/20 text-green-400 border-green-500/30",
  };

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold">Devices</h3>
        <span className="text-xs text-[var(--text-muted)]">{devices.length} total</span>
      </div>
      <div className="space-y-1.5 max-h-[300px] overflow-y-auto pr-1">
        {devices.map((d) => (
          <div
            key={d.id}
            className="flex items-center justify-between rounded-lg bg-[var(--bg-primary)] px-3 py-2 hover:bg-[var(--bg-card-hover)] transition-colors"
          >
            <div className="flex items-center gap-2.5">
              <StatusDot status="up" />
              <div>
                <p className="text-xs font-medium font-mono">{d.id}</p>
                <p className="text-[10px] text-[var(--text-muted)]">{d.site}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-[var(--text-muted)] font-mono">{d.loopback}</span>
              <span
                className={`inline-flex items-center justify-center w-5 h-5 rounded text-[10px] font-bold border ${
                  vendorColors[d.vendor] || ""
                }`}
              >
                {vendorIcons[d.vendor] || "?"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// SDN Decision Log
// ============================================================

function SDNLog() {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const interval = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  const events = [
    { time: "09:55:40.717", type: "REROUTE", msg: "dc-east-core-01 -> nyse-exchange via backup (265us, 4 hops)", color: "text-amber-400" },
    { time: "09:55:40.720", type: "RESTORE", msg: "dc-east-core-01 -> colo-nyse-edge-01 link restored", color: "text-green-400" },
    { time: "09:55:40.721", type: "OPTIMAL", msg: "Reverted to optimal path (205us, 2 hops)", color: "text-blue-400" },
    { time: "09:55:40.700", type: "RPKI", msg: "HIJACK BLOCKED: AS99999 announced 198.51.100.0/24 (expected AS11111)", color: "text-red-400" },
    { time: "09:55:40.715", type: "CHAOS", msg: "Link failure injected: dc-east-core-01 -- colo-nyse-edge-01", color: "text-purple-400" },
  ];

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold">SDN Controller Log</h3>
        <span className="text-[10px] tabular-nums text-[var(--text-muted)] font-mono">
          {time.toLocaleTimeString()}
        </span>
      </div>
      <div className="space-y-1 font-mono text-[11px]">
        {events.map((e, i) => (
          <div key={i} className="flex gap-2 py-1 border-b border-[var(--border)]/30">
            <span className="text-[var(--text-muted)] shrink-0">{e.time}</span>
            <span className={`font-semibold shrink-0 w-16 ${e.color}`}>{e.type}</span>
            <span className="text-[var(--text-secondary)] truncate">{e.msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// Main Dashboard
// ============================================================

export default function Dashboard() {
  const [activeLink, setActiveLink] = useState<string | null>(null);
  const [uptime, setUptime] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setUptime((u) => u + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const linksUp = links.filter((l) => l.state === "up").length;
  const avgLatency = (
    links.reduce((sum, l) => sum + l.metrics.latency_us, 0) / links.length
  ).toFixed(0);

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-[var(--border)] bg-[var(--bg-primary)]/80 backdrop-blur-xl">
        <div className="max-w-[1600px] mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-500 flex items-center justify-center">
              <span className="text-white text-xs font-bold">TF</span>
            </div>
            <div>
              <h1 className="text-sm font-semibold tracking-tight">TradeNet Fabric</h1>
              <p className="text-[10px] text-[var(--text-muted)] -mt-0.5">Network Control Plane</p>
            </div>
          </div>
          <div className="flex items-center gap-5">
            <div className="flex items-center gap-2">
              <StatusDot status="healthy" />
              <span className="text-xs text-[var(--text-secondary)]">Controller Healthy</span>
            </div>
            <span className="text-xs tabular-nums text-[var(--text-muted)] font-mono">
              Uptime: {Math.floor(uptime / 3600)}h {Math.floor((uptime % 3600) / 60)}m {uptime % 60}s
            </span>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-6">
        {/* Top Metrics Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 animate-fade-in">
          <MetricCard label="Devices" value={devices.length.toString()} unit="active" color="blue" subtitle="All sites" />
          <MetricCard label="Links" value={`${linksUp}/${links.length}`} unit="up" color="green" subtitle="0 down" />
          <MetricCard label="Avg Latency" value={avgLatency} unit="us" color="cyan" subtitle="All links" />
          <MetricCard label="Failover P99" value="1.98" unit="ms" color="purple" subtitle="Target: 100ms" />
          <MetricCard label="Path Comp P99" value="1.52" unit="ms" color="amber" subtitle="Target: 50ms" />
          <MetricCard label="Tests" value="29" unit="passing" color="green" subtitle="21 unit + 8 prop" />
        </div>

        {/* Main Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Topology Map — spans 2 columns */}
          <div className="lg:col-span-2 space-y-4">
            <TopologyMap activeLink={activeLink} onLinkClick={setActiveLink} />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <ChaosPanel />
              <BenchmarkPanel />
            </div>
          </div>

          {/* Right sidebar */}
          <div className="space-y-4">
            <LinkDetail linkId={activeLink} />
            <SDNLog />
            <DevicePanel />
          </div>
        </div>

        {/* Optimal Path Banner */}
        <div className="rounded-xl border border-green-500/20 bg-green-500/5 p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-green-500/20 flex items-center justify-center">
              <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </div>
            <div>
              <p className="text-xs font-semibold text-green-400">Optimal Path: DC-East &rarr; NYSE Exchange</p>
              <p className="text-[11px] text-[var(--text-secondary)] font-mono mt-0.5">
                {optimalPath.hops.join(" → ")}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-6 text-xs">
            <div>
              <span className="text-[var(--text-muted)]">Latency: </span>
              <span className="font-semibold tabular-nums text-green-400 font-mono">{optimalPath.total_latency_us}us</span>
            </div>
            <div>
              <span className="text-[var(--text-muted)]">Hops: </span>
              <span className="font-semibold tabular-nums text-green-400 font-mono">{optimalPath.hop_count}</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <footer className="text-center py-6 text-xs text-[var(--text-muted)] border-t border-[var(--border)]">
          <p>TradeNet Fabric &mdash; SDN Controller Dashboard</p>
          <p className="mt-1">Python + React + eBPF &middot; Built for Jane Street Network Engineering</p>
        </footer>
      </main>
    </div>
  );
}
