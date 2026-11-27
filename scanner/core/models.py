from django.db import models


class LegacyJSONField(models.JSONField):
    """SQLAlchemy JSON columns may return already-deserialized Python objects."""

    def from_db_value(self, value, expression, connection):
        if isinstance(value, (dict, list)):
            return value
        return super().from_db_value(value, expression, connection)
