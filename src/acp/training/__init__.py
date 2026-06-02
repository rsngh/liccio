"""Training-data factory (Alpha-7 WS3/4/18).

Turns persisted ACP run exhaust (traces, evaluations, weak/human labels,
routing decisions, rewards) into versioned, redacted, leakage-audited training
datasets, JSONL exporters, and a fine-tuning candidate report.
"""

from __future__ import annotations

from acp.training.dataset_factory import DatasetFactory

__all__ = ["DatasetFactory"]
