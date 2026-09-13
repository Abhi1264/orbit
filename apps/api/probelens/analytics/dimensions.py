"""Allowlisted dimensions and filter compilation.

Only columns listed here can be filtered or grouped on, and every value is
bound as a query parameter, so no user input is ever interpolated into SQL.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

class Scope(StrEnum):
    # Constant across a session (set on every event of the session).
    session = "session"
    # Set only on the events it applies to (product, payment, search attributes).
    event = "event"

@dataclass(frozen=True)
class Dimension:
    key: str
    label: str
    scope: Scope
    ch_type: str = "String"
    column: str | None = None

    @property
    def col(self) -> str:
        return self.column or self.key

DIMENSIONS: dict[str, Dimension] = {
    d.key: d
    for d in [
        Dimension("platform", "Platform", Scope.session),
        Dimension("device_type", "Device", Scope.session),
        Dimension("app_version", "App version", Scope.session),
        Dimension("country", "Country", Scope.session),
        Dimension("city", "City", Scope.session),
        Dimension("city_tier", "City tier", Scope.session),
        Dimension("traffic_source", "Traffic source", Scope.session),
        Dimension("user_type", "New vs returning", Scope.session),
        Dimension("category", "Category", Scope.event),
        Dimension("subcategory", "Subcategory", Scope.event),
        Dimension("product_id", "Product", Scope.event, ch_type="UInt32"),
        Dimension("payment_method", "Payment method", Scope.event),
        Dimension("payment_gateway", "Payment gateway", Scope.event),
        Dimension("failure_reason", "Payment failure reason", Scope.event),
        Dimension("return_reason", "Return reason", Scope.event),
        Dimension("search_query", "Search query", Scope.event),
    ]
}

Operator = Literal["eq", "neq", "in", "not_in"]

class Filter(BaseModel):
    dimension: str
    operator: Operator = "eq"
    value: str | int | None = None
    values: list[str | int] | None = None

    @model_validator(mode="after")
    def _check(self) -> "Filter":
        if self.dimension not in DIMENSIONS:
            raise ValueError(f"Unknown dimension '{self.dimension}'")
        if self.operator in ("eq", "neq") and self.value is None:
            raise ValueError("value is required for eq/neq")
        if self.operator in ("in", "not_in") and not self.values:
            raise ValueError("values is required for in/not_in")
        return self

    @property
    def dim(self) -> Dimension:
        return DIMENSIONS[self.dimension]

    def describe(self) -> str:
        label = self.dim.label
        if self.operator == "eq":
            return f"{label} = {self.value}"
        if self.operator == "neq":
            return f"{label} ≠ {self.value}"
        joined = ", ".join(str(v) for v in self.values or [])
        return f"{label} {'in' if self.operator == 'in' else 'not in'} ({joined})"

class CompiledWhere(BaseModel):
    sql: str
    params: dict[str, Any] = Field(default_factory=dict)

def compile_filters(filters: list[Filter], prefix: str = "f") -> CompiledWhere:
    """Compile filters to a WHERE fragment with bound parameters. Callers decide
    whether event-scoped filters apply directly or via a session subquery."""
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for i, f in enumerate(filters):
        dim = f.dim
        name = f"{prefix}{i}"
        if f.operator in ("eq", "neq"):
            params[name] = _coerce(dim, f.value)
            op = "=" if f.operator == "eq" else "!="
            clauses.append(f"{dim.col} {op} {{{name}:{dim.ch_type}}}")
        else:
            params[name] = [_coerce(dim, v) for v in f.values or []]
            op = "IN" if f.operator == "in" else "NOT IN"
            clauses.append(f"{dim.col} {op} {{{name}:Array({dim.ch_type})}}")
    return CompiledWhere(sql=" AND ".join(clauses) if clauses else "1", params=params)

def split_by_scope(filters: list[Filter]) -> tuple[list[Filter], list[Filter]]:
    session = [f for f in filters if f.dim.scope == Scope.session]
    event = [f for f in filters if f.dim.scope == Scope.event]
    return session, event

def _coerce(dim: Dimension, value: Any) -> Any:
    if dim.ch_type == "UInt32":
        return int(value)
    return str(value)
