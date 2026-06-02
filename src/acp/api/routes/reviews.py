"""Human-review studio product API (Alpha 8, WS15).

A FastAPI ``APIRouter`` exposing the review-studio endpoints, wired to the
existing :class:`~acp.api.service.AppService`. The app constructs routers with a
service instance (mirroring the closure pattern in :mod:`acp.api.app`), so the
router is built by :func:`build_reviews_router` rather than a global dependency.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from acp.api.service import AppService
from acp.core.enums import HumanVerdict
from acp.evaluation.evaluator_trust import default_trust_dataset, evaluate_trust
from acp.schemas.human_review import HumanLabel


class LabelBody(BaseModel):
    """Request body for labelling a review item."""

    verdict: HumanVerdict = HumanVerdict.PASS
    score: float = 0.8
    reason: str = ""
    reviewer: str = "studio"


def build_reviews_router(svc: AppService) -> APIRouter:
    """Build the review-studio router bound to ``svc``."""
    router = APIRouter(prefix="/reviews", tags=["review-studio"])

    @router.get("/queue")
    def queue(priority_min: float = 0.0) -> list[dict]:
        """List open reviews, highest priority first."""
        return [i.model_dump(mode="json") for i in svc.list_reviews(priority_min)]

    @router.get("/{review_id}/bundle")
    def bundle(review_id: str) -> dict:
        """Return the secret-free adjudication bundle for a review."""
        try:
            return svc.review_bundle(review_id)
        except KeyError as exc:
            raise HTTPException(404, "review not found") from exc

    @router.post("/{review_id}/label")
    def label(review_id: str, body: LabelBody) -> dict:
        """Record a human label and resume the paused run."""
        item = svc.get_review(review_id)
        if item is None:
            raise HTTPException(404, "review not found")
        human_label = HumanLabel(
            review_item_id=review_id,
            task_id=item.task_id,
            attempt_id=item.attempt_id,
            verdict=body.verdict,
            score=body.score,
            reason=body.reason,
            reviewer=body.reviewer,
        )
        svc.label_review(review_id, human_label)
        return human_label.model_dump(mode="json")

    @router.post("/{review_id}/make-eval-case")
    def make_eval_case(review_id: str) -> dict:
        """Turn a labelled review into a durable eval case."""
        try:
            return svc.make_eval_case(review_id)
        except KeyError as exc:
            raise HTTPException(404, "review not found") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/{review_id}/make-training-example")
    def make_training_example(review_id: str) -> dict:
        """Turn a labelled review into a redacted training example."""
        try:
            return svc.make_training_example(review_id)
        except KeyError as exc:
            raise HTTPException(404, "review not found") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/{review_id}/calibrate")
    def calibrate(review_id: str) -> dict:
        """Evaluator-trust calibration view for a review.

        Runs the trust evaluation over the default synthetic dataset and attaches
        the review's own evaluation summary so the reviewer can weigh the
        evaluator's calibrated trustworthiness against this specific verdict.
        """
        item = svc.get_review(review_id)
        if item is None:
            raise HTTPException(404, "review not found")
        bundle = svc.review_bundle(review_id)
        return {
            "review_id": review_id,
            "trust": evaluate_trust(default_trust_dataset()),
            "evaluation": bundle.get("evaluation"),
            "judge_disagreement": bundle.get("judge_disagreement"),
        }

    return router
