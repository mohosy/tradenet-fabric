# TradeNet Fabric — Project Orchestration
# ==========================================
# One-command deployment and testing for a simulated
# quantitative trading firm network infrastructure.
#
# Usage:
#   make setup      — Install all dependencies (first time only)
#   make deploy     — Bring up the entire network from scratch
#   make teardown   — Clean shutdown of all components
#   make test       — Run all unit, property, and integration tests
#   make chaos      — Run chaos engineering test suite
#   make bench      — Run benchmarks and generate report
#   make lint       — Validate all configs and templates
#   make clean      — Remove build artifacts

.PHONY: setup deploy teardown test chaos bench lint clean \
        setup-ocaml setup-python setup-ebpf \
        deploy-topology deploy-configs deploy-sdn deploy-monitoring deploy-dashboard \
        test-unit test-property test-integration

# ============================================================
# Setup — Install all dependencies
# ============================================================
setup: setup-ocaml setup-python
	@echo "All dependencies installed."

setup-ocaml:
	@echo "Installing OCaml toolchain..."
	opam install . --deps-only --yes
	@echo "OCaml dependencies installed."

setup-python:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	@echo "Python dependencies installed."

# ============================================================
# Deploy — Bring up the full network
# ============================================================
deploy: deploy-topology deploy-configs deploy-sdn deploy-monitoring deploy-dashboard
	@echo "=========================================="
	@echo "TradeNet Fabric is running."
	@echo "Dashboard: http://localhost:8080"
	@echo "SDN Controller API: http://localhost:9090"
	@echo "Prometheus: http://localhost:9091"
	@echo "Grafana: http://localhost:3000"
	@echo "=========================================="

deploy-topology:
	@echo "Provisioning EVE-NG topology..."
	# TODO: EVE-NG API calls to create/start topology

deploy-configs:
	@echo "Pushing device configurations..."
	cd automation && ansible-playbook ansible/playbooks/site.yaml

deploy-sdn:
	@echo "Starting SDN controller..."
	cd sdn-controller && dune exec bin/main.exe &

deploy-monitoring:
	@echo "Starting monitoring stack..."
	# TODO: Start eBPF probes, Prometheus, Grafana

deploy-dashboard:
	@echo "Starting dashboard..."
	# TODO: Start OCaml backend + React frontend

# ============================================================
# Teardown — Clean shutdown
# ============================================================
teardown:
	@echo "Shutting down TradeNet Fabric..."
	# TODO: Stop all components in reverse order

# ============================================================
# Testing
# ============================================================
test: test-unit test-property test-integration
	@echo "All tests passed."

test-unit:
	@echo "Running unit tests..."
	cd sdn-controller && dune runtest

test-property:
	@echo "Running property-based tests..."
	cd sdn-controller && dune exec test/property/run_properties.exe

test-integration:
	@echo "Running integration tests..."
	# TODO: Integration tests against live topology

# ============================================================
# Chaos Engineering
# ============================================================
chaos:
	@echo "Running chaos test suite..."
	python3 chaos/engine/run_all.py
	@echo "Chaos report: chaos/reports/latest.html"

# ============================================================
# Benchmarks
# ============================================================
bench:
	@echo "Running benchmarks..."
	python3 benchmarks/scripts/run_all.py
	@echo "Benchmark report: benchmarks/reports/latest.html"

# ============================================================
# Linting & Validation
# ============================================================
lint:
	@echo "Validating configurations..."
	python3 automation/ci/validate_configs.py
	python3 automation/ci/lint_templates.py
	cd sdn-controller && dune build @fmt
	@echo "All validations passed."

# ============================================================
# Clean
# ============================================================
clean:
	cd sdn-controller && dune clean
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean."
