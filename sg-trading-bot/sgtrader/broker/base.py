"""The Broker interface every execution adapter implements.

The engine only ever talks to this interface, so swapping the paper simulator
for the live IBKR connection changes nothing upstream.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Account, Fill, Instrument, Order


class Broker(ABC):
    @abstractmethod
    def connect(self) -> None:
        """Establish any connection needed. No-op for the simulator."""

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def get_account(self) -> Account:
        """Current cash + marked-to-market positions, in base currency."""

    @abstractmethod
    def get_price(self, instrument: Instrument) -> float:
        """Latest reference price for sizing/marking."""

    @abstractmethod
    def place_order(self, order: Order) -> Fill:
        """Submit an order and return the resulting fill."""

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.disconnect()
        return False
