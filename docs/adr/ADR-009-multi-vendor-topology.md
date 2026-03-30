# ADR-009: Multi-Vendor Topology Design

## Status
Accepted

## Context
We need to decide whether to use a single vendor or multiple vendors for our simulated trading firm network. Real trading firms run multi-vendor networks — the question is whether the added complexity is worth it for a project.

## Decision
**Multi-vendor: Cisco (backbone), Arista (data center), Juniper (edge/firewall).**

### Vendor-to-role mapping:
- **Cisco IOSv** → Core/backbone routers (DC interconnects, WAN)
  - Why: Cisco has the most mature BGP implementation, battle-tested in backbone roles globally
- **Arista vEOS** → Data center leaf/spine switches
  - Why: Arista dominates modern data center networking. Their EOS is Linux-based, API-first (eAPI), and automation-friendly — exactly what data center teams want
- **Juniper vSRX** → Edge routers at exchange colocations (with firewall capabilities)
  - Why: Juniper's SRX line combines routing and security (zone-based firewall), making them ideal for perimeter roles where you need both

## Alternatives Considered

### Single vendor (all Cisco)
- **Pro:** Simpler configuration syntax, one set of automation templates
- **Con:** Unrealistic. No trading firm runs single-vendor. It signals "I only know Cisco" rather than "I understand network engineering." Jane Street's job description says "multi-vendor" — this is a direct requirement.

### Different vendor mapping (e.g., Arista backbone, Cisco DC)
- **Pro:** Could work technically
- **Con:** Our mapping reflects industry norms. Arista's strength is data center leaf/spine (their market dominance is there). Cisco's BGP implementation is the reference standard for backbone. Juniper SRX is purpose-built for edge security. Deviating from these norms would need a strong reason.

## Consequences
- **Positive:** Demonstrates real-world multi-vendor competence
- **Positive:** Forces us to build vendor-agnostic automation (Jinja2 templates per vendor, Nornir with multiple connection plugins)
- **Positive:** Each vendor's CLI/API is different — learning to handle this is directly applicable to the job
- **Negative:** More complex automation (need templates per vendor per feature)
- **Negative:** Different configuration syntax for the same feature (e.g., OSPF on Cisco vs. Arista vs. Juniper) — but this is a feature, not a bug, for interview purposes
