from __future__ import annotations

import uuid

from scratch_notebook import models
from scratch_notebook.validation import NOT_VALIDATED_MESSAGE, validate_cell


def test_plain_text_validation_returns_warning() -> None:
    cell = models.ScratchCell(
        cell_id=str(uuid.uuid4()),
        index=3,
        language="txt",
        content="free form notes",
    )

    result = validate_cell(cell)

    assert result.valid is True
    assert any(NOT_VALIDATED_MESSAGE in warning["message"] for warning in result.warnings)
    assert result.details.get("reason") == "Plain text does not require validation"
