"""
Deploy executor: copies scripts to the OS clipboard
and generates step-by-step instructions for Packet Tracer.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from ...domain.models.plans import TopologyPlan
from ...shared.utils import safe_name
from ..generator.ptbuilder_generator import generate_ptbuilder_script, generate_full_script
from ..generator.cli_config_generator import generate_all_configs
from .executor_base import ExecutorBase


def _clipboard_command() -> tuple[list[str], str] | None:
    """Return (argv, text-encoding) for the current OS's clipboard tool, or None.

    Cross-platform so deploy behaves identically on Windows, macOS and Linux:
      - Windows -> clip.exe        (expects UTF-16-LE)
      - macOS   -> pbcopy          (UTF-8)
      - Linux   -> wl-copy / xclip / xsel, whichever is installed (UTF-8)
    """
    if sys.platform == "win32":
        return (["clip"], "utf-16-le")
    if sys.platform == "darwin":
        return (["pbcopy"], "utf-8")
    # Linux / BSD: prefer Wayland, then X11 helpers; use the first available.
    for argv in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
        if shutil.which(argv[0]):
            return (argv, "utf-8")
    return None


def _copy_to_clipboard(text: str) -> bool:
    """Copy text to the OS clipboard. Best-effort and cross-platform.

    Returns False (not an error) when no clipboard tool is available; callers
    always also write the script to disk, so deploy still succeeds either way.
    """
    cmd = _clipboard_command()
    if cmd is None:
        return False
    argv, encoding = cmd
    try:
        subprocess.run(
            argv,
            input=text.encode(encoding),
            check=True,
            timeout=5,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


class DeployExecutor(ExecutorBase):
    """
    Deploy a topology in Packet Tracer.

    Strategy:
    1. Generate the PTBuilder script (addDevice + addLink)
    2. Copy it to the Windows clipboard
    3. Export files to disk (CLI configs, plan JSON)
    4. Return step-by-step instructions
    """

    def __init__(self, output_dir: str | Path = "projects"):
        self.output_dir = Path(output_dir)

    def execute(self, plan: TopologyPlan, project_name: str | None = None) -> dict:
        """Deploy the plan: clipboard + files + instructions."""
        base_name = (project_name or plan.name or "topology").strip() or "topology"
        # Use the SAME normalization as ProjectRepository so a name with '/' or
        # other unsafe chars maps to the same single directory (not a nested path).
        project_dir = self.output_dir / safe_name(base_name)
        project_dir.mkdir(parents=True, exist_ok=True)

        # Generate scripts
        topology_script = generate_ptbuilder_script(plan)
        full_script = generate_full_script(plan)
        configs = generate_all_configs(plan)

        # Copy the topology script to the clipboard
        clipboard_ok = _copy_to_clipboard(topology_script)

        # Save files to disk
        files: dict[str, str] = {}

        script_path = project_dir / "topology.js"
        script_path.write_text(topology_script, encoding="utf-8", newline="\n")
        files["topology_script"] = str(script_path)

        full_path = project_dir / "full_build.js"
        full_path.write_text(full_script, encoding="utf-8", newline="\n")
        files["full_script"] = str(full_path)

        for device_name, config_text in configs.items():
            cfg_path = project_dir / f"{device_name}_config.txt"
            cfg_path.write_text(config_text, encoding="utf-8", newline="\n")
            files[f"config_{device_name}"] = str(cfg_path)

        plan_path = project_dir / "plan.json"
        plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8", newline="\n")
        files["plan_json"] = str(plan_path)

        # Generate instructions
        instructions = self._build_instructions(
            plan, configs, clipboard_ok, project_dir
        )

        return {
            "status": "deployed" if clipboard_ok else "exported",
            "clipboard": clipboard_ok,
            "project_dir": str(project_dir),
            "files": files,
            "devices_count": len(plan.devices),
            "links_count": len(plan.links),
            "instructions": instructions,
        }

    def is_available(self) -> bool:
        """Always available. File export + instructions are platform-independent,
        and the clipboard step (clip.exe / pbcopy / xclip / wl-copy) degrades
        gracefully to file export when no clipboard tool is present."""
        return True

    @staticmethod
    def _build_instructions(
        plan: TopologyPlan,
        configs: dict[str, str],
        clipboard_ok: bool,
        project_dir: Path,
    ) -> str:
        """Generate step-by-step instructions to complete the deployment."""
        steps: list[str] = []

        # Step 1: PTBuilder script
        steps.append("=" * 60)
        steps.append("STEP 1: Create the topology in Packet Tracer")
        steps.append("=" * 60)
        if clipboard_ok:
            steps.append("The PTBuilder script is already on your clipboard.")
            steps.append("")
            steps.append("  1. Open Packet Tracer")
            steps.append("  2. Go to Extensions > Scripting (or Builder Code Editor)")
            steps.append("  3. Paste the script (Ctrl+V)")
            steps.append("  4. Click 'Run' or press the run button")
            steps.append("")
            steps.append(f"The devices and links will be created automatically.")
        else:
            steps.append(f"Open the file: {project_dir / 'topology.js'}")
            steps.append("Copy its contents and paste them into Packet Tracer:")
            steps.append("  Extensions > Scripting > Paste > Run")

        # Step 2: Configure devices
        routers = [d for d in plan.devices if d.category == "router"]
        switches = [d for d in plan.devices if d.category == "switch"]

        if configs:
            steps.append("")
            steps.append("=" * 60)
            steps.append("STEP 2: Configure devices")
            steps.append("=" * 60)

            for router in routers:
                if router.name in configs:
                    steps.append(f"")
                    steps.append(f"  {router.name}:")
                    steps.append(f"    - Double-click {router.name} > CLI tab")
                    steps.append(f"    - Paste the contents of: {project_dir / f'{router.name}_config.txt'}")

            for switch in switches:
                if switch.name in configs:
                    steps.append(f"")
                    steps.append(f"  {switch.name}:")
                    steps.append(f"    - Double-click {switch.name} > CLI tab")
                    steps.append(f"    - Paste the contents of: {project_dir / f'{switch.name}_config.txt'}")

        # Step 3: Configure PCs
        pcs = [d for d in plan.devices if d.category in ("pc", "server", "laptop")]
        if pcs:
            steps.append("")
            steps.append("=" * 60)
            steps.append("STEP 3: Configure hosts (PCs)")
            steps.append("=" * 60)
            for pc in pcs:
                if plan.dhcp_pools:
                    steps.append(f"  {pc.name}: Desktop > IP Configuration > DHCP")
                elif pc.interfaces:
                    for iface, ip_cidr in pc.interfaces.items():
                        ip = ip_cidr.split("/")[0]
                        steps.append(f"  {pc.name}: IP={ip}, Gateway={pc.gateway or 'N/A'}")

        # Step 4: Verify
        if plan.validations:
            steps.append("")
            steps.append("=" * 60)
            steps.append("STEP 4: Verify connectivity")
            steps.append("=" * 60)
            for v in plan.validations:
                steps.append(f"  {v.check_type}: {v.from_device} -> {v.to_target} (expected: {v.expected})")

        return "\n".join(steps)
