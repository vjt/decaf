"""YAML output — canonical tax report dump.

Uses pydantic's `model_dump(mode='json')` to get a Decimal-safe, date-safe
dict, then PyYAML `safe_dump` to emit human-diffable YAML.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from decaf.models import TaxReport


def write_yaml(report: TaxReport, path: Path) -> None:
    """Write the tax report as a YAML file (canonical oracle format)."""
    data = report.model_dump(mode="json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(
            data,
            f,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )


def read_yaml(path: Path) -> TaxReport:
    """Load a YAML tax report, validated back into a typed TaxReport."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return TaxReport.model_validate(data)
