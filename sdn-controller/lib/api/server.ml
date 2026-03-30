(* REST API Server
   ===============
   Exposes the SDN controller's state and path computation via HTTP.

   WHY Dream (for interview):
   Dream is a modern OCaml web framework — clean API, good performance,
   built on top of httpaf. We chose it over Cohttp because:
   - Simpler API for defining routes (less boilerplate)
   - Built-in middleware support (logging, CORS)
   - Active development and good documentation
   - Still lightweight — not a full "batteries included" framework

   The API serves two consumers:
   1. The React dashboard (real-time network visualization)
   2. External tools/scripts (chaos framework, benchmarks)
*)

open Topology

(** The controller state shared across API handlers.
    We use a mutable ref because the telemetry collector
    updates the graph continuously. The graph itself is
    immutable — we swap the ref atomically. *)
type controller_state = {
  mutable graph : Network_graph.t;
  mutable last_update : float;
}

let state = {
  graph = Network_graph.empty ();
  last_update = 0.0;
}

(** Initialize the controller with a network graph. *)
let init graph =
  state.graph <- graph;
  state.last_update <- Unix.gettimeofday ()

(** Update the graph (called by telemetry collector). *)
let update_graph graph =
  state.graph <- graph;
  state.last_update <- Unix.gettimeofday ()

(* ============================================================
   API Handlers
   ============================================================ *)

(** GET /api/topology — Return the full network graph as JSON.
    Used by the dashboard to render the topology map. *)
let handle_topology _req =
  let json = Network_graph.to_yojson state.graph in
  Dream.json (Yojson.Safe.to_string json)

(** GET /api/devices — List all network devices. *)
let handle_devices _req =
  let devices = Network_graph.all_devices state.graph in
  let json = `List (List.map Network_graph.device_to_yojson devices) in
  Dream.json (Yojson.Safe.to_string json)

(** GET /api/devices/:id — Get a specific device. *)
let handle_device req =
  let id = Dream.param req "id" in
  match Network_graph.find_device state.graph id with
  | Some device ->
    Dream.json (Yojson.Safe.to_string (Network_graph.device_to_yojson device))
  | None ->
    Dream.json ~status:`Not_Found
      (Yojson.Safe.to_string (`Assoc [("error", `String "Device not found")]))

(** GET /api/links — List all network links with current metrics. *)
let handle_links _req =
  let links = Network_graph.all_links state.graph in
  let json = `List (List.map (fun (src, dst, link) ->
    `Assoc [
      ("src", `String src);
      ("dst", `String dst);
      ("link", Network_graph.link_to_yojson link);
    ]
  ) links) in
  Dream.json (Yojson.Safe.to_string json)

(** POST /api/path — Compute optimal path between two devices.
    Request body: { "src": "...", "dst": "...", "traffic_class": "market_data" }
    Response: path details with latency, hop count, etc. *)
let handle_path req =
  let%lwt body = Dream.body req in
  let json = Yojson.Safe.from_string body in
  match json with
  | `Assoc assoc ->
    let src = List.assoc "src" assoc |> Yojson.Safe.Util.to_string in
    let dst = List.assoc "dst" assoc |> Yojson.Safe.Util.to_string in
    let traffic_class_str =
      List.assoc_opt "traffic_class" assoc
      |> Option.map Yojson.Safe.Util.to_string
      |> Option.value ~default:"market_data"
    in
    let traffic_class = match traffic_class_str with
      | "market_data" -> Pathcomp.Path_engine.MarketData
      | "trading" -> Pathcomp.Path_engine.Trading
      | "bulk_transfer" -> Pathcomp.Path_engine.BulkTransfer
      | "management" -> Pathcomp.Path_engine.Management
      | _ -> Pathcomp.Path_engine.MarketData
    in
    begin match Pathcomp.Path_engine.compute_path state.graph ~src ~dst
                  ~traffic_class ~constraints:[] with
    | Some result ->
      let path_json = `List (List.map (fun (node, link) ->
        `Assoc [
          ("node", `String node);
          ("link", Network_graph.link_to_yojson link);
        ]
      ) result.path) in
      let response = `Assoc [
        ("path", path_json);
        ("total_latency_us", `Float result.total_latency_us);
        ("total_cost", `Float result.total_cost);
        ("hop_count", `Int result.hop_count);
        ("bottleneck_bandwidth_mbps", `Int result.bottleneck_bandwidth);
      ] in
      Dream.json (Yojson.Safe.to_string response)
    | None ->
      Dream.json ~status:`Not_Found
        (Yojson.Safe.to_string
           (`Assoc [("error", `String "No path found")]))
    end
  | _ ->
    Dream.json ~status:`Bad_Request
      (Yojson.Safe.to_string
         (`Assoc [("error", `String "Invalid request body")]))

(** POST /api/link/state — Update a link's state (used by chaos framework).
    Request body: { "src": "...", "dst": "...", "state": "down" } *)
let handle_link_state req =
  let%lwt body = Dream.body req in
  let json = Yojson.Safe.from_string body in
  match json with
  | `Assoc assoc ->
    let src = List.assoc "src" assoc |> Yojson.Safe.Util.to_string in
    let dst = List.assoc "dst" assoc |> Yojson.Safe.Util.to_string in
    let state_str = List.assoc "state" assoc |> Yojson.Safe.Util.to_string in
    let link_state = match state_str with
      | "up" -> Network_graph.Up
      | "down" -> Network_graph.Down
      | "degraded" -> Network_graph.Degraded
      | _ -> Network_graph.Up
    in
    let new_graph = Network_graph.update_link_state state.graph ~src ~dst link_state in
    update_graph new_graph;
    Dream.json (Yojson.Safe.to_string (`Assoc [("status", `String "ok")]))
  | _ ->
    Dream.json ~status:`Bad_Request
      (Yojson.Safe.to_string
         (`Assoc [("error", `String "Invalid request body")]))

(** GET /api/health — Health check endpoint. *)
let handle_health _req =
  let response = `Assoc [
    ("status", `String "healthy");
    ("last_update", `Float state.last_update);
    ("device_count", `Int (List.length (Network_graph.all_devices state.graph)));
    ("link_count", `Int (List.length (Network_graph.all_links state.graph)));
  ] in
  Dream.json (Yojson.Safe.to_string response)

(* ============================================================
   Router — Define all API routes
   ============================================================ *)

let cors_middleware inner_handler req =
  let%lwt response = inner_handler req in
  Dream.set_header response "Access-Control-Allow-Origin" "*";
  Dream.set_header response "Access-Control-Allow-Methods" "GET, POST, OPTIONS";
  Dream.set_header response "Access-Control-Allow-Headers" "Content-Type";
  Lwt.return response

let routes =
  Dream.router [
    Dream.get "/api/health" handle_health;
    Dream.get "/api/topology" handle_topology;
    Dream.get "/api/devices" handle_devices;
    Dream.get "/api/devices/:id" handle_device;
    Dream.get "/api/links" handle_links;
    Dream.post "/api/path" handle_path;
    Dream.post "/api/link/state" handle_link_state;
  ]

(** Start the API server on the given port. *)
let start ?(port = 9090) () =
  Dream.run ~port
  @@ Dream.logger
  @@ cors_middleware
  @@ routes
