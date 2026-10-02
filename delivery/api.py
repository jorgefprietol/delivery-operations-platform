import hmac
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, field_validator

from delivery.store import Conflict, NotFound, Store

logger = logging.getLogger("delivery")
bearer = HTTPBearer(auto_error=False)


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: Literal["staging", "production"]
    commit_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    image_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    committed_at: AwareDatetime
    evidence_url: HttpUrl
    quality_passed: Literal[True]
    security_passed: Literal[True]
    integration_passed: Literal[True]

    @field_validator("committed_at")
    @classmethod
    def past_timestamp(cls, value):
        if value > datetime.now(UTC):
            raise ValueError("Commit timestamp must not be in the future")
        return value.astimezone(UTC)

    @field_validator("evidence_url")
    @classmethod
    def github_evidence(cls, value):
        if (
            value.scheme != "https"
            or value.host != "github.com"
            or "/actions/runs/" not in (value.path or "")
        ):
            raise ValueError("Evidence must reference a GitHub Actions run over HTTPS")
        return value


class Transition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


def create_app(db_path=None, operator_token=None, approver_token=None):
    operator = operator_token or os.getenv("OPERATOR_TOKEN", "")
    approver = approver_token or os.getenv("APPROVER_TOKEN", "")

    @asynccontextmanager
    async def lifespan(app):
        if min(len(operator), len(approver)) < 32 or hmac.compare_digest(
            operator.encode(), approver.encode()
        ):
            raise RuntimeError("Configure distinct operator and approver tokens of 32+ characters")
        yield

    app = FastAPI(
        title="Delivery Operations Platform",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    store = Store(db_path or os.getenv("DATABASE_PATH", "/data/delivery.db"))
    registry = CollectorRegistry()
    requests = Counter(
        "delivery_http_requests", "HTTP requests", ["route", "status"], registry=registry
    )
    duration = Histogram(
        "delivery_http_duration_seconds", "HTTP duration", ["route"], registry=registry
    )

    def role(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        supplied = credentials.credentials if credentials else ""
        if operator and hmac.compare_digest(supplied.encode(), operator.encode()):
            return "operator"
        if approver and hmac.compare_digest(supplied.encode(), approver.encode()):
            return "approver"
        raise HTTPException(401, "Invalid bearer token", headers={"WWW-Authenticate": "Bearer"})

    def require_operator(actor: Annotated[str, Depends(role)]):
        if actor != "operator":
            raise HTTPException(403, "Operator role required")
        return actor

    def require_approver(actor: Annotated[str, Depends(role)]):
        if actor != "approver":
            raise HTTPException(403, "Approver role required")
        return actor

    @app.exception_handler(Conflict)
    async def conflict_handler(request, error):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(NotFound)
    async def missing_handler(request, error):
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.middleware("http")
    async def observe(request: Request, call_next):
        request_id, start = str(uuid4()), time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.error(json.dumps({"request_id": request_id, "event": "request_failed"}))
            response = JSONResponse(status_code=500, content={"detail": "Internal service error"})
        route = request.scope.get("route")
        path = route.path if route else "unmatched"
        elapsed = time.perf_counter() - start
        if path not in {"/metrics", "/health/live", "/health/ready"}:
            requests.labels(path, str(response.status_code)).inc()
            duration.labels(path).observe(elapsed)
            logger.info(
                json.dumps(
                    {
                        "request_id": request_id,
                        "route": path,
                        "method": request.method,
                        "status": response.status_code,
                        "duration_ms": round(elapsed * 1000, 2),
                    }
                )
            )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            with store.connect() as db:
                db.execute("SELECT 1 FROM releases LIMIT 1")
        except Exception as error:
            raise HTTPException(503, "Database unavailable") from error
        return {"status": "ready", "revision": os.getenv("SOURCE_REVISION", "development")}

    @app.get("/api/v1/releases", dependencies=[Depends(role)])
    def releases(limit: Annotated[int, Query(ge=1, le=200)] = 50):
        return store.list(limit)

    @app.post("/api/v1/releases", status_code=201)
    def register(payload: Candidate, actor: Annotated[str, Depends(require_operator)]):
        return store.create(payload, actor)

    @app.get("/api/v1/releases/{release_id}", dependencies=[Depends(role)])
    def release(release_id: str):
        return store.get(release_id)

    @app.get("/api/v1/releases/{release_id}/events", dependencies=[Depends(role)])
    def events(release_id: str):
        return store.events(release_id)

    @app.post("/api/v1/releases/{release_id}/approve")
    def approve(
        release_id: str, payload: Transition, actor: Annotated[str, Depends(require_approver)]
    ):
        return store.transition(release_id, "approve", payload.expected_version, actor)

    @app.post("/api/v1/releases/{release_id}/{action}")
    def transition(
        release_id: str,
        action: Literal["deploy", "fail", "rollback"],
        payload: Transition,
        actor: Annotated[str, Depends(require_operator)],
    ):
        return store.transition(release_id, action, payload.expected_version, actor)

    @app.get("/api/v1/summary", dependencies=[Depends(role)])
    def summary(days: Annotated[int, Query(ge=1, le=90)] = 30):
        return store.summary(days)

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        snapshot = store.summary()
        values = {
            "delivery_production_deployments_30d": snapshot["production_deployments"],
            "delivery_open_incidents_30d": snapshot["open_incidents"],
            "delivery_recovered_incidents_30d": snapshot["recovered_incidents"],
            "delivery_change_failure_ratio_30d": snapshot["change_failure_rate"],
            "delivery_mean_lead_time_seconds_30d": snapshot["mean_lead_time_seconds"],
            "delivery_mean_recovery_time_seconds_30d": snapshot["mean_recovery_time_seconds"],
        }
        business = "".join(
            f"# TYPE {key} gauge\n{key} {value}\n"
            for key, value in values.items()
            if value is not None
        )
        return Response(
            generate_latest(registry) + business.encode(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get("/", include_in_schema=False)
    def dashboard():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/assets/{filename}", include_in_schema=False)
    def assets(filename: Literal["app.js", "style.css"]):
        return FileResponse(Path(__file__).parent / "static" / filename)

    app.state.store = store
    return app
