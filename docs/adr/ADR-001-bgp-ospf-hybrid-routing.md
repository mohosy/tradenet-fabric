# ADR-001: BGP/OSPF Hybrid Routing Design

## Status
Accepted

## Context
We need a routing architecture for a multi-site trading firm network that spans 3 data centers, 3 exchange colocations, and external transit providers. The design must optimize for:
- **Fast intra-site failover** (sub-second) — market hours cannot tolerate routing convergence delays
- **Inter-site traffic engineering** — we need to control exactly which path traffic takes between sites
- **External peering** — exchanges and transit providers use BGP; we must speak their protocol
- **Scalability** — the design must handle growth without re-architecture

## Decision
**OSPF within each site, iBGP with route reflectors between sites, eBGP for external peering.**

### Intra-site: OSPF
Each site runs OSPF in its own area. OSPF is a link-state protocol — every router within an area has a complete view of the topology and computes shortest paths locally using Dijkstra's algorithm. When a link fails, OSPF detects it (via hello timer expiry or BFD) and reconverges in under 1 second.

### Inter-site: iBGP with Route Reflectors
All sites share ASN 65001. Core routers at DC-East and DC-West act as route reflectors. This gives us:
- **Policy control:** BGP attributes (local-preference, MED, AS-path prepend, communities) let us fine-tune path selection between sites
- **Scalability:** Route reflectors reduce the iBGP peering mesh from O(n^2) to O(n)
- **Traffic engineering:** We can steer traffic to prefer DC-East → Colo-NYSE over DC-West → Colo-NYSE by manipulating local-preference

### External: eBGP
We peer with simulated exchanges (NYSE, CME, NASDAQ) and transit providers over eBGP. This is how real trading firms receive market data routes and advertise their own prefixes.

## Alternatives Considered

### Pure OSPF everywhere
- **Pro:** Simpler — one protocol to manage
- **Con:** OSPF has no concept of policy. You can't say "prefer this path for trading traffic but use that path for backups." It just picks the shortest path by cost. Inter-site traffic engineering becomes nearly impossible. OSPF also doesn't scale well across organizational boundaries — it floods LSAs everywhere, which gets expensive at scale.

### Pure BGP everywhere (including intra-site)
- **Pro:** One protocol, full policy control everywhere
- **Con:** BGP converges slowly within a site. BGP's default timers (60s keepalive, 180s hold) are way too slow for intra-site failover. Even with aggressive tuning and BFD, BGP was designed for inter-domain stability, not intra-domain speed. You'd be fighting the protocol's design philosophy.

### IS-IS instead of OSPF
- **Pro:** IS-IS is technically more extensible and is what some large ISPs use
- **Con:** Less vendor support in lab environments (EVE-NG images), less community documentation for learning, and practically no advantage over OSPF at our scale. IS-IS shines at ISP scale — we're a trading firm, not an ISP.

### iBGP confederation instead of route reflectors
- **Pro:** Avoids the single-point-of-failure concern with route reflectors
- **Con:** Confederations add sub-AS complexity that's harder to debug and operate. At our scale (6 sites), route reflectors with redundancy (2 RRs) are simpler and sufficient. Jane Street's network is large but not ISP-scale — operational simplicity wins.

## Consequences
- **Positive:** Fast intra-site failover, full inter-site policy control, standard external peering
- **Positive:** Each site is an independent OSPF failure domain — a problem in one site's OSPF doesn't affect others
- **Negative:** Two routing protocols to learn, configure, and debug (acceptable tradeoff)
- **Negative:** Route redistribution between OSPF and BGP requires careful filtering to avoid loops (we handle this with explicit prefix lists)
