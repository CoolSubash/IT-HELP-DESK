"""
Generic pagination envelope, used as `response_model=Page[TicketRead]` etc.

Ticket/message lists can grow without bound in a real deployment, so every
list endpoint takes `limit`/`offset` query params instead of always
returning everything. `total` is included so a UI can render "showing 1-20
of 143" and build page controls without a second request.
"""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
