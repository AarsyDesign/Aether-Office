"""Artifact Model and Storage for Aether Office Work Products."""

from __future__ import annotations
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, List, Dict
from events import EventBus, Event, EVENT_ARTIFACT_CREATED, EVENT_ARTIFACT_UPDATED

logger = logging.getLogger("aether.artifacts")

# Standard Artifact Types
ARTIFACT_DOCUMENT = "document"
ARTIFACT_CODE = "code"
ARTIFACT_DESIGN = "design"
ARTIFACT_RESEARCH = "research"
ARTIFACT_COPY = "copy"
ARTIFACT_REPORT = "report"
ARTIFACT_DATA = "data"
ARTIFACT_TEST_RESULT = "test_result"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Artifact:
    """Represents an immutable or versioned deliverable produced by an employee."""

    artifact_id: str
    task_id: str
    project_id: str
    type: str = ARTIFACT_DOCUMENT
    name: str = ""
    path: Optional[str] = None
    content: str = ""
    created_by: str = ""  # employee_id
    version: int = 1
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    def create_new_version(self, new_content: str, updated_by: str, path: Optional[str] = None) -> Artifact:
        """Create a new version of this artifact."""
        new_version = self.version + 1
        meta = dict(self.metadata)
        history = meta.get("version_history", [])
        history.append({
            "version": self.version,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "content_preview": self.content[:100] if self.content else "",
        })
        meta["version_history"] = history

        return Artifact(
            artifact_id=self.artifact_id,
            task_id=self.task_id,
            project_id=self.project_id,
            type=self.type,
            name=self.name,
            path=path or self.path,
            content=new_content,
            created_by=updated_by,
            version=new_version,
            metadata=meta,
            created_at=_now_iso(),
        )

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "type": self.type,
            "name": self.name,
            "path": self.path,
            "content": self.content,
            "created_by": self.created_by,
            "version": self.version,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Artifact:
        return cls(
            artifact_id=d.get("artifact_id") or str(uuid.uuid4()),
            task_id=d.get("task_id", ""),
            project_id=d.get("project_id", "project"),
            type=d.get("type", ARTIFACT_DOCUMENT),
            name=d.get("name", ""),
            path=d.get("path"),
            content=d.get("content", ""),
            created_by=d.get("created_by", ""),
            version=d.get("version", 1),
            metadata=dict(d.get("metadata", {})),
            created_at=d.get("created_at", _now_iso()),
        )


class ArtifactStore:
    """In-memory and DB-integrated registry for project artifacts."""

    def __init__(self, db: Optional[Any] = None, event_bus: Optional[EventBus] = None):
        self.db = db
        self.event_bus = event_bus
        self._artifacts: dict[str, Artifact] = {}

    def register_artifact(self, artifact: Artifact) -> Artifact:
        """Store an artifact and emit artifact events."""
        is_update = artifact.artifact_id in self._artifacts
        self._artifacts[artifact.artifact_id] = artifact

        if self.db and hasattr(self.db, "save_artifact"):
            self.db.save_artifact(
                artifact_id=artifact.artifact_id,
                task_id=artifact.task_id,
                project_id=artifact.project_id,
                type=artifact.type,
                name=artifact.name,
                path=artifact.path,
                content=artifact.content,
                created_by=artifact.created_by,
                version=artifact.version,
                metadata=artifact.metadata,
            )

        if self.event_bus:
            evt_type = EVENT_ARTIFACT_UPDATED if is_update else EVENT_ARTIFACT_CREATED
            self.event_bus.publish(
                Event(
                    event_type=evt_type,
                    project_id=artifact.project_id,
                    task_id=artifact.task_id,
                    agent_id=artifact.created_by,
                    payload={
                        "artifact_id": artifact.artifact_id,
                        "type": artifact.type,
                        "name": artifact.name,
                        "version": artifact.version,
                    },
                )
            )

        return artifact

    def save_artifact(
        self,
        project_id: str,
        name: str,
        artifact_type: str = ARTIFACT_DOCUMENT,
        content: Optional[str] = None,
        task_id: Optional[str] = None,
        created_by: Optional[str] = None,
        path: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Artifact:
        """Convenience method to construct and register an artifact in one step."""
        import uuid
        art = Artifact(
            artifact_id=f"art_{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            task_id=task_id or f"task_{uuid.uuid4().hex[:6]}",
            type=artifact_type,
            name=name,
            path=path,
            content=content,
            created_by=created_by or "system",
            metadata=metadata or {},
        )
        return self.register_artifact(art)

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """Fetch artifact from memory or DB."""
        if artifact_id in self._artifacts:
            return self._artifacts[artifact_id]
        if self.db and hasattr(self.db, "get_artifact"):
            data = self.db.get_artifact(artifact_id)
            if data:
                art = Artifact.from_dict(data)
                self._artifacts[art.artifact_id] = art
                return art
        return None

    def list_artifacts(self, project_id: Optional[str] = None, task_id: Optional[str] = None) -> list[Artifact]:
        """List artifacts matching filters."""
        if self.db and hasattr(self.db, "list_artifacts"):
            rows = self.db.list_artifacts(project_id=project_id, task_id=task_id)
            return [Artifact.from_dict(r) for r in rows]
        res = list(self._artifacts.values())
        if project_id:
            res = [a for a in res if a.project_id == project_id]
        if task_id:
            res = [a for a in res if a.task_id == task_id]
        return res
