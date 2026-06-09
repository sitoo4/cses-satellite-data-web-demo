from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4


class JobRegistry:
    def __init__(self) -> None:
        self._items: dict[str, dict] = {}

    def register_completed(self, *, kind: str, datasource: str, request_payload: dict, result: dict) -> dict:
        now = datetime.now(UTC).isoformat()
        job_id = f"{kind}:{datasource}:{uuid4().hex[:12]}"
        record = {
            "job_id": job_id,
            "status": "completed",
            "kind": kind,
            "datasource": datasource,
            "created_at": now,
            "finished_at": now,
            "request": deepcopy(request_payload),
            "result": deepcopy(result),
        }
        self._items[job_id] = record
        return deepcopy(record)

    def get(self, job_id: str) -> dict:
        if job_id not in self._items:
            raise KeyError(job_id)
        return deepcopy(self._items[job_id])
