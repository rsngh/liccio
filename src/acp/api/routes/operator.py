"""Operator API surface (Alpha 11, WS16/WS17).

A backend-first operator view over the control plane: health (mode-aware),
artifact manifest, capability matrix, per-run policy dossier, scheduler run, and
the ingested report warehouse — all wired to existing ``AppService`` methods so a
UI can follow later.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from acp.api.service import AppService


def build_operator_router(svc: AppService) -> APIRouter:
    router = APIRouter(prefix="/operator", tags=["operator"])

    @router.get("/health/control-plane")
    def control_plane_health(mode: str = "lab") -> dict:
        return svc.control_plane_health(mode=mode)

    @router.get("/capability-matrix")
    def capability_matrix() -> dict:
        return svc.build_capability_matrix()

    @router.get("/runs/{run_id}/policy-dossier")
    def policy_dossier(run_id: str) -> dict:
        try:
            return svc.policy_dossier(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found") from exc

    @router.get("/reports")
    def reports(ingest_id: str | None = None) -> dict:
        return {"reports": svc.list_reports(ingest_id)}

    @router.post("/reports/ingest")
    def ingest_reports() -> dict:
        return svc.ingest_reports(source_command="operator-api")

    @router.post("/scheduler/run")
    def scheduler_run() -> dict:
        return svc.learn_schedule_run()

    return router
