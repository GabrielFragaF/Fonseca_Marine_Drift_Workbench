from __future__ import annotations

from ..domain.models import SimulationRequest, SimulationSummary, ValidationMessage
from .validation import SimulationRequestValidator


class SimulationWorkflowEngine:
    """
    Coordinates generalized request validation and higher-level workflow notes.

    This layer is intentionally independent from the UI so the same logic can be
    reused by a future CLI runner, background worker, or packaged desktop build.
    """

    def __init__(self, validator: SimulationRequestValidator | None = None) -> None:
        self.validator = validator or SimulationRequestValidator()

    def preview(self, request: SimulationRequest) -> SimulationSummary:
        messages = self.validator.validate(request)
        if not any(message.level == "error" for message in messages):
            messages.extend(
                [
                    ValidationMessage(
                        "info",
                        "Configuration is ready for local reverse-drift execution.",
                    ),
                    ValidationMessage(
                        "info",
                        "Run simulation will use these observation, forcing, position, and model settings.",
                    ),
                ]
            )

        return SimulationSummary(
            output_directory=request.data_sources.output_directory,
            messages=messages,
        )
