# ADR-003: eBPF over sFlow/NetFlow for Traffic Analysis

## Status
Accepted

## Context
We need network monitoring that feeds real-time metrics into the SDN controller for path optimization. The metrics must include per-flow latency, jitter, and packet loss at high precision.

## Decision
**eBPF probes attached to network interfaces, with metrics exported via Prometheus.**

## Why eBPF
1. **Precision.** eBPF operates in-kernel with nanosecond timestamps. We achieve 10μs-precision per-flow latency measurement. sFlow samples 1-in-N packets (typically 1-in-1000), NetFlow aggregates into flows — neither gives per-packet precision.

2. **Programmability.** We write custom analysis logic (C programs compiled to BPF bytecode). We can measure exactly what matters for trading: jitter on multicast market data feeds, latency distribution across specific paths. sFlow/NetFlow only give predefined counters.

3. **Performance.** eBPF runs in kernel space — packets are analyzed in-place without copying to userspace. This is critical for monitoring high-throughput links without adding latency to the traffic being monitored.

4. **Jane Street relevance.** Their network team maintains production trading infrastructure. Building custom, precision monitoring tools (not just deploying off-the-shelf Grafana dashboards) demonstrates the kind of systems-level capability they need.

## Alternatives Considered

### sFlow
- **Pro:** Industry standard, widely supported by network devices, easy to deploy
- **Con:** Sampled — misses most packets. At 1-in-1000 sampling, you can estimate averages but can't measure per-flow jitter. A market data feed that jitters for 50ms might never be captured in the sample.

### NetFlow/IPFIX
- **Pro:** Flow-level aggregation, built into most routers
- **Con:** Aggregated after the fact — you get total bytes/packets per flow, not per-packet timing. Export intervals (typically 60s) are too slow for real-time SDN decisions.

### SNMP polling
- **Pro:** Universal support, simple to implement
- **Con:** Interface-level counters only, no per-flow visibility. Polling intervals (typically 5-60s) are far too slow.

### Packet mirroring (SPAN/TAP)
- **Pro:** Captures everything
- **Con:** Requires separate analysis infrastructure, doubles bandwidth consumption, complex at scale.

## Consequences
- **Positive:** Highest possible monitoring precision
- **Positive:** Custom logic for trading-specific metrics
- **Positive:** Minimal performance overhead on monitored traffic
- **Negative:** Requires Linux (eBPF is a Linux kernel feature) — runs in EVE-NG VM, not on network devices directly
- **Negative:** More complex to develop than configuring sFlow
