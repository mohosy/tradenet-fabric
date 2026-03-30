(* Path Computation Engine
   =======================
   This module sits between the raw graph and the policy engine.
   It provides high-level routing decisions by combining graph algorithms
   with trading-network-specific constraints.

   KEY DESIGN DECISIONS (for interview):

   1. We separate path computation from the graph module because the graph
      is a general data structure, but path computation is domain-specific.
      The graph doesn't know about "trading traffic" vs "management traffic" —
      this module does.

   2. We define multiple weight functions for different traffic classes.
      A trading firm doesn't route all traffic the same way:
      - Market data needs minimum latency
      - Bulk transfers need maximum bandwidth
      - Management traffic just needs reachability

   3. We support constraints (avoid specific links, prefer specific sites)
      because real traffic engineering isn't just "shortest path" — it's
      "shortest path that also satisfies these business requirements."
*)

open Topology.Network_graph

(** Traffic class determines how we weight path computation.
    Different traffic has different optimization objectives. *)
type traffic_class =
  | MarketData    (** Optimize for minimum latency — every microsecond matters *)
  | Trading       (** Optimize for minimum latency + low jitter *)
  | BulkTransfer  (** Optimize for available bandwidth *)
  | Management    (** Optimize for reliability (avoid degraded links) *)

(** Constraints on path selection. *)
type path_constraint =
  | AvoidLink of string * string    (** Don't use the link between these two devices *)
  | AvoidSite of string             (** Don't route through this site *)
  | PreferSite of string            (** Prefer paths through this site (lower cost) *)
  | MaxLatency of float             (** Total path latency must be under this (microseconds) *)
  | MaxHops of int                  (** Maximum number of hops *)

(** Result of a path computation. *)
type path_result = {
  path : (string * link) list;    (** Ordered list of (device_id, link) pairs *)
  total_latency_us : float;       (** Sum of link latencies along the path *)
  total_cost : float;             (** Computed cost (depends on weight function used) *)
  hop_count : int;                (** Number of hops *)
  bottleneck_bandwidth : int;     (** Minimum bandwidth link on the path (Mbps) *)
}

(* ============================================================
   Weight Functions

   These define what "optimal" means for each traffic class.
   The SDN controller picks the right one based on what kind
   of traffic it's routing.

   WHY PARAMETERIZED WEIGHTS (for interview):
   Traditional routing (OSPF, BGP) uses static metrics — you
   set a cost on each link and it never changes. Our SDN controller
   uses LIVE metrics (actual latency, actual utilization), so the
   "best" path changes as network conditions change. This is the
   whole point of SDN — dynamic, data-driven routing decisions.
   ============================================================ *)

(** Weight function for market data: pure latency optimization.
    Every microsecond of latency is money in a trading firm. *)
let market_data_weight (link : link) : float =
  match link.state with
  | Down -> Float.infinity       (* Can't use down links *)
  | Degraded -> link.metrics.latency_us *. 2.0  (* Heavy penalty *)
  | Up -> link.metrics.latency_us

(** Weight function for trading traffic: latency + jitter penalty.
    Low jitter is almost as important as low latency for trading —
    consistent latency means predictable execution times. *)
let trading_weight (link : link) : float =
  match link.state with
  | Down -> Float.infinity
  | Degraded -> (link.metrics.latency_us +. link.metrics.jitter_us *. 3.0) *. 2.0
  | Up -> link.metrics.latency_us +. link.metrics.jitter_us *. 3.0

(** Weight function for bulk transfers: inverse bandwidth preference.
    We want to use the fattest pipes. Links with high utilization
    get a penalty to spread load. *)
let bulk_transfer_weight (link : link) : float =
  match link.state with
  | Down -> Float.infinity
  | Degraded -> Float.infinity   (* Don't put bulk traffic on degraded links *)
  | Up ->
    let bw = Float.of_int link.bandwidth_mbps in
    let available = bw *. (1.0 -. link.metrics.utilization) in
    if available <= 0.0 then Float.infinity
    else 1000.0 /. available  (* Inverse: more available BW = lower cost *)

(** Weight function for management traffic: prefer reliable links.
    We don't care about latency — we care about not dropping packets. *)
let management_weight (link : link) : float =
  match link.state with
  | Down -> Float.infinity
  | Degraded -> 1000.0           (* Heavy penalty but still usable *)
  | Up ->
    (* Base cost of 1.0 + penalty for packet loss *)
    1.0 +. link.metrics.packet_loss *. 100.0

(** Select the appropriate weight function for a traffic class. *)
let weight_for_class = function
  | MarketData -> market_data_weight
  | Trading -> trading_weight
  | BulkTransfer -> bulk_transfer_weight
  | Management -> management_weight

(* ============================================================
   Constrained Path Computation

   Real traffic engineering needs constraints. For example:
   - "Route market data from NYSE to DC-East, but avoid the
      DC-East-to-DC-West link because it's under maintenance"
   - "Route this traffic through DC-East, not DC-West"

   We implement constraints by modifying the weight function:
   links that violate constraints get infinite weight (= unusable).
   This is cleaner than modifying the graph itself.
   ============================================================ *)

(** Apply constraints to a weight function.
    Returns a new weight function that respects the constraints. *)
let apply_constraints (_graph : t) (constraints : path_constraint list) (base_weight : link -> float) : link -> float =
  fun link ->
    let base = base_weight link in
    if Float.is_infinite base then base  (* Already unusable *)
    else
      let violates = List.exists (fun constraint_ ->
        match constraint_ with
        | AvoidLink (src, dst) ->
          (* Check if this link connects the avoided pair.
             We need to check the link ID or endpoints. *)
          String.equal link.id (Printf.sprintf "%s--%s" src dst) ||
          String.equal link.id (Printf.sprintf "%s--%s" dst src)
        | AvoidSite site ->
          (* We can't check site from just the link — this constraint
             is better applied at the graph level. For now, we handle
             it in compute_path below. *)
          ignore site; false
        | PreferSite _site ->
          (* Preference is a bonus, not a violation *)
          false
        | MaxLatency _max ->
          (* Can't check total path latency per-link — checked post-computation *)
          false
        | MaxHops _max ->
          (* Can't check hop count per-link — checked post-computation *)
          false
      ) constraints in
      if violates then Float.infinity
      else base

(** Compute the optimal path between two devices for a given traffic class,
    subject to constraints. *)
let compute_path (graph : t) ~(src : string) ~(dst : string)
    ~(traffic_class : traffic_class) ~(constraints : path_constraint list)
  : path_result option =
  let base_weight = weight_for_class traffic_class in
  let weight = apply_constraints graph constraints base_weight in
  match shortest_path graph ~src ~dst ~weight with
  | None -> None  (* No path exists *)
  | Some (path, total_cost) ->
    let total_latency_us =
      List.fold_left (fun acc (_node, link) ->
        acc +. link.metrics.latency_us
      ) 0.0 path
    in
    let hop_count = List.length path in
    let bottleneck_bandwidth =
      List.fold_left (fun acc (_node, link) ->
        min acc link.bandwidth_mbps
      ) Int.max_int path
      |> (fun bw -> if bw = Int.max_int then 0 else bw)
    in
    let result = {
      path;
      total_latency_us;
      total_cost;
      hop_count;
      bottleneck_bandwidth;
    } in
    (* Check post-computation constraints *)
    let satisfies_constraints =
      List.for_all (fun constraint_ ->
        match constraint_ with
        | MaxLatency max -> result.total_latency_us <= max
        | MaxHops max -> result.hop_count <= max
        | AvoidSite site ->
          not (List.exists (fun (node_id, _link) ->
            match find_device graph node_id with
            | Some dev -> String.equal dev.site site
            | None -> false
          ) path)
        | _ -> true  (* Already handled in weight function *)
      ) constraints
    in
    if satisfies_constraints then Some result
    else None  (* Path found but violates constraints *)

(** Compute paths from a source to ALL destinations for a given traffic class.
    Returns a routing table: destination -> best path. *)
let compute_routing_table (graph : t) ~(src : string)
    ~(traffic_class : traffic_class)
  : (string * path_result) list =
  let weight = weight_for_class traffic_class in
  all_shortest_paths graph ~src ~weight
  |> List.map (fun (dst, path, total_cost) ->
    let total_latency_us =
      List.fold_left (fun acc (_node, link) ->
        acc +. link.metrics.latency_us
      ) 0.0 path
    in
    let hop_count = List.length path in
    let bottleneck_bandwidth =
      List.fold_left (fun acc (_node, link) ->
        min acc link.bandwidth_mbps
      ) Int.max_int path
      |> (fun bw -> if bw = Int.max_int then 0 else bw)
    in
    (dst, { path; total_latency_us; total_cost; hop_count; bottleneck_bandwidth })
  )
