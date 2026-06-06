"""
Manual executor: exports files for the user to copy/paste.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from ...domain.models.plans import TopologyPlan
from ...shared.utils import safe_name
from ..generator.ptbuilder_generator import generate_ptbuilder_script, generate_full_script
from ..generator.cli_config_generator import generate_all_configs
from .executor_base import ExecutorBase


class ManualExecutor(ExecutorBase):
    """Generate output files for manual execution."""

    def __init__(self, output_dir: str | Path = "projects"):
        self.output_dir = Path(output_dir)

    def execute(self, plan: TopologyPlan, project_name: str | None = None) -> dict:
        """Generate all topology files."""
        safe_proj = safe_name(project_name or plan.name or "topology")
        project_dir = self.output_dir / safe_proj
        project_dir.mkdir(parents=True, exist_ok=True)

        files: dict[str, str] = {}

        # PTBuilder script
        script = generate_ptbuilder_script(plan)
        script_path = project_dir / "topology.js"
        script_path.write_text(script, encoding="utf-8", newline="\n")
        files["topology_script"] = str(script_path)

        # Full script (topology + configs as comments)
        full = generate_full_script(plan)
        full_path = project_dir / "full_build.js"
        full_path.write_text(full, encoding="utf-8", newline="\n")
        files["full_script"] = str(full_path)

        # Individual CLI configs
        configs = generate_all_configs(plan)
        for device_name, config_text in configs.items():
            cfg_path = project_dir / f"{safe_name(device_name, fallback=device_name or 'device')}_config.txt"
            cfg_path.write_text(config_text, encoding="utf-8", newline="\n")
            files[f"config_{device_name}"] = str(cfg_path)

        # Plan JSON
        plan_path = project_dir / "plan.json"
        plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8", newline="\n")
        files["plan_json"] = str(plan_path)

        # Project metadata
        meta_path = project_dir / "metadata.json"
        metadata = {
            "project_name": safe_proj,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "devices": len(plan.devices),
            "links": len(plan.links),
            "is_valid": plan.is_valid,
        }
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8", newline="\n")
        files["metadata"] = str(meta_path)

        return {
            "status": "exported",
            "project_dir": str(project_dir),
            "files": files,
            "devices_count": len(plan.devices),
            "links_count": len(plan.links),
        }

    def is_available(self) -> bool:
        return True
