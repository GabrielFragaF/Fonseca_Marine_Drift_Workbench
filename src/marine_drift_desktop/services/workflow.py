from __future__ import annotations

from ..core.workflow import SimulationWorkflowEngine


class SimulationWorkflowService(SimulationWorkflowEngine):
    """App-facing workflow service backed by the shared core engine."""
