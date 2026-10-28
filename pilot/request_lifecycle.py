"""Off-host, deterministic PT v2 cancellation lifecycle REFERENCE IMPLEMENTATION.

No HTTP endpoints, authentication tokens, Android integration or host workers
are installed here. The server MUST authenticate its caller and independently
verify/bind the ticket; caller-supplied session IDs are not authentication.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, RLock
from typing import Callable
import math
import time


@dataclass(frozen=True)
class TaskTicket:
    principal: str
    session_id: str
    task_id: str
    generation: int
    snapshot_id: str
    issued_at: float
    expires_at: float

    def __post_init__(self):
        if any(not isinstance(v, str) or not v.strip() or len(v) > 128
               for v in (self.principal, self.session_id, self.task_id,
                         self.snapshot_id)):
            raise ValueError("Missing or invalid ticket identity")
        if not isinstance(self.generation, int) or self.generation < 0:
            raise ValueError("Invalid generation")
        if not (math.isfinite(self.issued_at) and
                math.isfinite(self.expires_at) and
                self.issued_at < self.expires_at <= self.issued_at + 180):
            raise ValueError("Invalid bounded ticket lease")

    @property
    def key(self) -> tuple[str, str, int]:
        return (self.session_id, self.task_id, self.generation)


@dataclass
class _Record:
    ticket: TaskTicket
    status: str
    cancelled: Event = field(default_factory=Event)


class RemoteTaskRegistry:
    """One-process, locked cancellation tombstone and task-admission model.

    A production multi-worker implementation needs an atomic authenticated
    shared store; this in-process dictionary is NOT a server integration.
    """
    def __init__(self, *, max_active: int = 4, max_records: int = 1000,
                 delivery_grace_s: float = 10,
                 clock: Callable[[], float] = time.monotonic):
        if (not 1 <= max_active <= max_records or
                not 0 <= delivery_grace_s <= 120):
            raise ValueError("Invalid capacity bounds")
        self.max_active = max_active
        self.max_records = max_records
        self.delivery_grace_s = delivery_grace_s
        self.clock = clock
        self._lock = RLock()
        self._records: dict[tuple[str, str, int], _Record] = {}
        self._deny_new_until = 0.0

    def _authorise(self, ticket: TaskTicket, authenticated_principal: str):
        if ticket.principal != authenticated_principal:
            raise PermissionError("Task ownership mismatch")

    def _existing(self, ticket: TaskTicket) -> _Record | None:
        record = self._records.get(ticket.key)
        if record is not None and record.ticket != ticket:
            raise ValueError("Task identity already bound to different lease")
        return record

    def _expire(self, now: float):
        for key, rec in list(self._records.items()):
            if now >= rec.ticket.expires_at and rec.status == "RUNNING":
                rec.cancelled.set()
                rec.status = "STOPPING"
            if (rec.status in {"STOPPED", "COMPLETED"} and
                    now >= rec.ticket.expires_at + self.delivery_grace_s):
                del self._records[key]

    def register(self, ticket: TaskTicket,
                 authenticated_principal: str) -> str:
        """Before any worker starts; duplicate/late registration never runs."""
        self._authorise(ticket, authenticated_principal)
        with self._lock:
            now = self.clock()
            self._expire(now)
            if now < ticket.issued_at or now >= ticket.expires_at:
                return "REJECTED_EXPIRED"
            rec = self._existing(ticket)
            if rec is not None:
                if rec.status == "RUNNING":
                    return "DUPLICATE_RUNNING"
                return "REJECTED_CANCELLED" if rec.status in (
                    "STOPPING", "STOPPED") else "DUPLICATE_COMPLETED"
            if now < self._deny_new_until:
                return "RATE_LIMITED"
            if (sum(r.status in ("RUNNING", "STOPPING")
                    for r in self._records.values()) >= self.max_active or
                    len(self._records) >= self.max_records):
                return "RATE_LIMITED"
            self._records[ticket.key] = _Record(ticket, "RUNNING")
            return "RUNNING"

    def cancel(self, ticket: TaskTicket,
               authenticated_principal: str) -> str:
        """Idempotent, stores pre-registration tombstones until lease expiry."""
        self._authorise(ticket, authenticated_principal)
        with self._lock:
            now = self.clock()
            self._expire(now)
            rec = self._existing(ticket)
            if rec is not None:
                if rec.status == "RUNNING":
                    rec.cancelled.set()
                    rec.status = "STOPPING"
                return rec.status
            if now >= ticket.expires_at:
                return "REJECTED_EXPIRED"
            if len(self._records) >= self.max_records:
                # Fail CLOSED for ALL new work until this unseen task can
                # no longer be admitted. Never silently drop a tombstone.
                self._deny_new_until = max(self._deny_new_until,
                                           ticket.expires_at)
                return "STOPPING_CAPACITY_BLOCK"
            rec = _Record(ticket, "STOPPED")
            rec.cancelled.set()
            self._records[ticket.key] = rec
            return "STOPPED"

    def should_stop(self, ticket: TaskTicket,
                    authenticated_principal: str) -> bool:
        """Cheap cooperative worker check; missing/expired is fail-closed."""
        self._authorise(ticket, authenticated_principal)
        with self._lock:
            now = self.clock()
            self._expire(now)
            rec = self._existing(ticket)
            return (now >= ticket.expires_at or rec is None or
                    rec.status != "RUNNING" or rec.cancelled.is_set())

    def finish(self, ticket: TaskTicket,
               authenticated_principal: str) -> str:
        """A worker acknowledges STOPPED; never publish after cancellation."""
        self._authorise(ticket, authenticated_principal)
        with self._lock:
            self._expire(self.clock())
            rec = self._existing(ticket)
            if rec is None:
                return "REJECTED_EXPIRED"
            if rec.status == "RUNNING":
                rec.status = "COMPLETED"
            elif rec.status == "STOPPING":
                rec.status = "STOPPED"
            return rec.status

    def state(self, ticket: TaskTicket,
              authenticated_principal: str) -> str:
        self._authorise(ticket, authenticated_principal)
        with self._lock:
            self._expire(self.clock())
            rec = self._existing(ticket)
            return rec.status if rec else "UNKNOWN"


class ClientGenerationGate:
    """Foreground search and existing guidance have separate lifetimes."""
    def __init__(self, principal: str, session_id: str):
        self.principal = principal
        self.session_id = session_id
        self.highest_generation = -1
        self.foreground: TaskTicket | None = None
        self.guidance_id: str | None = None
        self.selected_itinerary_id: str | None = None

    def begin(self, ticket: TaskTicket):
        if (ticket.principal != self.principal or
                ticket.session_id != self.session_id):
            raise PermissionError("Wrong client session")
        if ticket.generation <= self.highest_generation:
            raise ValueError("Non-increasing client generation")
        self.highest_generation = ticket.generation
        self.foreground = ticket
        self.selected_itinerary_id = None

    def accepts(self, ticket: TaskTicket) -> bool:
        return ticket == self.foreground

    def cancel_foreground(self) -> TaskTicket | None:
        previous = self.foreground
        self.foreground = None
        return previous

    def commit_guidance(self, itinerary_id: str):
        if not itinerary_id:
            raise ValueError("Missing itinerary identity")
        self.guidance_id = itinerary_id

    def stop_guidance_explicitly(self):
        self.guidance_id = None

    def select_itinerary(self, ticket: TaskTicket, itinerary_id: str) -> bool:
        if not self.accepts(ticket) or not itinerary_id:
            return False
        if (self.selected_itinerary_id is not None and
                self.selected_itinerary_id != itinerary_id):
            return False
        self.selected_itinerary_id = itinerary_id
        return True

    def accepts_enrichment(self, ticket: TaskTicket,
                           itinerary_id: str) -> bool:
        return (self.accepts(ticket) and
                self.selected_itinerary_id == itinerary_id)


class SharedFetchSubscriptions:
    """Cancelling one subscriber never aborts another person's shared fetch."""
    def __init__(self):
        self._lock = RLock()
        self._subscriptions: dict[str, set[TaskTicket]] = {}

    def attach(self, fetch_key: str, ticket: TaskTicket):
        if not fetch_key:
            raise ValueError("Missing shared fetch key")
        with self._lock:
            self._subscriptions.setdefault(fetch_key, set()).add(ticket)

    def detach(self, fetch_key: str, ticket: TaskTicket) -> bool:
        """Return True only when no subscribers remain (caller may stop fetch)."""
        with self._lock:
            subscribers = self._subscriptions.get(fetch_key)
            if not subscribers or ticket not in subscribers:
                return False
            subscribers.remove(ticket)
            if subscribers:
                return False
            del self._subscriptions[fetch_key]
            return True

    def count(self, fetch_key: str) -> int:
        with self._lock:
            return len(self._subscriptions.get(fetch_key, ()))
