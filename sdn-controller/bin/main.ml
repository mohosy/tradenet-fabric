(* TradeNet Fabric — SDN Controller Entry Point
   =============================================
   This is the main binary that:
   1. Loads the network topology (from YAML addressing plan)
   2. Initializes the graph with all devices and links
   3. Starts the REST API server
   4. (Future) Starts the telemetry collector
   5. (Future) Starts the policy engine loop

   For now, we initialize with the demo topology so we can
   verify the build works and the API responds correctly.
*)

open Topology.Network_graph

(* ============================================================
   Demo Topology Builder

   Creates a small version of our trading firm topology for
   testing. This will later be replaced by loading from the
   YAML addressing plan or discovering from live devices.
   ============================================================ *)

let default_metrics = {
  latency_us = 100.0;
  jitter_us = 10.0;
  utilization = 0.1;
  packet_loss = 0.0;
  last_updated = Unix.gettimeofday ();
}

let make_link ~id ~src_if ~dst_if ?(bw=10000) ?(cost=10) ?(latency=100.0) () = {
  id;
  src_interface = src_if;
  dst_interface = dst_if;
  bandwidth_mbps = bw;
  state = Up;
  metrics = { default_metrics with latency_us = latency };
  ospf_cost = cost;
}

let build_demo_topology () =
  let g = empty () in

  (* DC-East devices *)
  let g = add_device g {
    id = "dc-east-core-01"; name = "DC-East Core Router 01";
    role = CoreRouter; site = "dc-east";
    loopback = "10.1.0.1"; vendor = "cisco"; asn = 65001;
  } in
  let g = add_device g {
    id = "dc-east-core-02"; name = "DC-East Core Router 02";
    role = CoreRouter; site = "dc-east";
    loopback = "10.1.0.2"; vendor = "cisco"; asn = 65001;
  } in
  let g = add_device g {
    id = "dc-east-spine-01"; name = "DC-East Spine Switch 01";
    role = SpineSwitch; site = "dc-east";
    loopback = "10.1.0.11"; vendor = "arista"; asn = 65001;
  } in
  let g = add_device g {
    id = "dc-east-spine-02"; name = "DC-East Spine Switch 02";
    role = SpineSwitch; site = "dc-east";
    loopback = "10.1.0.12"; vendor = "arista"; asn = 65001;
  } in

  (* DC-West devices *)
  let g = add_device g {
    id = "dc-west-core-01"; name = "DC-West Core Router 01";
    role = CoreRouter; site = "dc-west";
    loopback = "10.2.0.1"; vendor = "cisco"; asn = 65001;
  } in
  let g = add_device g {
    id = "dc-west-spine-01"; name = "DC-West Spine Switch 01";
    role = SpineSwitch; site = "dc-west";
    loopback = "10.2.0.11"; vendor = "arista"; asn = 65001;
  } in

  (* Colo-NYSE devices *)
  let g = add_device g {
    id = "colo-nyse-edge-01"; name = "NYSE Colo Edge Router 01";
    role = EdgeRouter; site = "colo-nyse";
    loopback = "10.4.0.1"; vendor = "juniper"; asn = 65001;
  } in
  let g = add_device g {
    id = "colo-nyse-edge-02"; name = "NYSE Colo Edge Router 02";
    role = EdgeRouter; site = "colo-nyse";
    loopback = "10.4.0.2"; vendor = "juniper"; asn = 65001;
  } in

  (* NYSE Exchange (simulated) *)
  let g = add_device g {
    id = "nyse-exchange"; name = "NYSE Exchange Router";
    role = ExchangeRouter; site = "nyse";
    loopback = "198.51.100.1"; vendor = "cisco"; asn = 11111;
  } in

  (* DC-East internal links *)
  let g = add_link g ~src:"dc-east-core-01" ~dst:"dc-east-core-02"
    (make_link ~id:"dc-east-core-01--dc-east-core-02"
       ~src_if:"GigabitEthernet0/1" ~dst_if:"GigabitEthernet0/1"
       ~latency:50.0 ~cost:5 ()) in
  let g = add_link g ~src:"dc-east-core-01" ~dst:"dc-east-spine-01"
    (make_link ~id:"dc-east-core-01--dc-east-spine-01"
       ~src_if:"GigabitEthernet0/2" ~dst_if:"Ethernet1"
       ~latency:30.0 ~cost:3 ()) in
  let g = add_link g ~src:"dc-east-core-02" ~dst:"dc-east-spine-02"
    (make_link ~id:"dc-east-core-02--dc-east-spine-02"
       ~src_if:"GigabitEthernet0/2" ~dst_if:"Ethernet1"
       ~latency:30.0 ~cost:3 ()) in

  (* Inter-site WAN: DC-East <-> DC-West *)
  let g = add_link g ~src:"dc-east-core-01" ~dst:"dc-west-core-01"
    (make_link ~id:"dc-east-core-01--dc-west-core-01"
       ~src_if:"GigabitEthernet0/3" ~dst_if:"GigabitEthernet0/3"
       ~bw:10000 ~latency:5000.0 ~cost:100 ()) in  (* 5ms WAN latency *)

  (* DC-West internal *)
  let g = add_link g ~src:"dc-west-core-01" ~dst:"dc-west-spine-01"
    (make_link ~id:"dc-west-core-01--dc-west-spine-01"
       ~src_if:"GigabitEthernet0/2" ~dst_if:"Ethernet1"
       ~latency:30.0 ~cost:3 ()) in

  (* DC-East <-> Colo-NYSE *)
  let g = add_link g ~src:"dc-east-core-01" ~dst:"colo-nyse-edge-01"
    (make_link ~id:"dc-east-core-01--colo-nyse-edge-01"
       ~src_if:"GigabitEthernet0/4" ~dst_if:"ge-0/0/0"
       ~bw:10000 ~latency:200.0 ~cost:20 ()) in
  let g = add_link g ~src:"dc-east-core-02" ~dst:"colo-nyse-edge-02"
    (make_link ~id:"dc-east-core-02--colo-nyse-edge-02"
       ~src_if:"GigabitEthernet0/4" ~dst_if:"ge-0/0/0"
       ~bw:10000 ~latency:200.0 ~cost:20 ()) in

  (* Colo-NYSE internal + exchange peering *)
  let g = add_link g ~src:"colo-nyse-edge-01" ~dst:"colo-nyse-edge-02"
    (make_link ~id:"colo-nyse-edge-01--colo-nyse-edge-02"
       ~src_if:"ge-0/0/1" ~dst_if:"ge-0/0/1"
       ~latency:10.0 ~cost:1 ()) in
  let g = add_link g ~src:"colo-nyse-edge-01" ~dst:"nyse-exchange"
    (make_link ~id:"colo-nyse-edge-01--nyse-exchange"
       ~src_if:"ge-0/0/2" ~dst_if:"GigabitEthernet0/0"
       ~bw:10000 ~latency:5.0 ~cost:1 ()) in  (* Ultra low latency to exchange *)

  g

(* ============================================================
   Main
   ============================================================ *)

let () =
  Printf.printf "TradeNet Fabric — SDN Controller\n";
  Printf.printf "================================\n\n";

  let graph = build_demo_topology () in
  let devices = all_devices graph in
  let links = all_links graph in
  Printf.printf "Topology loaded: %d devices, %d links\n\n"
    (List.length devices) (List.length links);

  (* Demo: compute shortest path from DC-East to NYSE exchange *)
  Printf.printf "Computing optimal paths...\n";
  begin match Pathcomp.Path_engine.compute_path graph
    ~src:"dc-east-core-01" ~dst:"nyse-exchange"
    ~traffic_class:MarketData ~constraints:[] with
  | Some result ->
    Printf.printf "  DC-East → NYSE Exchange (Market Data):\n";
    Printf.printf "    Latency: %.1f μs\n" result.total_latency_us;
    Printf.printf "    Hops: %d\n" result.hop_count;
    Printf.printf "    Bottleneck BW: %d Mbps\n" result.bottleneck_bandwidth;
    Printf.printf "    Path: ";
    List.iter (fun (node, _link) ->
      Printf.printf "%s → " node
    ) result.path;
    Printf.printf "(destination)\n";
  | None ->
    Printf.printf "  No path found!\n"
  end;
  Printf.printf "\n";

  (* Demo: compute path from DC-West to NYSE (longer path) *)
  begin match Pathcomp.Path_engine.compute_path graph
    ~src:"dc-west-core-01" ~dst:"nyse-exchange"
    ~traffic_class:MarketData ~constraints:[] with
  | Some result ->
    Printf.printf "  DC-West → NYSE Exchange (Market Data):\n";
    Printf.printf "    Latency: %.1f μs\n" result.total_latency_us;
    Printf.printf "    Hops: %d\n" result.hop_count;
    Printf.printf "    Path: ";
    List.iter (fun (node, _link) ->
      Printf.printf "%s → " node
    ) result.path;
    Printf.printf "(destination)\n";
  | None ->
    Printf.printf "  No path found!\n"
  end;
  Printf.printf "\n";

  (* Initialize API and start server *)
  Api.Server.init graph;
  Printf.printf "Starting API server on port 9090...\n";
  Printf.printf "Endpoints:\n";
  Printf.printf "  GET  /api/health     — Health check\n";
  Printf.printf "  GET  /api/topology   — Full network graph\n";
  Printf.printf "  GET  /api/devices    — List all devices\n";
  Printf.printf "  GET  /api/links      — List all links with metrics\n";
  Printf.printf "  POST /api/path       — Compute optimal path\n";
  Printf.printf "  POST /api/link/state — Update link state (chaos)\n";
  Printf.printf "\n";
  Api.Server.start ~port:9090 ()
