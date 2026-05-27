"""Generate the TradeNet Fabric Interview Prep PDF — Light theme for readability."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, HRFlowable, Frame, PageTemplate,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ============================================================
# Colors — Clean light theme
# ============================================================
NAVY = HexColor("#0f172a")
DARK_GRAY = HexColor("#1e293b")
MID_GRAY = HexColor("#475569")
LIGHT_GRAY = HexColor("#94a3b8")
PALE_BG = HexColor("#f8fafc")
CARD_BG = HexColor("#f1f5f9")
BORDER_COLOR = HexColor("#e2e8f0")
BLUE = HexColor("#2563eb")
DARK_BLUE = HexColor("#1e40af")
GREEN = HexColor("#16a34a")
CYAN = HexColor("#0891b2")
PURPLE = HexColor("#7c3aed")
AMBER = HexColor("#d97706")
RED = HexColor("#dc2626")

# ============================================================
# Styles
# ============================================================
S_TITLE = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=32, textColor=NAVY, spaceAfter=2)
S_SUBTITLE = ParagraphStyle("subtitle", fontName="Helvetica", fontSize=12, textColor=MID_GRAY, spaceAfter=20)
S_SECTION = ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=20, textColor=DARK_BLUE, spaceBefore=24, spaceAfter=8)
S_QUESTION = ParagraphStyle("question", fontName="Helvetica-Bold", fontSize=12, textColor=BLUE, spaceBefore=16, spaceAfter=6)
S_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10, textColor=DARK_GRAY, leading=15, spaceAfter=5)
S_INDENT = ParagraphStyle("indent", fontName="Helvetica", fontSize=10, textColor=DARK_GRAY, leading=15, spaceAfter=3, leftIndent=16)
S_BOLD = ParagraphStyle("bold", fontName="Helvetica-Bold", fontSize=10, textColor=NAVY, leading=15, spaceAfter=3)
S_TIP = ParagraphStyle("tip", fontName="Helvetica-Oblique", fontSize=9.5, textColor=PURPLE, leading=14, spaceAfter=6, leftIndent=16, borderColor=PURPLE, borderWidth=0.5, borderPadding=5, borderRadius=3)
S_KEY = ParagraphStyle("key", fontName="Helvetica-Bold", fontSize=10, textColor=GREEN, leading=15, spaceAfter=4, leftIndent=16)
S_FOOTER = ParagraphStyle("footer", fontName="Helvetica", fontSize=7.5, textColor=LIGHT_GRAY, alignment=TA_CENTER)
S_TOC = ParagraphStyle("toc", fontName="Helvetica", fontSize=10, textColor=MID_GRAY, leading=16, leftIndent=16)


def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(LIGHT_GRAY)
    canvas.drawCentredString(letter[0] / 2, 28,
        f"TradeNet Fabric \u2014 Interview Prep Guide  |  Page {doc.page}")
    # Top accent line
    canvas.setStrokeColor(BLUE)
    canvas.setLineWidth(2)
    canvas.line(54, letter[1] - 36, letter[0] - 54, letter[1] - 36)
    canvas.restoreState()


def hr():
    return HRFlowable(width="100%", thickness=0.5, color=BORDER_COLOR, spaceBefore=6, spaceAfter=6)

def S(h=6):
    return Spacer(1, h)

def Q(t):
    return Paragraph(t, S_QUESTION)
def B(t):
    return Paragraph(t, S_BODY)
def BI(t):
    return Paragraph(t, S_INDENT)
def BB(t):
    return Paragraph(t, S_BOLD)
def KP(t):
    return Paragraph(t, S_KEY)
def IT(t):
    return Paragraph(t, S_TIP)
def SEC(t):
    return Paragraph(t, S_SECTION)


def build_pdf():
    outpath = "/Users/mo/Downloads/janestreet_project1/docs/interview-prep.pdf"
    doc = SimpleDocTemplate(
        outpath, pagesize=letter,
        topMargin=0.65 * inch, bottomMargin=0.55 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    template = PageTemplate(id="main", frames=frame, onPage=add_page_number)
    doc.addPageTemplates([template])

    story = []

    # ======================== TITLE PAGE ========================
    story.append(S(80))
    story.append(Paragraph("TradeNet Fabric", S_TITLE))
    story.append(Paragraph("Interview Prep Guide \u2014 Network Engineering", S_SUBTITLE))
    story.append(hr())
    story.append(S(8))
    story.append(B("A comprehensive Q&A guide covering networking fundamentals, OCaml programming, "
                    "systems infrastructure, and project-specific questions. Every concept explained from first principles \u2014 no prior networking knowledge assumed."))
    story.append(S(16))

    stats = [
        ["29 tests passing", "1.52ms p99 path comp", "1.98ms p99 failover"],
        ["8 QCheck properties", "3 chaos scenarios", "6 architecture decisions"],
        ["12 devices \u00b7 3 vendors", "4 security zones", "314 auto-gen firewall rules"],
    ]
    t = Table(stats, colWidths=[2.2 * inch, 2.2 * inch, 2.2 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CARD_BG),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK_BLUE),
        ("FONTNAME", (0, 0), (-1, -1), "Courier"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    story.append(t)
    story.append(S(24))

    story.append(BB("Contents"))
    for item in [
        "Section 1: Routing Protocols (Q1\u2013Q6)",
        "Section 2: OCaml & Programming (Q7\u2013Q9)",
        "Section 3: Systems & Infrastructure (Q10\u2013Q12)",
        "Section 4: Project-Specific Questions (Q13\u2013Q16)",
        "Section 5: Bonus Questions (Q17\u2013Q30)",
        "Quick Reference \u2014 Key Numbers",
    ]:
        story.append(Paragraph(item, S_TOC))

    story.append(PageBreak())

    # ======================== SECTION 1 ========================
    story.append(SEC("Section 1: Routing Protocols"))
    story.append(hr())

    story.append(Q("Q1. What happens at the packet level when an OSPF adjacency forms?"))
    story.append(B("<b>What OSPF is:</b> A program running on routers that figures out how to get data from A to B. It talks to neighboring routers and builds a complete map of the network \u2014 like Google Maps for your network."))
    story.append(B("<b>An adjacency</b> is a relationship between two directly connected routers. They go through a 7-step introduction:"))
    story.append(S(3))
    for step, desc in [
        ("Step 1 \u2014 Down:", "Router just booted. Knows nothing. Like moving into a new neighborhood."),
        ("Step 2 \u2014 Init:", "Sends a Hello packet to multicast address 224.0.0.5: 'I'm Router A, here's my ID, I'm in Area 1.'"),
        ("Step 3 \u2014 Two-Way:", "Neighbor replies with a Hello containing A's name. Both know communication works both ways. Like exchanging phone numbers."),
        ("Step 4 \u2014 ExStart:", "Negotiate who talks first (higher ID = master). Agree on message numbering."),
        ("Step 5 \u2014 Exchange:", "Swap tables of contents of their map databases (DBD packets). Not full details yet."),
        ("Step 6 \u2014 Loading:", "Each requests full details (LSAs) for anything it's missing."),
        ("Step 7 \u2014 Full:", "Both have identical maps. Each independently runs Dijkstra's algorithm to compute fastest routes."),
    ]:
        story.append(BB(step))
        story.append(BI(desc))
    story.append(IT("Interview tip: Default hello/dead timers are 10s/40s \u2014 too slow for trading. We use 1s/4s with BFD (300ms failure detection) \u2014 133x faster than defaults."))

    story.append(Q("Q2. Why does BGP use TCP while OSPF uses raw IP?"))
    story.append(B("<b>IP</b> = base layer. Says 'from X, to Y' but doesn't guarantee delivery. <b>TCP</b> = layer on top that adds reliability (handshake, ordering, retransmission). <b>Raw IP</b> = skip TCP, just fire and hope."))
    story.append(S(3))
    story.append(BB("OSPF uses raw IP because:"))
    story.append(BI("\u2022 Only talks to directly connected neighbors (one hop). Low loss risk."))
    story.append(BI("\u2022 Has its own acknowledgment system (LSAcks)."))
    story.append(BI("\u2022 Uses multicast for neighbor discovery \u2014 TCP can't do multicast."))
    story.append(BI("\u2022 Lower overhead \u2014 important when sending Hellos every 1 second."))
    story.append(BB("BGP uses TCP because:"))
    story.append(BI("\u2022 Peers can be many hops apart (DC-East to DC-West across the country)."))
    story.append(BI("\u2022 Updates can be huge (real internet: 1M+ routes). TCP handles large transfers."))
    story.append(BI("\u2022 Sessions last days/weeks. TCP built for long-lived connections."))
    story.append(IT("Interview tip: 'OSPF is like shouting to your neighbor. BGP is like mailing a package cross-country \u2014 you need a reliable postal service (TCP).'"))

    story.append(Q("Q3. Link-state vs distance-vector protocols?"))
    story.append(BB("Distance-vector (e.g., RIP):"))
    story.append(BI("Each router only knows what neighbors told it. Like road signs: 'NYC: 200 miles.' Slow convergence. Count-to-infinity problem \u2014 failures can take MINUTES to propagate."))
    story.append(BB("Link-state (e.g., OSPF \u2014 what we use):"))
    story.append(BI("Every router floods its link info to ALL routers. Everyone has the same complete map. Each runs Dijkstra independently. Like everyone having GPS. Convergence under 1 second."))
    story.append(KP("We chose OSPF because trading firms need sub-second failover. Distance-vector is unacceptable."))

    story.append(Q("Q4. How would you debug a routing loop?"))
    story.append(B("A <b>routing loop</b>: packets bounce between routers forever. Router A sends to B, B sends back to A, repeat infinitely."))
    story.append(BB("Step 1:"))
    story.append(BI("Confirm with traceroute \u2014 if same IPs repeat, you have a loop."))
    story.append(BB("Step 2:"))
    story.append(BI("Check routing tables on both routers. If each points to the other for the same destination \u2014 that's your loop."))
    story.append(BB("Step 3:"))
    story.append(BI("Identify which protocol wrote the bad entry (O=OSPF, B=BGP, S=static)."))
    story.append(BB("Step 4:"))
    story.append(BI("OSPF: Check if both have identical link-state databases. MTU mismatch is a common sneaky cause."))
    story.append(BI("BGP: Check next-hop reachability. BGP may install a route with unreachable next-hop."))
    story.append(BI("Redistribution: OSPF\u2192BGP\u2192OSPF feedback loops need prefix filters."))
    story.append(IT("Interview tip: Our QCheck tests verify 'no path visits the same node twice' across 1,600 random topologies \u2014 loops are mathematically impossible in our path computation."))

    story.append(Q("Q5. Explain the BGP path selection algorithm."))
    story.append(B("When a router knows about the SAME destination from multiple sources, BGP uses ordered tiebreakers. First difference wins:"))
    for num, name, desc in [
        ("1", "Highest Weight", "Local sticky note: 'always prefer this.' Only one router sees it."),
        ("2", "Highest Local Preference", "Shared across your org. THE main knob our SDN controller uses."),
        ("3", "Locally originated", "Prefer routes this router created itself."),
        ("4", "Shortest AS-Path", "Fewer hops through organizations = preferred. Weak hijack defense."),
        ("5", "Lowest Origin type", "IGP > EGP > Incomplete. Minor tiebreaker."),
        ("6", "Lowest MED", "Neighbor's suggestion: 'prefer this link to me.' SDN controller also uses this."),
        ("7", "eBGP over iBGP", "External routes preferred over internal."),
        ("8", "Lowest IGP metric", "'Hot-potato routing' \u2014 hand off at nearest exit."),
        ("9-10", "Oldest route, lowest Router ID", "Final tiebreakers for stability."),
    ]:
        story.append(BI(f"<b>{num}. {name}</b> \u2014 {desc}"))
    story.append(IT("Interview tip: 'Our SDN controller uses Local Preference (#2) and MED (#6) to dynamically steer traffic based on live latency \u2014 traditional networks set these once and forget.'"))

    story.append(Q("Q6. What is BFD and why is it critical for trading?"))
    story.append(B("<b>BFD (Bidirectional Forwarding Detection)</b> = tiny fast heartbeat. Two routers exchange 'I'm alive' every 100ms. 3 missed = 300ms = link declared dead."))
    story.append(BB("Without BFD:"))
    story.append(BI("Link fails \u2192 4s to detect (OSPF dead timer) \u2192 SPF runs \u2192 ~5s total."))
    story.append(BB("With BFD:"))
    story.append(BI("Link fails \u2192 300ms to detect \u2192 OSPF notified \u2192 SPF runs \u2192 ~500ms total."))
    story.append(KP("BFD is 13x faster than aggressive OSPF timers. 4 seconds of blackholed traffic = thousands of missed price updates = lost money."))

    story.append(PageBreak())

    # ======================== SECTION 2 ========================
    story.append(SEC("Section 2: OCaml & Programming"))
    story.append(hr())

    story.append(Q("Q7. Why is OCaml's type system beneficial for a network controller?"))
    story.append(B("A <b>type system</b> enforces rules about data. Python: errors at runtime (production). OCaml: errors caught by compiler before code runs (your laptop)."))
    story.append(BB("1. Exhaustive pattern matching:"))
    story.append(BI("link_state has Up, Down, Degraded. Forget to handle Degraded? Compiler REFUSES to build. Python would silently do nothing."))
    story.append(BB("2. Can't mix up different number types:"))
    story.append(BI("Latency (200.0) and utilization (0.45) are both numbers. OCaml can make them distinct types. Compiler catches if you pass the wrong one."))
    story.append(BB("3. Immutable data for safe concurrency:"))
    story.append(BI("Updating the graph creates a NEW graph. Telemetry collector and path engine work simultaneously without locks. No race conditions. This is why Jane Street chose OCaml."))
    story.append(IT("Interview tip: 'For a controller pushing routing changes to live routers, a missed case could blackhole traffic. OCaml prevents entire categories of these bugs at compile time.'"))

    story.append(Q("Q8. What is Dijkstra's algorithm?"))
    story.append(B("Finds the cheapest path from one point to all others in a weighted graph."))
    story.append(BB("Analogy \u2014 finding shortest route to the airport:"))
    story.append(BI("1. Start at home. Distance to self = 0. Everything else = infinity."))
    story.append(BI("2. Look at all places reachable directly. Record distances."))
    story.append(BI("3. Go to closest unvisited place. (Key: this IS the shortest path to it.)"))
    story.append(BI("4. From there, check neighbors. If going through you is shorter, update them."))
    story.append(BI("5. Repeat until destination reached."))
    story.append(BB("Our key design: parameterized weight function."))
    story.append(BI("Pass a FUNCTION defining 'cost.' Market data: cost = latency. Bulk transfer: cost = inverse bandwidth. Same algorithm, different objectives."))
    story.append(KP("Performance: 1.52ms p99 for our 12-node topology. O((V+E) log V) complexity."))

    story.append(Q("Q9. What are property-based tests (QCheck)?"))
    story.append(B("<b>Unit tests:</b> 'This specific input gives this specific output.' One scenario."))
    story.append(B("<b>Property tests:</b> 'For ANY connected graph, a path exists between any two nodes.' Computer generates hundreds of random inputs and checks."))
    story.append(BB("Our 8 properties:"))
    story.append(BI("1. Connected nodes always have a path"))
    story.append(BI("2. Shortest path is actually shortest (no cheaper alternative)"))
    story.append(BI("3. A\u2192B costs the same as B\u2192A"))
    story.append(BI("4. No path visits the same node twice (no loops)"))
    story.append(BI("5. After killing any link, surviving paths still loop-free"))
    story.append(BI("6. Making a link slower never makes path through it cheaper"))
    story.append(BI("7. JSON roundtrip preserves graph exactly"))
    story.append(BI("8. Market data path always has lowest latency"))
    story.append(IT("Interview tip: Jane Street uses property-based testing extensively. Our QCheck tests verify 8 invariants across 1,600 random topologies."))

    story.append(PageBreak())

    # ======================== SECTION 3 ========================
    story.append(SEC("Section 3: Systems & Infrastructure"))
    story.append(hr())

    story.append(Q("Q10. What is eBPF and why use it over sFlow/NetFlow?"))
    story.append(B("OS has two layers: <b>userspace</b> (normal programs, sandboxed) and <b>kernel</b> (core, manages hardware). Network packets handled by kernel."))
    story.append(B("<b>eBPF</b> runs a small verified program INSIDE the kernel. No copying packets out. BPF verifier proves safety before loading (no infinite loops, no null pointers)."))
    story.append(BB("sFlow:"))
    story.append(BI("Samples 1 in 1000 packets. Misses 99.9%. A 50\u00b5s jitter spike? Probably missed."))
    story.append(BB("NetFlow:"))
    story.append(BI("Aggregates into 60-second summaries. Way too slow. Averages away spikes."))
    story.append(BB("eBPF:"))
    story.append(BI("Every packet. Nanosecond timestamps. Custom logic. Minimal overhead. Trading-grade."))

    story.append(Q("Q11. What is RPKI and how does it prevent BGP hijacks?"))
    story.append(B("Every network has an <b>AS number</b> (license plate) and owns IP ranges. BGP has NO authentication \u2014 anyone can claim 'I can route to NYSE.'"))
    story.append(B("<b>RPKI</b> adds cryptographic proof. NYSE publishes a signed ROA: 'Only AS 11111 may announce 198.51.100.0/24.' Our routers check every announcement against these records."))
    story.append(BI("<b>VALID</b> \u2014 ROA exists, ASN matches. Accept."))
    story.append(BI("<b>INVALID</b> \u2014 ROA exists, ASN doesn't match. HIJACK. Reject."))
    story.append(BI("<b>NOT FOUND</b> \u2014 No ROA. Accept cautiously."))
    story.append(KP("We tested: AS99999 announced NYSE's prefix. RPKI caught it immediately, marked INVALID, generated alert."))

    story.append(Q("Q12. Route reflectors vs full iBGP mesh?"))
    story.append(B("<b>iBGP rule:</b> Can't re-advertise routes learned from one iBGP peer to another. Prevents loops but requires full mesh."))
    story.append(B("Full mesh: N routers = N*(N-1)/2 sessions. 4 routers = 6 sessions. 50 routers = 1,225. Doesn't scale."))
    story.append(B("<b>Route reflectors</b> are ALLOWED to re-advertise. Central mail room instead of everyone mailing everyone. We use TWO RRs for redundancy."))

    story.append(PageBreak())

    # ======================== SECTION 4 ========================
    story.append(SEC("Section 4: Project-Specific Questions"))
    story.append(hr())

    story.append(Q("Q13. Why both Ansible AND Nornir?"))
    story.append(BB("Ansible = recipe book (declarative):"))
    story.append(BI("'Every Cisco router should have this exact config.' Push templates to 24 devices."))
    story.append(BB("Nornir = doctor doing rounds (programmatic):"))
    story.append(BI("'Check each router's OSPF neighbors, compare to expected, alert if wrong.' Real Python logic."))
    story.append(B("Ansible's YAML logic is painful for complex conditionals. Nornir's Python is clean. Using both shows engineering taste."))

    story.append(Q("Q14. Why zone-based firewall instead of ACLs?"))
    story.append(B("<b>ACLs</b> are stateless \u2014 each packet judged independently. Allow outbound? You ALSO need separate inbound rule for return traffic. Miss it? Silently dropped."))
    story.append(B("<b>Zone-based</b> are stateful \u2014 track connections. Allow outbound, returns auto-permitted. Zones are architectural: 'trading talks to exchange' maps to business requirements."))
    story.append(KP("4 zones: Trading (90), Exchange (50), Management (100), Internet (0). Auto-generated 314 lines of Junos config from YAML."))

    story.append(Q("Q15. Walk through a link failure in your system."))
    story.append(BI("<b>0ms</b> \u2014 Fiber breaks."))
    story.append(BI("<b>100ms</b> \u2014 First missed BFD heartbeat."))
    story.append(BI("<b>200ms</b> \u2014 Second missed."))
    story.append(BI("<b>300ms</b> \u2014 Third missed. BFD declares link DEAD. Notifies OSPF."))
    story.append(BI("<b>310ms</b> \u2014 OSPF floods new LSA to all routers."))
    story.append(BI("<b>400ms</b> \u2014 All routers run Dijkstra. New routes computed."))
    story.append(BI("<b>500ms</b> \u2014 Traffic rerouted. Failover complete."))
    story.append(BI("<b>Meanwhile</b> \u2014 SDN controller detects, runs Dijkstra (1.52ms p99), pushes BGP changes."))
    story.append(KP("Total SDN failover: 1.98ms p99. Target 100ms. We're 50x under."))

    story.append(Q("Q16. Why EVE-NG over GNS3 or Containerlab?"))
    story.append(BI("<b>EVE-NG:</b> Web UI, clean multi-vendor support, industry standard for professional labbing."))
    story.append(BI("<b>GNS3:</b> Client-server model adds complexity. Multi-vendor clunkier."))
    story.append(BI("<b>Containerlab:</b> Modern but not all vendors have good container images."))
    story.append(BI("<b>UTM over VirtualBox:</b> Free, native Apple Silicon. VBox has poor M-series support."))

    story.append(PageBreak())

    # ======================== SECTION 5: BONUS ========================
    story.append(SEC("Section 5: Bonus Questions"))
    story.append(hr())

    story.append(Q("Q17. What is ARP and why does it matter?"))
    story.append(B("<b>ARP (Address Resolution Protocol)</b> translates IP addresses to MAC addresses. IP = mailing address. MAC = name on the mailbox. Your computer broadcasts 'Who has 10.1.0.1?' The device replies with its MAC. Result cached."))
    story.append(IT("ARP only works within one network segment. To reach another subnet, you ARP for your default gateway (router), not the final destination."))

    story.append(Q("Q18. TCP vs UDP?"))
    story.append(BB("TCP:"))
    story.append(BI("Reliable, ordered, connection-oriented. 3-way handshake. Every byte acknowledged. Like a phone call."))
    story.append(BB("UDP:"))
    story.append(BI("Unreliable, unordered, connectionless. Just fire packets. Like throwing a letter over a fence."))
    story.append(KP("Market data from exchanges is typically UDP multicast. Missing one packet is better than waiting for retransmission and getting stale data late."))

    story.append(Q("Q19. What is subnetting?"))
    story.append(B("IP = 32 bits. <b>Subnetting</b> divides into network portion + host portion. 10.1.0.0/24 = first 24 bits fixed (network), last 8 bits for hosts (256 addresses)."))
    story.append(BI("/32 for loopbacks (one address), /30 for point-to-point links (2 usable), /24 for server subnets (254 usable)."))
    story.append(BI("Our scheme: 10.{site}.{function}.{host} \u2014 predictable and debuggable."))

    story.append(Q("Q20. What are OSPF areas and why?"))
    story.append(B("<b>Areas</b> = groups of routers sharing detailed maps. Within your area, you know every street. Between areas, only major highways."))
    story.append(BI("\u2022 Limit blast radius: flap in Area 1 doesn't affect Area 2"))
    story.append(BI("\u2022 Reduce memory and CPU per router"))
    story.append(BI("\u2022 Our project: each site = own area (DC-East=0.0.0.1, Colo-NYSE=0.0.0.4)"))

    story.append(Q("Q21. What is a BGP community?"))
    story.append(B("A <b>tag</b> attached to a route \u2014 colored sticky note. Doesn't change the route, just labels it for policy decisions."))
    story.append(BI("Tag as 'learned-from-nyse' \u2192 write policy: 'prefer routes tagged learned-from-nyse.'"))
    story.append(BI("Tag as 'do-not-export' \u2192 prevent internal routes leaking externally."))
    story.append(IT("Communities scale BGP policy. Instead of rules per-prefix (thousands), tag at the edge, write rules per-community (handful)."))

    story.append(Q("Q22. Why use loopback interfaces for BGP?"))
    story.append(B("<b>Loopback</b> = virtual interface, always up as long as router runs. Physical interfaces die when a cable is cut."))
    story.append(B("BGP sessions on loopbacks survive individual link failures as long as ANY path exists between routers. OSPF ensures loopbacks are reachable via any available path."))

    story.append(Q("Q23. What is traffic engineering?"))
    story.append(B("Controlling which path traffic takes, rather than letting protocols decide alone. OSPF picks shortest by cost \u2014 but 'shortest' isn't always 'best' (maybe it's congested)."))
    story.append(BB("Our SDN controller:"))
    story.append(BI("1. Collects live metrics from all links"))
    story.append(BI("2. Runs Dijkstra with live weights (not static costs)"))
    story.append(BI("3. Adjusts BGP attributes to steer traffic when optimal path changes"))
    story.append(B("Traditional: set costs once, forget. Ours: continuously optimized. This IS the value of SDN."))

    story.append(Q("Q24. iBGP vs eBGP?"))
    story.append(BI("<b>eBGP</b>: Between DIFFERENT organizations. NYSE (AS 11111) to us (AS 65001). Different AS numbers."))
    story.append(BI("<b>iBGP</b>: WITHIN same organization. DC-East to DC-West. Same AS number."))
    story.append(BI("eBGP: peers 1 hop apart, modifies AS-path. iBGP: peers many hops apart (loopbacks), does NOT modify AS-path (hence full-mesh/RR requirement)."))

    story.append(Q("Q25. What is MTU and why problems?"))
    story.append(B("<b>MTU</b> = biggest packet size a link can carry. Standard: 1500 bytes. Jumbo: 9000 bytes."))
    story.append(B("If Router A sends 9000-byte packet but link MTU is 1500, packet is fragmented or dropped."))
    story.append(BI("<b>OSPF trap:</b> If two sides disagree on MTU, adjacency gets STUCK in ExStart. Most common OSPF troubleshooting issue."))
    story.append(BI("<b>Trading:</b> Jumbo frames reduce overhead, but ONE mismatched link degrades performance."))

    story.append(Q("Q26. NETCONF vs SSH/CLI for automation?"))
    story.append(B("SSH/CLI: type commands, parse text output with regex. Fragile \u2014 if output format changes, parser breaks."))
    story.append(B("<b>NETCONF</b>: structured XML, transactional (commit/rollback), candidate config (stage changes, review diff, then apply), vendor-neutral protocol."))
    story.append(IT("Our SDN controller would use NETCONF to push BGP changes \u2014 structured, transactional, rollback-safe."))

    story.append(Q("Q27. What is leaf-spine topology?"))
    story.append(B("Traditional 3-tier (core/distribution/access) creates bottlenecks. <b>Leaf-spine</b>: every leaf connects to EVERY spine. Always exactly 2 hops. Predictable latency, no bottleneck, easy to scale."))
    story.append(BI("Our project: DC-East and DC-West use Arista in leaf-spine. Cisco core connects to WAN."))

    story.append(Q("Q28. What does 'convergence' mean?"))
    story.append(B("All routers agreeing on the same routes after a change. Until complete, different routers have different views \u2014 packets may take unexpected paths or get dropped."))
    story.append(BI("OSPF: <1s with BFD. BGP: 5-30s. Our SDN controller: 1.98ms p99."))
    story.append(KP("During convergence, traffic may be blackholed. Shorter = fewer dropped packets = fewer missed market updates."))

    story.append(Q("Q29. Multicast vs unicast?"))
    story.append(BI("<b>Unicast:</b> One sender, one receiver. 1000 viewers = 1000 copies sent. Inefficient."))
    story.append(BI("<b>Multicast:</b> One sender, many receivers. ONE copy sent, network replicates to all subscribers."))
    story.append(B("NYSE sends ONE market data stream (239.1.1.1). Network copies to every trading firm. PIM-SM builds the distribution tree."))

    story.append(Q("Q30. If you could redesign one part, what would you change?"))
    story.append(B("(Tests self-awareness and engineering maturity.)"))
    story.append(BB("Suggested answer:"))
    story.append(BI("'I'd add gRPC streaming telemetry \u2014 push-based instead of pull-based. Right now the controller polls via REST. In production, devices should continuously stream metrics, reducing detection delay to near-zero.'"))
    story.append(BI("'I'd also explore OCaml 5's algebraic effects for async I/O instead of Lwt \u2014 newer, cleaner concurrency model. Shows awareness of OCaml ecosystem direction.'"))
    story.append(IT("This shows you understand the limitation, know the production solution, AND track OCaml's evolution. All strong signals."))

    story.append(PageBreak())

    # ======================== CHEAT SHEET ========================
    story.append(SEC("Quick Reference \u2014 Key Numbers"))
    story.append(hr())

    cheat = [
        ["Metric", "Value", "Context"],
        ["Path Computation P99", "1.52ms", "Target: 50ms (33x under)"],
        ["Failover P99", "1.98ms", "Target: 100ms (50x under)"],
        ["API Health P99", "0.94ms", "Target: 10ms"],
        ["Unit Tests", "21 passing", "Alcotest framework"],
        ["Property Tests", "8 properties", "1,600 random topologies"],
        ["Total Tests", "29 passing", "0 failures"],
        ["Devices", "12", "Cisco / Arista / Juniper"],
        ["Links", "12", "All up, live metrics"],
        ["Sites", "6", "3 DCs + 3 exchange colos"],
        ["Security Zones", "4", "Trading, Exchange, Mgmt, Internet"],
        ["Chaos Scenarios", "3", "All passing"],
        ["ADRs", "6", "Documented design decisions"],
        ["Firewall Rules", "314 lines", "Auto-generated from YAML"],
        ["RPKI Hijacks Blocked", "2", "AS99999 + AS88888 rejected"],
        ["BFD Detection", "300ms", "vs 40s default (133x faster)"],
        ["OSPF Hello/Dead", "1s / 4s", "vs 10s / 40s default"],
        ["BGP Timers", "10s / 30s", "vs 60s / 180s default"],
        ["Internal ASN", "65001", "All sites, route reflectors"],
    ]
    t = Table(cheat, colWidths=[2.1 * inch, 1.4 * inch, 3.1 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("BACKGROUND", (0, 1), (-1, -1), white),
        ("TEXTCOLOR", (0, 1), (0, -1), NAVY),
        ("TEXTCOLOR", (1, 1), (1, -1), BLUE),
        ("TEXTCOLOR", (2, 1), (2, -1), MID_GRAY),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTNAME", (1, 1), (1, -1), "Courier"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, PALE_BG]),
    ]))
    story.append(t)
    story.append(S(30))
    story.append(Paragraph("Good luck, Mo.", ParagraphStyle(
        "luck", fontName="Helvetica-Bold", fontSize=16, textColor=DARK_BLUE, alignment=TA_CENTER)))

    doc.build(story)
    print(f"PDF generated: {outpath}")


if __name__ == "__main__":
    build_pdf()
