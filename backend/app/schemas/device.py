"""Pydantic schema for `Device` -- see app/schemas/user.py for how this
validates a raw row dict."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.enums import DeviceStatus


class DeviceRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    device_identifier: str
    device_type: str | None
    manufacturer: str | None
    model: str | None
    operating_system: str | None
    os_version: str | None
    status: DeviceStatus
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime
