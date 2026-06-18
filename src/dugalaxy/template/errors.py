"""Legible, pre-run errors: missing variable refs, dependency cycles, unknown types."""


class DugalaxyError(Exception):
    """Base class for all Dugalaxy errors."""


class TemplateLoadError(DugalaxyError):
    """Failed to parse or validate a template file (YAML syntax, schema mismatch)."""


class MissingReferenceError(DugalaxyError):
    """A template expression references a scenario variable that is not defined."""


class CyclicDependencyError(DugalaxyError):
    """Composite variables (computed/object) have a circular dependency."""
