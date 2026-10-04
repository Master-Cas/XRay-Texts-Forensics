"""SQLite/WAL metadata store with append-only audit hashing."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from xray_text_forensics.core import Artifact, Case, DerivedView, DetectorRun, Evidence

from .models import AuditEvent, CaseBundle, Relationship

ModelT = TypeVar("ModelT", bound=BaseModel)

CASE_SCHEMA_VERSION = 1


class CaseStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self._migrate_schema()

    def __enter__(self) -> CaseStore:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def journal_mode(self) -> str:
        row = self.connection.execute("PRAGMA journal_mode").fetchone()
        assert row is not None
        return str(row[0]).casefold()

    def schema_version(self) -> int:
        row = self.connection.execute(
            "SELECT version FROM schema_meta WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise RuntimeError("Case schema version is not initialized")
        return int(row[0])

    def _migrate_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                version INTEGER NOT NULL
            )
            """
        )
        row = self.connection.execute(
            "SELECT version FROM schema_meta WHERE singleton=1"
        ).fetchone()
        if row is not None and int(row[0]) > CASE_SCHEMA_VERSION:
            raise RuntimeError(
                f"Case database schema {int(row[0])} is newer than "
                f"supported version {CASE_SCHEMA_VERSION}"
            )

        self._create_schema_v1()
        if row is None:
            self.connection.execute(
                "INSERT INTO schema_meta(singleton, version) VALUES (1, ?)",
                (CASE_SCHEMA_VERSION,),
            )
        elif int(row[0]) < CASE_SCHEMA_VERSION:
            raise RuntimeError(
                f"No migration path from case schema {int(row[0])} "
                f"to {CASE_SCHEMA_VERSION}"
            )
        self.connection.commit()

    def _create_schema_v1(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(case_id),
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS views (
                view_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(case_id),
                artifact_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(case_id),
                artifact_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
                evidence_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(case_id),
                artifact_id TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS relationships (
                relationship_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL REFERENCES cases(case_id),
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL REFERENCES cases(case_id),
                payload TEXT NOT NULL
            );
            """
        )

    def create_case(self, title: str) -> Case:
        case = Case(title=title)
        with self.connection:
            self.connection.execute(
                "INSERT INTO cases(case_id, payload) VALUES (?, ?)",
                (case.case_id, case.model_dump_json()),
            )
            self._append_audit(
                case.case_id,
                action="CASE_CREATED",
                object_type="case",
                object_id=case.case_id,
                details={"title": title},
            )
        return case

    def record_analysis(
        self,
        case_id: str,
        *,
        artifact: Artifact,
        views: list[DerivedView],
        run: DetectorRun,
        evidence: list[Evidence],
    ) -> None:
        self._require_case(case_id)
        if run.artifact_id != artifact.artifact_id:
            raise ValueError("DetectorRun artifact_id must match Artifact")
        if any(view.artifact_id != artifact.artifact_id for view in views):
            raise ValueError("All DerivedViews must belong to the Artifact")
        if any(item.artifact_id != artifact.artifact_id for item in evidence):
            raise ValueError("All Evidence must belong to the Artifact")

        with self.connection:
            self.connection.execute(
                "INSERT INTO artifacts(artifact_id, case_id, payload) VALUES (?, ?, ?)",
                (artifact.artifact_id, case_id, artifact.model_dump_json()),
            )
            self._append_audit(
                case_id,
                action="ARTIFACT_RECORDED",
                object_type="artifact",
                object_id=artifact.artifact_id,
                details={"sha256": artifact.sha256},
            )

            for view in views:
                self.connection.execute(
                    "INSERT INTO views(view_id, case_id, artifact_id, payload) VALUES (?, ?, ?, ?)",
                    (view.view_id, case_id, artifact.artifact_id, view.model_dump_json()),
                )
                self._append_audit(
                    case_id,
                    action="VIEW_RECORDED",
                    object_type="view",
                    object_id=view.view_id,
                    details={
                        "artifact_id": artifact.artifact_id,
                        "kind": view.kind.value,
                    },
                )

            self.connection.execute(
                "INSERT INTO runs(run_id, case_id, artifact_id, payload) VALUES (?, ?, ?, ?)",
                (run.run_id, case_id, artifact.artifact_id, run.model_dump_json()),
            )
            self._append_audit(
                case_id,
                action="DETECTOR_RUN_RECORDED",
                object_type="detector_run",
                object_id=run.run_id,
                details={
                    "artifact_id": artifact.artifact_id,
                    "detector_id": run.detector_id,
                    "detector_version": run.detector_version,
                },
            )

            for item in evidence:
                self.connection.execute(
                    "INSERT INTO evidence(evidence_id, case_id, artifact_id, payload) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        item.evidence_id,
                        case_id,
                        artifact.artifact_id,
                        item.model_dump_json(),
                    ),
                )
                self._append_audit(
                    case_id,
                    action="EVIDENCE_RECORDED",
                    object_type="evidence",
                    object_id=item.evidence_id,
                    details={
                        "artifact_id": artifact.artifact_id,
                        "family": item.family.value,
                        "status": item.status.value,
                        "detector_id": item.detector_id,
                    },
                )

    def add_relationship(
        self,
        case_id: str,
        *,
        subject_id: str,
        predicate: str,
        object_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> Relationship:
        self._require_case(case_id)
        if not self._object_exists(case_id, subject_id):
            raise ValueError(f"Unknown relationship subject: {subject_id}")
        if not self._object_exists(case_id, object_id):
            raise ValueError(f"Unknown relationship object: {object_id}")

        relationship = Relationship(
            case_id=case_id,
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            metadata=metadata or {},
        )
        with self.connection:
            self.connection.execute(
                "INSERT INTO relationships(relationship_id, case_id, payload) VALUES (?, ?, ?)",
                (
                    relationship.relationship_id,
                    case_id,
                    relationship.model_dump_json(),
                ),
            )
            self._append_audit(
                case_id,
                action="RELATIONSHIP_RECORDED",
                object_type="relationship",
                object_id=relationship.relationship_id,
                details={
                    "subject_id": subject_id,
                    "predicate": predicate,
                    "object_id": object_id,
                },
            )
        return relationship

    def fetch_bundle(self, case_id: str) -> CaseBundle:
        self._require_case(case_id)
        case_row = self.connection.execute(
            "SELECT payload FROM cases WHERE case_id=?",
            (case_id,),
        ).fetchone()
        assert case_row is not None

        artifacts = self._load_models(
            "SELECT payload FROM artifacts WHERE case_id=? ORDER BY rowid",
            case_id,
            Artifact,
        )
        views = self._load_models(
            "SELECT payload FROM views WHERE case_id=? ORDER BY rowid",
            case_id,
            DerivedView,
        )
        runs = self._load_models(
            "SELECT payload FROM runs WHERE case_id=? ORDER BY rowid",
            case_id,
            DetectorRun,
        )
        evidence = self._load_models(
            "SELECT payload FROM evidence WHERE case_id=? ORDER BY rowid",
            case_id,
            Evidence,
        )
        relationships = self._load_models(
            "SELECT payload FROM relationships WHERE case_id=? ORDER BY rowid",
            case_id,
            Relationship,
        )
        audit_events = self._load_models(
            "SELECT payload FROM audit_events WHERE case_id=? ORDER BY seq",
            case_id,
            AuditEvent,
        )

        case = Case.model_validate_json(case_row[0]).model_copy(
            update={
                "artifact_ids": [item.artifact_id for item in artifacts],
                "detector_run_ids": [item.run_id for item in runs],
                "evidence_ids": [item.evidence_id for item in evidence],
            }
        )
        return CaseBundle(
            case=case,
            artifacts=artifacts,
            views=views,
            runs=runs,
            evidence=evidence,
            relationships=relationships,
            audit_events=audit_events,
            audit_verified=self.verify_audit(case_id),
        )

    def verify_audit(self, case_id: str) -> bool:
        events = self._load_models(
            "SELECT payload FROM audit_events WHERE case_id=? ORDER BY seq",
            case_id,
            AuditEvent,
        )
        previous: str | None = None
        for event in events:
            if event.previous_hash != previous:
                return False
            if self._event_hash(event) != event.event_hash:
                return False
            previous = event.event_hash
        return bool(events)

    def _append_audit(
        self,
        case_id: str,
        *,
        action: str,
        object_type: str,
        object_id: str,
        details: dict[str, Any],
    ) -> AuditEvent:
        row = self.connection.execute(
            "SELECT payload FROM audit_events WHERE case_id=? ORDER BY seq DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        previous_hash = AuditEvent.model_validate_json(row[0]).event_hash if row else None

        seed = AuditEvent(
            case_id=case_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            details=details,
            previous_hash=previous_hash,
            event_hash="pending",
        )
        event = seed.model_copy(update={"event_hash": self._event_hash(seed)})
        self.connection.execute(
            "INSERT INTO audit_events(case_id, payload) VALUES (?, ?)",
            (case_id, event.model_dump_json()),
        )
        return event

    @staticmethod
    def _event_hash(event: AuditEvent) -> str:
        payload = event.model_dump(mode="json")
        payload.pop("event_hash", None)
        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _require_case(self, case_id: str) -> None:
        row = self.connection.execute(
            "SELECT 1 FROM cases WHERE case_id=?",
            (case_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown case: {case_id}")

    def _object_exists(self, case_id: str, object_id: str) -> bool:
        if object_id == case_id:
            return True
        for table, column in (
            ("artifacts", "artifact_id"),
            ("views", "view_id"),
            ("runs", "run_id"),
            ("evidence", "evidence_id"),
        ):
            row = self.connection.execute(
                f"SELECT 1 FROM {table} WHERE case_id=? AND {column}=?",
                (case_id, object_id),
            ).fetchone()
            if row is not None:
                return True
        return False

    def _load_models(
        self,
        query: str,
        case_id: str,
        model: type[ModelT],
    ) -> list[ModelT]:
        rows = self.connection.execute(query, (case_id,)).fetchall()
        return [model.model_validate_json(row[0]) for row in rows]
