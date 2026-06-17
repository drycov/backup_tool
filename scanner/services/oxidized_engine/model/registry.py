from __future__ import annotations

from services.oxidized_engine.exceptions import ModelNotFound
from services.oxidized_engine.model.base import Model
from services.oxidized_engine.model.routeros import RouterOSModel

_MODELS: dict[str, type[Model]] = {
    "routeros": RouterOSModel,
}


def get_model(name: str) -> Model:
    model_cls = _MODELS.get((name or "").lower())
    if not model_cls:
        raise ModelNotFound(f"model '{name}' not found")
    return model_cls()
