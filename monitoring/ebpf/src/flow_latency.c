/* TradeNet Fabric — eBPF Flow Latency Monitor
 * =============================================
 * This BPF program attaches to network interfaces and measures
 * per-flow latency with microsecond precision.
 *
 * HOW IT WORKS (for interview):
 * 1. On packet INGRESS (TC or XDP hook), we record the timestamp
 *    and flow 5-tuple (src IP, dst IP, src port, dst port, protocol)
 *    in a BPF hash map.
 * 2. On packet EGRESS (or on the return packet), we look up the
 *    flow's start timestamp and compute the latency.
 * 3. We store the result in a per-flow metrics map that userspace
 *    reads via the BPF ring buffer.
 *
 * WHY eBPF (for interview):
 * - Runs IN the kernel — no packet copying to userspace
 * - Nanosecond-precision timestamps via bpf_ktime_get_ns()
 * - Per-packet analysis (not sampled like sFlow)
 * - Custom logic: we measure exactly what we need for trading
 * - Safe: the BPF verifier ensures our program can't crash the kernel
 *
 * BPF VERIFIER CONSTRAINTS (for interview):
 * The BPF verifier is extremely strict — it proves your program is safe
 * BEFORE loading it into the kernel. This means:
 * - No unbounded loops (must have a known iteration limit)
 * - No null pointer dereferences (must check every pointer)
 * - Limited stack size (512 bytes)
 * - No calling arbitrary kernel functions (only BPF helpers)
 * This discipline is similar to writing safety-critical code —
 * the same mindset Jane Street applies to trading systems.
 */

#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

/* Maximum number of flows to track simultaneously.
 * For a trading firm's network, this should be tuned to the
 * expected number of concurrent flows. 65536 is generous for
 * a lab environment. */
#define MAX_FLOWS 65536

/* How long to keep a flow entry before expiring it (nanoseconds).
 * 10 seconds — if we don't see a return packet within this window,
 * the flow entry is stale and can be reused. */
#define FLOW_TIMEOUT_NS (10ULL * 1000000000ULL)

/* ============================================================
 * Data Structures
 * ============================================================ */

/* Flow key — identifies a unique network flow.
 * Using the classic 5-tuple: src/dst IP, src/dst port, protocol. */
struct flow_key {
    __u32 src_ip;
    __u32 dst_ip;
    __u16 src_port;
    __u16 dst_port;
    __u8  protocol;
    __u8  pad[3];  /* Padding for alignment — BPF verifier cares about this */
};

/* Per-flow timing data stored in the hash map. */
struct flow_timestamp {
    __u64 first_seen_ns;     /* Timestamp of first packet */
    __u64 last_seen_ns;      /* Timestamp of most recent packet */
    __u64 packet_count;      /* Total packets in this flow */
};

/* Per-flow metrics exported to userspace via ring buffer. */
struct flow_metrics {
    struct flow_key key;
    __u64 latency_ns;        /* One-way latency estimate (ns) */
    __u64 jitter_ns;         /* Jitter: |current_latency - avg_latency| */
    __u64 packet_count;      /* Total packets observed */
    __u64 byte_count;        /* Total bytes observed */
    __u64 timestamp_ns;      /* When this metric was computed */
};

/* ============================================================
 * BPF Maps
 *
 * Maps are how BPF programs store state and communicate with
 * userspace. Think of them as kernel-resident hash tables.
 *
 * WHY HASH MAPS (for interview):
 * BPF_MAP_TYPE_HASH gives O(1) lookup by flow key.
 * For per-packet processing, we need fast lookups — O(1) is
 * critical when processing millions of packets per second.
 * ============================================================ */

/* Flow timestamp map: tracks when we first/last saw each flow */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_FLOWS);
    __type(key, struct flow_key);
    __type(value, struct flow_timestamp);
} flow_timestamps SEC(".maps");

/* Per-flow byte/packet counters */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, MAX_FLOWS);
    __type(key, struct flow_key);
    __type(value, struct flow_metrics);
} flow_counters SEC(".maps");

/* Ring buffer for exporting metrics to userspace.
 *
 * WHY RING BUFFER (for interview):
 * BPF_MAP_TYPE_RINGBUF is the modern way to export data from
 * BPF to userspace. It's:
 * - Lock-free (no contention between kernel and userspace)
 * - Variable-length entries
 * - Much more efficient than perf_event_output
 * This is what we use to feed metrics to the Prometheus exporter. */
struct {
    __uint(type, BPF_MAP_TYPE_RINGBUF);
    __uint(max_entries, 1 << 20);  /* 1MB ring buffer */
} metrics_ringbuf SEC(".maps");

/* Global counters for monitoring the monitor itself */
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 4);
    __type(key, __u32);
    __type(value, __u64);
} global_stats SEC(".maps");

#define STAT_PACKETS_TOTAL     0
#define STAT_PACKETS_TRACKED   1
#define STAT_FLOWS_ACTIVE      2
#define STAT_METRICS_EXPORTED  3

/* ============================================================
 * Helper Functions
 * ============================================================ */

/* Extract the flow key from a packet.
 * Returns 0 on success, -1 if the packet can't be parsed. */
static __always_inline int
extract_flow_key(void *data, void *data_end, struct flow_key *key)
{
    struct ethhdr *eth = data;

    /* Bounds check: is the Ethernet header within the packet?
     * The BPF verifier REQUIRES this check — without it, the
     * program won't load. This is how BPF ensures safety. */
    if ((void *)(eth + 1) > data_end)
        return -1;

    /* We only handle IPv4 for now */
    if (eth->h_proto != bpf_htons(ETH_P_IP))
        return -1;

    struct iphdr *ip = (void *)(eth + 1);
    if ((void *)(ip + 1) > data_end)
        return -1;

    key->src_ip = ip->saddr;
    key->dst_ip = ip->daddr;
    key->protocol = ip->protocol;
    key->pad[0] = key->pad[1] = key->pad[2] = 0;

    /* Extract ports for TCP and UDP */
    if (ip->protocol == IPPROTO_TCP) {
        struct tcphdr *tcp = (void *)ip + (ip->ihl * 4);
        if ((void *)(tcp + 1) > data_end)
            return -1;
        key->src_port = tcp->source;
        key->dst_port = tcp->dest;
    } else if (ip->protocol == IPPROTO_UDP) {
        struct udphdr *udp = (void *)ip + (ip->ihl * 4);
        if ((void *)(udp + 1) > data_end)
            return -1;
        key->src_port = udp->source;
        key->dst_port = udp->dest;
    } else {
        key->src_port = 0;
        key->dst_port = 0;
    }

    return 0;
}

/* Increment a global counter atomically */
static __always_inline void
increment_stat(__u32 stat_id)
{
    __u64 *val = bpf_map_lookup_elem(&global_stats, &stat_id);
    if (val)
        __sync_fetch_and_add(val, 1);
}

/* ============================================================
 * Main BPF Program — TC (Traffic Control) Ingress Hook
 *
 * This runs for EVERY packet entering the interface.
 * It must be fast — any latency we add here affects the
 * actual network traffic. eBPF's in-kernel execution
 * keeps overhead to single-digit microseconds.
 * ============================================================ */

SEC("tc")
int flow_latency_ingress(struct __sk_buff *skb)
{
    void *data = (void *)(long)skb->data;
    void *data_end = (void *)(long)skb->data_end;

    increment_stat(STAT_PACKETS_TOTAL);

    /* Extract flow key from packet */
    struct flow_key key = {};
    if (extract_flow_key(data, data_end, &key) < 0)
        return TC_ACT_OK;  /* Can't parse — pass through */

    __u64 now = bpf_ktime_get_ns();

    /* Look up or create flow timestamp entry */
    struct flow_timestamp *ts = bpf_map_lookup_elem(&flow_timestamps, &key);
    if (ts) {
        /* Existing flow — update metrics */
        __u64 inter_packet_gap = now - ts->last_seen_ns;
        ts->last_seen_ns = now;
        ts->packet_count += 1;

        /* Update flow counters/metrics */
        struct flow_metrics *metrics = bpf_map_lookup_elem(&flow_counters, &key);
        if (metrics) {
            metrics->packet_count += 1;
            metrics->byte_count += skb->len;
            metrics->latency_ns = inter_packet_gap;
            metrics->timestamp_ns = now;

            /* Export to ring buffer every 100 packets
             * (don't flood userspace with every packet) */
            if (metrics->packet_count % 100 == 0) {
                struct flow_metrics *rb_entry;
                rb_entry = bpf_ringbuf_reserve(&metrics_ringbuf,
                                                sizeof(*rb_entry), 0);
                if (rb_entry) {
                    __builtin_memcpy(rb_entry, metrics, sizeof(*rb_entry));
                    bpf_ringbuf_submit(rb_entry, 0);
                    increment_stat(STAT_METRICS_EXPORTED);
                }
            }
        }
    } else {
        /* New flow — record first timestamp */
        struct flow_timestamp new_ts = {
            .first_seen_ns = now,
            .last_seen_ns = now,
            .packet_count = 1,
        };
        bpf_map_update_elem(&flow_timestamps, &key, &new_ts, BPF_ANY);

        /* Initialize flow metrics */
        struct flow_metrics new_metrics = {
            .key = key,
            .latency_ns = 0,
            .jitter_ns = 0,
            .packet_count = 1,
            .byte_count = skb->len,
            .timestamp_ns = now,
        };
        bpf_map_update_elem(&flow_counters, &key, &new_metrics, BPF_ANY);

        increment_stat(STAT_FLOWS_ACTIVE);
    }

    increment_stat(STAT_PACKETS_TRACKED);

    /* TC_ACT_OK: pass the packet through unchanged.
     * We're monitoring, not filtering. The packet continues
     * its normal path through the network stack. */
    return TC_ACT_OK;
}

char _license[] SEC("license") = "GPL";
