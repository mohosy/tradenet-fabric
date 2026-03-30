# ADR-002: OCaml for the SDN Controller

## Status
Accepted

## Context
We need to choose a language for the SDN controller — the central component that ingests telemetry, computes optimal paths, and pushes routing policy changes to network devices.

## Decision
**OCaml 5.x with the Dune build system.**

## Why OCaml
1. **Jane Street's primary language.** They write almost all their production software in OCaml. Demonstrating comfort with OCaml on a networking project signals that I can work in their stack — not just for networking, but for the systems-level code that surrounds it.

2. **Strong type system for correctness.** The SDN controller pushes BGP route maps to live routers. A bug here could blackhole traffic or create routing loops. OCaml's type system catches entire classes of bugs at compile time: you can't accidentally pass a device where a link is expected, or confuse latency with utilization.

3. **Pattern matching for network state machines.** Network devices have states (Up, Down, Degraded). Links have states. BGP sessions have states. Pattern matching makes handling these states exhaustive — the compiler warns you if you miss a case.

4. **Immutable data structures for concurrency.** The telemetry collector updates the network graph continuously while the path computation engine reads it. With immutable data structures, we don't need locks — we atomically swap the reference to the new graph. This eliminates a whole class of concurrency bugs.

5. **Performance.** OCaml compiles to native code. Path computation needs to be fast (target: <50ms). OCaml gives us near-C performance without sacrificing safety.

## Alternatives Considered

### Python
- **Pro:** Everyone knows Python, rich networking libraries (NAPALM, Nornir, Scapy)
- **Con:** Too slow for real-time path computation. No static types means bugs show up at runtime. Doesn't demonstrate OCaml proficiency. We already use Python for automation (Ansible/Nornir) — the SDN controller should show breadth.

### Go
- **Pro:** Fast, compiled, good concurrency model, popular for network tools
- **Con:** Jane Street doesn't use Go. The type system is weaker than OCaml's. Go's error handling (`if err != nil`) is verbose compared to OCaml's Result types.

### Rust
- **Pro:** Extremely fast, strong safety guarantees
- **Con:** Jane Street doesn't use Rust. The learning curve would slow down the project. Ownership model adds complexity that isn't needed for this use case.

## Key Libraries
- `lwt` — Async I/O for telemetry streaming
- `dream` — HTTP framework for the REST API
- `ocamlgraph` — Graph algorithms (Dijkstra)
- `yojson` — JSON serialization
- `qcheck` — Property-based testing (Phase 10)
- `alcotest` — Unit testing

## Consequences
- **Positive:** Demonstrates OCaml proficiency directly relevant to Jane Street
- **Positive:** Type-safe control plane code that's hard to break
- **Positive:** Native compilation gives excellent performance
- **Negative:** Smaller ecosystem than Python/Go for networking
- **Negative:** Learning curve (mitigated by building incrementally)
