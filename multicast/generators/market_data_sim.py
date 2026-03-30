"""
TradeNet Fabric — Market Data Feed Simulator
==============================================
Simulates multicast market data feeds from exchanges (NYSE, CME, NASDAQ)
to test the PIM-SM multicast distribution tree and measure jitter.

WHAT IS MARKET DATA (for interview):
Exchanges broadcast real-time price updates to all connected trading firms
via multicast. For example, NYSE sends every trade, quote, and order book
update on a set of multicast groups (239.x.x.x addresses). Every firm
that's plugged into NYSE receives this data simultaneously.

WHY MULTICAST (for interview):
If NYSE had to send individual unicast streams to every trading firm,
the exchange's uplink would be saturated. Multicast lets them send
ONE copy of the data, and the network replicates it to every subscriber.
This is managed by PIM-SM (Protocol Independent Multicast - Sparse Mode)
on the routers and IGMP (Internet Group Management Protocol) on the switches.

WHAT WE MEASURE:
1. Jitter — variance in inter-packet arrival time. For trading, consistent
   latency is almost as important as low latency. If market data normally
   arrives every 100μs but sometimes arrives after 500μs, that 400μs spike
   could cause your trading strategy to make decisions on stale data.
2. Packet loss — any lost market data packet means missed price updates.
3. Out-of-order packets — multicast over redundant paths can cause packets
   to arrive out of sequence.

FEED STRUCTURE:
Each exchange has multiple "channels" (multicast groups):
- NYSE: 239.1.1.1 (equities), 239.1.1.2 (options), 239.1.1.3 (bonds)
- CME: 239.1.2.1 (futures), 239.1.2.2 (options)
- NASDAQ: 239.1.3.1 (equities), 239.1.3.2 (options)
"""

import json
import socket
import struct
import time
import random
import signal
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.live import Live

console = Console()


@dataclass
class MarketDataMessage:
    """A single market data message (simulated)."""
    sequence_number: int
    timestamp_ns: int        # Nanosecond timestamp
    exchange: str            # NYSE, CME, NASDAQ
    symbol: str              # e.g., "AAPL", "ES", "QQQ"
    msg_type: str            # "trade", "quote", "order"
    price: float
    size: int
    channel: str             # Multicast group address


@dataclass
class FeedConfig:
    """Configuration for a simulated market data feed."""
    exchange: str
    channel: str             # Multicast group
    port: int
    symbols: List[str]
    msgs_per_second: int     # Message rate
    description: str


# Feed configurations matching our topology's multicast addressing
FEED_CONFIGS = [
    FeedConfig(
        exchange="NYSE",
        channel="239.1.1.1",
        port=30001,
        symbols=["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM"],
        msgs_per_second=10000,
        description="NYSE Equities - Top of Book",
    ),
    FeedConfig(
        exchange="NYSE",
        channel="239.1.1.2",
        port=30002,
        symbols=["AAPL", "MSFT", "SPY", "QQQ"],
        msgs_per_second=5000,
        description="NYSE Options - NBBO",
    ),
    FeedConfig(
        exchange="CME",
        channel="239.1.2.1",
        port=30003,
        symbols=["ES", "NQ", "YM", "RTY", "CL", "GC", "ZB", "ZN"],
        msgs_per_second=15000,
        description="CME Futures - Market Depth",
    ),
    FeedConfig(
        exchange="NASDAQ",
        channel="239.1.3.1",
        port=30004,
        symbols=["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD"],
        msgs_per_second=12000,
        description="NASDAQ Equities - Full Book",
    ),
]


class JitterAnalyzer:
    """Analyzes inter-packet jitter for market data feeds.

    WHY JITTER ANALYSIS (for interview):
    Low average latency is not enough — you need CONSISTENT latency.
    A feed with 100μs average but occasional 10ms spikes is worse than
    a feed with 200μs average and no spikes, because the spikes cause
    your trading system to make decisions on stale data.

    We measure:
    - Mean inter-packet gap
    - Standard deviation (jitter)
    - P99 inter-packet gap (worst 1% of packets)
    - Max inter-packet gap
    """

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.gaps: List[float] = []
        self.last_timestamp: Optional[float] = None
        self.total_packets = 0
        self.total_bytes = 0
        self.out_of_order = 0
        self.last_seq = -1

    def record_packet(self, timestamp: float, seq: int, size: int):
        """Record a received packet for jitter analysis."""
        self.total_packets += 1
        self.total_bytes += size

        if seq <= self.last_seq and self.last_seq >= 0:
            self.out_of_order += 1
        self.last_seq = max(self.last_seq, seq)

        if self.last_timestamp is not None:
            gap = (timestamp - self.last_timestamp) * 1_000_000  # Convert to μs
            self.gaps.append(gap)
            if len(self.gaps) > self.window_size:
                self.gaps.pop(0)

        self.last_timestamp = timestamp

    @property
    def mean_gap_us(self) -> float:
        if not self.gaps:
            return 0.0
        return sum(self.gaps) / len(self.gaps)

    @property
    def jitter_us(self) -> float:
        """Standard deviation of inter-packet gaps."""
        if len(self.gaps) < 2:
            return 0.0
        mean = self.mean_gap_us
        variance = sum((g - mean) ** 2 for g in self.gaps) / len(self.gaps)
        return variance ** 0.5

    @property
    def p99_gap_us(self) -> float:
        """99th percentile inter-packet gap."""
        if not self.gaps:
            return 0.0
        sorted_gaps = sorted(self.gaps)
        idx = int(len(sorted_gaps) * 0.99)
        return sorted_gaps[min(idx, len(sorted_gaps) - 1)]

    @property
    def max_gap_us(self) -> float:
        if not self.gaps:
            return 0.0
        return max(self.gaps)


class MarketDataSimulator:
    """Simulates multicast market data feeds."""

    def __init__(self):
        self.running = True
        self.analyzers: Dict[str, JitterAnalyzer] = {}
        self.sequence_numbers: Dict[str, int] = {}

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        self.running = False

    def generate_message(self, config: FeedConfig) -> MarketDataMessage:
        """Generate a realistic market data message."""
        if config.exchange not in self.sequence_numbers:
            self.sequence_numbers[config.exchange] = 0
        self.sequence_numbers[config.exchange] += 1

        symbol = random.choice(config.symbols)
        msg_type = random.choices(
            ["trade", "quote", "order"],
            weights=[0.2, 0.5, 0.3],  # Quotes are most common
        )[0]

        # Realistic price around $100-$500 with small random changes
        base_prices = {"AAPL": 185, "MSFT": 420, "GOOGL": 175, "AMZN": 185,
                       "META": 500, "NVDA": 900, "TSLA": 170, "JPM": 200,
                       "ES": 5200, "NQ": 18500, "YM": 39000, "RTY": 2050,
                       "CL": 78, "GC": 2300, "ZB": 118, "ZN": 110,
                       "SPY": 520, "QQQ": 450, "AMD": 170}
        base = base_prices.get(symbol, 100)
        price = base + random.gauss(0, base * 0.001)

        return MarketDataMessage(
            sequence_number=self.sequence_numbers[config.exchange],
            timestamp_ns=int(time.time_ns()),
            exchange=config.exchange,
            symbol=symbol,
            msg_type=msg_type,
            price=round(price, 2),
            size=random.randint(1, 1000) * 100,
            channel=config.channel,
        )

    def run_demo(self, duration_seconds: int = 10):
        """Run the simulator in demo mode (no actual multicast)."""
        console.print("[bold cyan]TradeNet Fabric — Market Data Simulator[/]")
        console.print("[bold cyan]=======================================[/]\n")

        for config in FEED_CONFIGS:
            self.analyzers[config.exchange] = JitterAnalyzer()
            console.print(f"  [dim]{config.description}: {config.channel}:{config.port} "
                          f"({config.msgs_per_second} msg/s)[/]")

        console.print(f"\n[bold]Running simulation for {duration_seconds} seconds...[/]\n")

        start = time.time()
        total_messages = 0

        while self.running and (time.time() - start) < duration_seconds:
            for config in FEED_CONFIGS:
                # Generate messages at configured rate
                batch_size = config.msgs_per_second // 100  # 100 batches per second
                for _ in range(batch_size):
                    msg = self.generate_message(config)
                    # Simulate receiving the message (with realistic jitter)
                    jitter_us = random.gauss(0, 5)  # 5μs jitter
                    recv_time = time.time() + jitter_us / 1_000_000
                    self.analyzers[config.exchange].record_packet(
                        recv_time, msg.sequence_number, 128
                    )
                    total_messages += 1

            time.sleep(0.01)  # 10ms batches

        elapsed = time.time() - start

        # Print results
        console.print(f"\n[bold]Results ({total_messages:,} messages in {elapsed:.1f}s)[/]\n")

        table = Table(title="Market Data Feed Jitter Analysis")
        table.add_column("Exchange", style="cyan")
        table.add_column("Packets")
        table.add_column("Mean Gap (μs)")
        table.add_column("Jitter (μs)", style="bold")
        table.add_column("P99 Gap (μs)")
        table.add_column("Max Gap (μs)")
        table.add_column("Out-of-Order")

        for config in FEED_CONFIGS:
            analyzer = self.analyzers[config.exchange]
            jitter_style = (
                "[green]" if analyzer.jitter_us < 20 else
                "[yellow]" if analyzer.jitter_us < 50 else
                "[red]"
            )
            table.add_row(
                f"{config.exchange} ({config.channel})",
                f"{analyzer.total_packets:,}",
                f"{analyzer.mean_gap_us:.1f}",
                f"{jitter_style}{analyzer.jitter_us:.1f}[/]",
                f"{analyzer.p99_gap_us:.1f}",
                f"{analyzer.max_gap_us:.1f}",
                str(analyzer.out_of_order),
            )

        console.print(table)

        # Verdict
        max_jitter = max(a.jitter_us for a in self.analyzers.values())
        if max_jitter < 20:
            console.print(f"\n[bold green]JITTER WITHIN TOLERANCE — max {max_jitter:.1f}μs[/]")
        else:
            console.print(f"\n[bold red]JITTER EXCEEDS TOLERANCE — max {max_jitter:.1f}μs[/]")


if __name__ == "__main__":
    sim = MarketDataSimulator()
    sim.run_demo(duration_seconds=5)
