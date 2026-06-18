"""Topological dependency resolution for computed/object variables. Detects cycles.

Primitives have no dependencies; composites (``computed``/``object``) may reference
other variables. We sort so that every referenced variable is resolved before the
variable that needs it. Independent variables are ordered lexicographically so the
resolution order itself is deterministic (the facts do not depend on it — each
variable is seeded independently by name — but a stable order keeps things legible).
"""

import heapq
from collections.abc import Mapping

from dugalaxy.template.errors import CyclicDependencyError, MissingReferenceError
from dugalaxy.template.loader import extract_refs
from dugalaxy.template.spec import ComputedVar, ObjectVar, VariableSpec


def _dependencies(variables: Mapping[str, VariableSpec]) -> dict[str, set[str]]:
    """Map each variable to the set of variables it directly references."""
    defined = set(variables)
    deps: dict[str, set[str]] = {}
    for name, var in variables.items():
        if isinstance(var, (ComputedVar, ObjectVar)):
            refs = extract_refs(var.value)
            missing = refs - defined
            if missing:
                ref = sorted(missing)[0]
                raise MissingReferenceError(
                    f"Variable '{name}' references undefined variable '{ref}'"
                )
            deps[name] = refs
        else:
            deps[name] = set()
    return deps


def resolve_order(variables: Mapping[str, VariableSpec]) -> list[str]:
    """Return variable names in dependency order (dependencies first).

    Raises:
        MissingReferenceError: a composite references an undefined variable.
        CyclicDependencyError: composite variables form a dependency cycle.
    """
    deps = _dependencies(variables)

    # Kahn's algorithm. Edge d -> name means "name depends on d".
    indegree = {name: len(ds) for name, ds in deps.items()}
    dependents: dict[str, list[str]] = {name: [] for name in deps}
    for name, ds in deps.items():
        for d in ds:
            dependents[d].append(name)

    ready = [name for name, deg in indegree.items() if deg == 0]
    heapq.heapify(ready)

    order: list[str] = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for dependent in dependents[node]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                heapq.heappush(ready, dependent)

    if len(order) != len(deps):
        stuck = ", ".join(sorted(set(deps) - set(order)))
        raise CyclicDependencyError(f"Circular dependency among composite variables: {stuck}")
    return order
