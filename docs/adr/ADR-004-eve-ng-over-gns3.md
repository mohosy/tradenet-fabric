# ADR-004: EVE-NG over GNS3/Containerlab

## Status
Accepted

## Context
We need a network simulation platform to host our multi-vendor topology. The platform must support Cisco, Arista, and Juniper virtual images running simultaneously, provide API access for automation, and be accessible via a web interface.

## Decision
**EVE-NG Community Edition, hosted in a UTM virtual machine on macOS (Apple Silicon).**

## Alternatives Considered

### GNS3
- **Pro:** Open source, large community, good documentation
- **Con:** GNS3 uses a client-server model that's clunkier for API automation. Multi-vendor image management is less clean. The GNS3 VM adds another layer of complexity. EVE-NG's web UI is more streamlined for lab work.

### Containerlab
- **Pro:** Modern, container-native, great for CI/CD pipelines, declarative topology files
- **Con:** Requires container images (cEOS, vMX containers) which have different licensing and availability than traditional VM images. Not all vendors have well-supported container images. Less mature for complex multi-vendor scenarios with full-featured routing.

### Physical hardware
- **Pro:** Most realistic
- **Con:** Expensive, not portable, not reproducible. A virtual lab can be version-controlled and rebuilt from scratch — a physical lab cannot.

### Why UTM over VirtualBox/VMware Fusion?
- UTM is free and native to Apple Silicon (arm64) — no x86 emulation overhead
- VirtualBox has poor Apple Silicon support
- VMware Fusion works but costs money for the features we need

## Consequences
- **Positive:** Web-based UI accessible from Mac browser, API for automation, supports all three vendors
- **Positive:** UTM + Apple Silicon means good performance for multiple virtual routers/switches
- **Negative:** EVE-NG CE has some limitations vs. Professional (max nodes, features) — acceptable for our lab scale
- **Negative:** Some vendor images (Cisco IOSv) are x86-only, requiring QEMU emulation on arm64 — may need to use alternative images or accept some performance overhead
