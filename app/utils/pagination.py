import base64
import json
from datetime import datetime


def encode_cursor(updated_at: datetime, object_id: str) -> str:
    raw = json.dumps({"updated_at": updated_at.isoformat(), "id": object_id})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> dict:
    decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
    return json.loads(decoded)
