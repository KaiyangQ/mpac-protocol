"""Message envelope for MPAC protocol."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import json
import uuid

from .models import Sender, Watermark


@dataclass
class MessageEnvelope:
    """MPAC message envelope."""
    protocol: str = "MPAC"
    version: str = "0.1.13"
    message_type: str = ""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    sender: Sender = field(default_factory=lambda: Sender("", "", ""))
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    payload: Dict[str, Any] = field(default_factory=dict)
    watermark: Optional[Watermark] = None
    coordinator_epoch: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        data = {
            "protocol": self.protocol,
            "version": self.version,
            "message_type": self.message_type,
            "message_id": self.message_id,
            "session_id": self.session_id,
            "sender": self.sender.to_dict(),
            "ts": self.ts,
            "payload": self.payload,
        }
        if self.watermark:
            data["watermark"] = self.watermark.to_dict()
        if self.coordinator_epoch is not None:
            data["coordinator_epoch"] = self.coordinator_epoch
        return data

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessageEnvelope":
        """Create from dict."""
        data_copy = data.copy()

        # Convert sender dict to Sender object
        if isinstance(data_copy.get('sender'), dict):
            data_copy['sender'] = Sender.from_dict(data_copy['sender'])

        # Convert watermark dict to Watermark object if present
        if data_copy.get('watermark') and isinstance(data_copy['watermark'], dict):
            data_copy['watermark'] = Watermark.from_dict(data_copy['watermark'])

        return cls(**data_copy)

    @classmethod
    def from_json(cls, json_str: str) -> "MessageEnvelope":
        """Create from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def create(
        cls,
        message_type: str,
        session_id: str,
        sender: Sender,
        payload: Dict[str, Any],
        watermark: Optional[Watermark] = None,
        coordinator_epoch: Optional[int] = None,
    ) -> "MessageEnvelope":
        """Factory method to create a message envelope."""
        return cls(
            protocol="MPAC",
            version="0.1.13",
            message_type=message_type,
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            sender=sender,
            ts=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            payload=payload,
            watermark=watermark,
            coordinator_epoch=coordinator_epoch,
        )
