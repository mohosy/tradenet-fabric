# TradeNet Fabric

**A software-defined network simulator for quantitative trading infrastructure.**

Built from scratch: an OCaml SDN controller, multi-vendor network automation, eBPF kernel monitoring, chaos engineering, RPKI security, and a real-time dashboard — simulating the full network stack of a quantitative trading firm.

[Live Dashboard](https://frontend-two-eta-77.vercel.app)

---

## Performance

| Metric | P99 | Target | Result |
|--------|-----|--------|--------|
| Path Computation (Dijkstra) | **1.52ms** | 50ms | 33x under budget |
| Failover After Link Failure | **1.98ms** | 100ms | 50x under budget |
| API Response (Health) | **0.94ms** | 10ms | 10x under budget |
| Topology Serialization | **1.14ms** | 20ms | 17x under budget |

29 tests passing (21 unit + 8 property-based across 1,600 random topologies).

---

## Architecture

```
                        ┌─────────────┐
                        │  INTERNET    │
                        │  (Transit)   │
                        └──────┬──────┘
                               │ eBGP
                  ┌────────────┼────────────┐
                  │            │            │
            ┌─────┴─────┐ ┌───┴────┐ ┌────┴─────┐
            │  DC-EAST   │ │DC-WEST │ │ DR-SITE  │
            │ (Primary)  │ │(Second)│ │(Disaster)│
            └─────┬─────┘ └───┬────┘ └────┬─────┘
                  │            │            │
                  │      iBGP Full Mesh     │
                  │    (Route Reflectors)    │
                  │            │            │
            ┌─────┴──────────┬─┴───────────┴──┐
            │                │                 │
       ┌────┴────┐    ┌─────┴─────┐    ┌─────┴─────┐
       │  NYSE   │    │   CME     │    │  NASDAQ   │
       │  Colo   │    │   Colo    │    │   Colo    │
       └─────────┘    └───────────┘    └───────────┘
```

**6 sites, 12 devices, 12 links** — 3 data centers, 3 exchange colocations, multi-vendor (Cisco backbone, Arista DC switches, Juniper edge/firewall).

---

## Components

### OCaml SDN Controller
The core of the project. An SDN controller written in OCaml that ingests network telemetry, computes optimal paths using Dijkstra's algorithm weighted by live metrics, and exposes a REST API.

- **4 traffic classes** with distinct optimization objectives: market data (min latency), trading (min latency + jitter), bulk transfer (max bandwidth), management (max reliability)
- **Constraint engine** — avoid specific links, avoid sites, enforce max latency/hop budgets
- **Immutable graph** — functional updates for lock-free concurrent access between telemetry ingestion and path computation
- **Property-based testing** with QCheck: 8 invariants verified across 1,600 randomly generated topologies (path existence, optimality, symmetry, loop-freedom, failover correctness, metric consistency, JSON roundtrip, traffic class ordering)

```
sdn-controller/
├── lib/
│   ├── topology/       # Network graph (devices, links, metrics, Dijkstra)
│   ├── pathcomp/       # Path computation engine (traffic classes, constraints)
│   └── api/            # Dream REST API (6 endpoints)
├── bin/                # Main binary (demo topology + server)
└── test/
    ├── unit/           # 21 Alcotest cases
    └── property/       # 8 QCheck properties
```

### Multi-Vendor Automation
Ansible + Nornir automation for Cisco IOS, Arista EOS, and Juniper Junos. Same features, three different config syntaxes, all generated from Jinja2 templates.

- **Ansible** — Declarative config management with vendor-specific templates for base provisioning, OSPF, BGP, and security
- **Nornir** — Programmatic network audit (OSPF adjacency verification, BGP session health, interface error counters)
- **CI validation** — YAML linting, Jinja2 syntax checking, addressing plan consistency, cross-reference validation

### eBPF Traffic Analysis
Kernel-level network monitoring using eBPF for per-flow latency measurement with microsecond precision.

- BPF program attached at TC ingress hook — processes every packet in-kernel with zero copy to userspace
- Per-flow metrics via BPF hash maps and ring buffer export
- Prometheus exporter for Grafana dashboards and SDN controller integration
- Simulation mode for demo without Linux kernel requirements

### Chaos Engineering
Automated fault injection with measurable failover targets.

| Scenario | Failover | Target |
|----------|----------|--------|
| Link Failure — DC-East to NYSE | 2.5ms | 100ms |
| Link Failure — Inter-DC WAN | 2.0ms | 500ms |
| BGP Hijack — NYSE Prefix | 1.4ms | 5,000ms |

Each scenario verifies preconditions, injects the fault via the SDN controller API, measures impact, validates postconditions, and restores the network.

### RPKI Validation
BGP route origin validation to detect and block route hijacks. Maintains a local ROA database, validates announcements per RFC 6811, and generates alerts on INVALID origins. Tested against simulated hijack scenarios (AS99999 announcing NYSE prefixes — caught and rejected).

### Market Data Simulation
Multicast market data feed simulator for NYSE, CME, and NASDAQ with jitter analysis. Generates realistic trading traffic (equities, futures, options) across PIM-SM multicast groups and measures inter-packet arrival variance.

### Zone-Based Firewall
Security zone architecture with auto-generated Juniper Junos rules. 4 zones (trading, exchange, management, internet) with a full policy matrix — generated from YAML definitions, not hand-written.

### Real-Time Dashboard
Next.js + Tailwind CSS dashboard deployed on Vercel. Shows live topology with optimal path visualization, link metrics, chaos test results, benchmark numbers, SDN controller decision log, and device inventory.

---

## Routing Design

**OSPF within sites** — Link-state protocol, sub-second convergence, BFD for 300ms failure detection. Each site is its own OSPF area (failure domain isolation).

**iBGP between sites** — Route reflectors at DC-East and DC-West. Aggressive timers (10s/30s). Soft reconfiguration for hitless policy changes during market hours.

**eBGP for external peering** — Simulated exchange and transit provider connections with prefix filtering and RPKI validation.

**Why hybrid?** OSPF gives speed inside a site. BGP gives policy control between sites. Pure OSPF can't do traffic engineering. Pure BGP converges too slowly intra-site. The hybrid approach is how production trading networks actually work.

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| SDN Controller | OCaml 5.4, Dream, OCamlGraph | Strong types for control-plane safety, native performance |
| Network Sim | EVE-NG (Cisco/Arista/Juniper) | Multi-vendor realism |
| Automation | Ansible + Nornir + Jinja2 | Declarative config + programmatic operations |
| Monitoring | eBPF (C) + Prometheus + Grafana | Kernel-level precision, industry-standard metrics |
| Security | RPKI (Routinator) | Cryptographic route origin validation |
| Firewall | Juniper SRX zones | Stateful inspection with auto-generated rules |
| Dashboard | Next.js 15, Tailwind CSS 4, Vercel | Modern frontend, static export, instant deploy |
| Testing | Alcotest + QCheck | Unit tests + property-based testing |

---

## Quick Start

```bash
# Install OCaml dependencies
opam install . --deps-only --yes

# Install Python dependencies
pip install -r requirements.txt

# Build and run the SDN controller
cd sdn-controller && dune build && dune exec bin/main.exe

# Run tests (29 total)
dune runtest

# Run chaos scenarios (requires running controller)
python3 chaos/engine/chaos_runner.py

# Run benchmarks
python3 benchmarks/scripts/run_benchmarks.py

# Validate all configs
python3 automation/ci/validate_configs.py

# Run RPKI demo
python3 security/rpki/rpki_validator.py

# Run market data simulation
python3 multicast/generators/market_data_sim.py
```

---

## Architecture Decision Records

Every major design choice is documented with context, alternatives considered, and tradeoffs:

- [ADR-001](docs/adr/ADR-001-bgp-ospf-hybrid-routing.md) — BGP/OSPF Hybrid Routing
- [ADR-002](docs/adr/ADR-002-ocaml-sdn-controller.md) — OCaml for SDN Controller
- [ADR-003](docs/adr/ADR-003-ebpf-over-sflow.md) — eBPF over sFlow/NetFlow
- [ADR-004](docs/adr/ADR-004-eve-ng-over-gns3.md) — EVE-NG over GNS3/Containerlab
- [ADR-006](docs/adr/ADR-006-ansible-and-nornir.md) — Ansible + Nornir (Both)
- [ADR-009](docs/adr/ADR-009-multi-vendor-topology.md) — Multi-Vendor Topology

---

## Project Structure

```
tradenet-fabric/
├── sdn-controller/          # OCaml SDN controller (Dijkstra, REST API, tests)
├── automation/
│   ├── ansible/             # Playbooks, inventory, group vars
│   ├── nornir/              # Python audit scripts
│   ├── templates/           # Jinja2 per vendor (cisco_ios, arista_eos, junos)
│   └── ci/                  # Config validation pipeline
├── monitoring/
│   ├── ebpf/                # BPF C programs
│   └── userspace/           # Prometheus metrics exporter
├── chaos/                   # Chaos engineering (scenarios + runner)
├── security/rpki/           # RPKI validator + alerting
├── multicast/               # Market data feed simulator
├── firewall/                # Zone-based firewall generator
├── dashboard/frontend/      # Next.js + Tailwind dashboard
├── topology/                # IP addressing plan
├── benchmarks/              # Performance benchmark suite
├── docs/adr/                # Architecture Decision Records
├── Makefile                 # One-command orchestration
└── requirements.txt         # Python dependencies
```

---

*Built by Mo Shirmohammadi*
