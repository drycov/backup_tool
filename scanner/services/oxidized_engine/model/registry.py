from __future__ import annotations

from services.oxidized_engine.exceptions import ModelNotFound
from services.oxidized_engine.model.base import Model
from services.oxidized_engine.model.eos import EOSModel
from services.oxidized_engine.model.ios import IOSModel
from services.oxidized_engine.model.junos import JunOSModel
from services.oxidized_engine.model.routeros import RouterOSModel

_MODELS: dict[str, type[Model]] = {
    "routeros": RouterOSModel,
    "mikrotik": RouterOSModel,
    "ros": RouterOSModel,
    "ios": IOSModel,
    "cisco": IOSModel,
    "iosxe": IOSModel,
    "junos": JunOSModel,
    "juniper": JunOSModel,
    "eos": EOSModel,
    "arista": EOSModel,
}


def get_model(name: str) -> Model:
    key = (name or "").lower().replace("-", "").replace("_", "")
    model_cls = _MODELS.get(key)
    if not model_cls:
        raise ModelNotFound(f"model '{name}' not found")
    return model_cls()


def list_native_models() -> list[str]:
    seen: set[type[Model]] = set()
    names: list[str] = []
    priority = ("routeros", "ios", "junos", "eos")
    for key in priority + tuple(sorted(_MODELS.keys())):
        cls = _MODELS.get(key)
        if not cls or cls in seen:
            continue
        seen.add(cls)
        names.append(key)
    return names
