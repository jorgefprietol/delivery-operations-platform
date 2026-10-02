import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4


def now():
    return datetime.now(UTC).isoformat()


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS releases (
                    id TEXT PRIMARY KEY, environment TEXT NOT NULL,
                    commit_sha TEXT NOT NULL, image_digest TEXT NOT NULL,
                    committed_at TEXT NOT NULL, evidence_url TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'candidate', version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, approved_at TEXT, deployed_at TEXT,
                    failed_at TEXT, recovered_at TEXT, previous_id TEXT,
                    UNIQUE(environment, image_digest)
                );
                CREATE TABLE IF NOT EXISTS active (
                    environment TEXT PRIMARY KEY, release_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, release_id TEXT NOT NULL,
                    action TEXT NOT NULL, actor TEXT NOT NULL, timestamp TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def row(db, release_id):
        item = db.execute("SELECT * FROM releases WHERE id = ?", (release_id,)).fetchone()
        if item is None:
            raise NotFound("Release does not exist")
        return dict(item)

    @staticmethod
    def event(db, release_id, action, actor, timestamp):
        db.execute(
            "INSERT INTO events(release_id, action, actor, timestamp) VALUES (?, ?, ?, ?)",
            (release_id, action, actor, timestamp),
        )

    def create(self, payload, actor):
        release_id, timestamp = str(uuid4()), now()
        try:
            with self.transaction() as db:
                db.execute(
                    """INSERT INTO releases(id, environment, commit_sha, image_digest,
                       committed_at, evidence_url, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        release_id,
                        payload.environment,
                        payload.commit_sha,
                        payload.image_digest,
                        payload.committed_at.isoformat(),
                        str(payload.evidence_url),
                        timestamp,
                    ),
                )
                self.event(db, release_id, "created", actor, timestamp)
                return self.row(db, release_id)
        except sqlite3.IntegrityError as error:
            raise Conflict("Image digest is already registered in this environment") from error

    def get(self, release_id):
        with self.connect() as db:
            return self.row(db, release_id)

    def list(self, limit=50):
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM releases ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
                )
            ]

    def events(self, release_id):
        with self.connect() as db:
            self.row(db, release_id)
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM events WHERE release_id = ? ORDER BY sequence", (release_id,)
                )
            ]

    def transition(self, release_id, action, version, actor):
        timestamp = now()
        with self.transaction() as db:
            item = self.row(db, release_id)
            if item["version"] != version:
                raise Conflict("Stale version: reload the release before retrying")
            allowed = {
                "approve": "candidate",
                "deploy": "approved",
                "fail": "deployed",
                "rollback": "failed",
            }
            if item["status"] != allowed[action]:
                raise Conflict(f"Cannot {action} a release in state {item['status']}")
            active = db.execute(
                "SELECT release_id FROM active WHERE environment = ?", (item["environment"],)
            ).fetchone()
            if action in {"fail", "rollback"} and (
                active is None or active["release_id"] != release_id
            ):
                raise Conflict("Only the active release can fail or roll back")
            if action == "approve":
                db.execute(
                    "UPDATE releases SET status='approved', approved_at=?, version=version+1 "
                    "WHERE id=?",
                    (timestamp, release_id),
                )
            elif action == "deploy":
                previous_id = active["release_id"] if active else None
                if previous_id:
                    previous = self.row(db, previous_id)
                    if previous["status"] == "deployed":
                        db.execute(
                            "UPDATE releases SET status='superseded', version=version+1 WHERE id=?",
                            (previous_id,),
                        )
                    elif previous["status"] == "failed":
                        db.execute(
                            "UPDATE releases SET recovered_at=?, version=version+1 WHERE id=?",
                            (timestamp, previous_id),
                        )
                        self.event(db, previous_id, "recovered_by_deployment", actor, timestamp)
                        # A failed release is not a valid future rollback target.
                        previous_id = previous["previous_id"]
                db.execute(
                    "UPDATE releases SET status='deployed', deployed_at=?, previous_id=?, "
                    "version=version+1 WHERE id=?",
                    (timestamp, previous_id, release_id),
                )
                db.execute(
                    "INSERT INTO active(environment, release_id) VALUES (?, ?) "
                    "ON CONFLICT(environment) DO UPDATE SET release_id=excluded.release_id",
                    (item["environment"], release_id),
                )
            elif action == "fail":
                db.execute(
                    "UPDATE releases SET status='failed', failed_at=?, "
                    "version=version+1 WHERE id=?",
                    (timestamp, release_id),
                )
            else:
                if item["previous_id"] is None:
                    raise Conflict("No healthy predecessor; deploy a verified replacement")
                previous = self.row(db, item["previous_id"])
                if previous["status"] != "superseded":
                    raise Conflict("Rollback target is not a healthy predecessor")
                db.execute(
                    "UPDATE releases SET status='rolled_back', recovered_at=?, version=version+1 "
                    "WHERE id=?",
                    (timestamp, release_id),
                )
                db.execute(
                    "UPDATE releases SET status='deployed', version=version+1 WHERE id=?",
                    (previous["id"],),
                )
                db.execute(
                    "UPDATE active SET release_id=? WHERE environment=?",
                    (previous["id"], item["environment"]),
                )
                self.event(db, previous["id"], "restored", actor, timestamp)
            self.event(db, release_id, action, actor, timestamp)
            return self.row(db, release_id)

    def summary(self, days=30):
        end = datetime.now(UTC)
        start = (end - timedelta(days=days)).isoformat()
        with self.connect() as db:
            releases = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM releases WHERE environment='production' AND deployed_at >= ?",
                    (start,),
                )
            ]
            active = [
                dict(row)
                for row in db.execute(
                    "SELECT r.* FROM releases r JOIN active a ON a.release_id=r.id "
                    "ORDER BY r.environment"
                )
            ]
        failures = [r for r in releases if r["failed_at"]]
        recovery = [
            (
                datetime.fromisoformat(r["recovered_at"]) - datetime.fromisoformat(r["failed_at"])
            ).total_seconds()
            for r in failures
            if r["recovered_at"]
        ]
        leads = [
            (
                datetime.fromisoformat(r["deployed_at"]) - datetime.fromisoformat(r["committed_at"])
            ).total_seconds()
            for r in releases
        ]
        return {
            "window_days": days,
            "window_start": start,
            "window_end": end.isoformat(),
            "production_deployments": len(releases),
            "deployments_per_day": len(releases) / days,
            "change_failure_rate": len(failures) / len(releases) if releases else None,
            "mean_lead_time_seconds": sum(leads) / len(leads) if leads else None,
            "mean_recovery_time_seconds": sum(recovery) / len(recovery) if recovery else None,
            "recovered_incidents": len(recovery),
            "open_incidents": sum(r["recovered_at"] is None for r in failures),
            "active": active,
        }
