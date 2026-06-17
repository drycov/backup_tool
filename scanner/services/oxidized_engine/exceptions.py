class OxidizedError(Exception):
    """Base error for the Python oxidized engine."""


class MethodNotFound(OxidizedError):
    pass


class ModelNotFound(OxidizedError):
    pass


class NodeNotFound(OxidizedError):
    pass
