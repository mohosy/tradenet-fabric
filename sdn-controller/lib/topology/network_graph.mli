(** Network Graph — Models the trading firm's network topology as a weighted graph.

    This is the core data structure of the SDN controller. Every routing decision
    starts here: the topology graph represents all devices (nodes) and links (edges)
    with their current metrics (latency, utilization, packet loss).

    {b Why a graph?} Networks ARE graphs — routers are nodes, links are edges.
    Modeling them explicitly lets us run graph algorithms (Dijkstra, Bellman-Ford)
    to compute optimal paths, rather than relying on distributed routing protocols
    alone.

    {b Why OCaml?} The type system ensures we can't accidentally confuse a router
    with a switch, or a latency metric with a utilization metric. Pattern matching
    makes handling different device types and link states clean and exhaustive. *)

(** The type of network device. Each variant maps to a real role in the topology. *)
type device_role =
  | CoreRouter      (** Cisco IOSv — backbone/WAN interconnects *)
  | SpineSwitch     (** Arista vEOS — data center spine *)
  | LeafSwitch      (** Arista vEOS — data center leaf *)
  | EdgeRouter      (** Juniper vSRX — colo perimeter with firewall *)
  | TransitRouter   (** External transit provider (simulated) *)
  | ExchangeRouter  (** Exchange-side router (simulated NYSE/CME/NASDAQ) *)

(** A network device (node in the graph). *)
type device = {
  id : string;              (** Unique identifier, e.g., "dc-east-core-rtr-01" *)
  name : string;            (** Human-readable name *)
  role : device_role;       (** What role this device plays *)
  site : string;            (** Which site it belongs to *)
  loopback : string;        (** Loopback IP address (used for BGP peering) *)
  vendor : string;          (** "cisco", "arista", or "juniper" *)
  asn : int;                (** BGP AS number *)
}

(** Current state of a network link. *)
type link_state =
  | Up            (** Link is operational *)
  | Down          (** Link is down (failure or admin shutdown) *)
  | Degraded      (** Link is up but experiencing issues *)

(** Real-time metrics for a link, updated by the telemetry collector. *)
type link_metrics = {
  latency_us : float;       (** One-way latency in microseconds *)
  jitter_us : float;        (** Jitter (latency variance) in microseconds *)
  utilization : float;      (** Link utilization as a fraction [0.0, 1.0] *)
  packet_loss : float;      (** Packet loss rate as a fraction [0.0, 1.0] *)
  last_updated : float;     (** Unix timestamp of last metric update *)
}

(** A network link (edge in the graph). *)
type link = {
  id : string;              (** Unique link identifier *)
  src_interface : string;   (** Source interface name, e.g., "GigabitEthernet0/1" *)
  dst_interface : string;   (** Destination interface name *)
  bandwidth_mbps : int;     (** Link bandwidth in Mbps *)
  state : link_state;       (** Current operational state *)
  metrics : link_metrics;   (** Current real-time metrics *)
  ospf_cost : int;          (** OSPF cost assigned to this link *)
}

(** {1 Graph Construction} *)

(** The network graph type. Opaque — interact through the functions below. *)
type t

(** Create an empty network graph. *)
val empty : unit -> t

(** Add a device to the graph. Returns the updated graph.
    Raises [Invalid_argument] if a device with the same ID already exists. *)
val add_device : t -> device -> t

(** Add a link between two devices. Both devices must already exist.
    Raises [Not_found] if either device ID is unknown. *)
val add_link : t -> src:string -> dst:string -> link -> t

(** {1 Queries} *)

(** Look up a device by ID. Returns [None] if not found. *)
val find_device : t -> string -> device option

(** Look up a link between two devices. Returns [None] if no link exists. *)
val find_link : t -> src:string -> dst:string -> link option

(** Get all devices in the graph. *)
val all_devices : t -> device list

(** Get all links in the graph. *)
val all_links : t -> (string * string * link) list

(** Get all neighbors of a device (devices connected by an Up or Degraded link). *)
val neighbors : t -> string -> (string * link) list

(** Get all devices at a specific site. *)
val devices_at_site : t -> string -> device list

(** {1 Metric Updates} *)

(** Update the metrics for a specific link. Used by the telemetry collector
    to feed real-time data into the graph. *)
val update_metrics : t -> src:string -> dst:string -> link_metrics -> t

(** Update the state of a link (e.g., when chaos framework kills a link). *)
val update_link_state : t -> src:string -> dst:string -> link_state -> t

(** {1 Path Computation} *)

(** Compute the shortest path between two devices using Dijkstra's algorithm.

    The [weight] function determines what "shortest" means:
    - For minimum latency: use [fun link -> link.metrics.latency_us]
    - For minimum cost: use [fun link -> Float.of_int link.ospf_cost]
    - For composite: combine latency + utilization penalty

    Returns [None] if no path exists (network partition).
    Returns [Some (path, total_weight)] where [path] is the ordered list of
    (device_id, link) pairs from source to destination. *)
val shortest_path :
  t ->
  src:string ->
  dst:string ->
  weight:(link -> float) ->
  ((string * link) list * float) option

(** Compute all shortest paths from a source to every reachable device.
    Useful for building a full routing table. *)
val all_shortest_paths :
  t ->
  src:string ->
  weight:(link -> float) ->
  (string * (string * link) list * float) list

(** {1 Serialization} *)

(** Serialize a device to JSON. *)
val device_to_yojson : device -> Yojson.Safe.t

(** Serialize a link to JSON. *)
val link_to_yojson : link -> Yojson.Safe.t

(** Serialize the graph to JSON (for the REST API and dashboard). *)
val to_yojson : t -> Yojson.Safe.t

(** Deserialize a graph from JSON. *)
val of_yojson : Yojson.Safe.t -> (t, string) result
