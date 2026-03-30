# ADR-006: Using Both Ansible AND Nornir

## Status
Accepted

## Context
We need network automation for configuration management and operational tasks. Both Ansible and Nornir are popular in the network automation space.

## Decision
**Use both: Ansible for declarative config management, Nornir for programmatic operations.**

## Why Both
They serve different purposes:

### Ansible: "Make it look like this"
- Declarative — you define the desired state, Ansible figures out how to get there
- Jinja2 templates generate device configs from variables
- Idempotent — running the same playbook twice produces the same result
- Best for: initial provisioning, config changes, bulk updates

### Nornir: "Gather this, decide, then act"
- Programmatic — it's Python, so you can write real logic
- Best for: auditing, troubleshooting, complex operational workflows
- Example: "Check OSPF neighbors, compare against expected count, alert if mismatch"

### Why not just Ansible?
Ansible's YAML-based logic (when/with_items/register/set_fact) gets painful for complex operations. Try writing a network audit with conditional alerts in Ansible — it's verbose and hard to debug. In Nornir, it's just Python.

### Why not just Nornir?
Nornir doesn't have Ansible's template engine integration or role/playbook structure. For "push this config template to 50 devices," Ansible is cleaner.

## Consequences
- **Positive:** Right tool for each job — clean config management AND flexible operations
- **Positive:** Shows breadth — familiarity with both major network automation frameworks
- **Positive:** Jane Street automates everything; showing you can pick the right tool matters
- **Negative:** Two tools to maintain, two inventories to keep in sync (mitigated by shared variable files)
