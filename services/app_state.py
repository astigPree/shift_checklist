"""Central registry used to share services between Kivy screens."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ServiceContainer:
    """Small explicit service registry populated during application startup."""

    _services: dict[str, Any] = field(default_factory=dict)

    def register(self, name: str, service: Any) -> None:
        """Register exactly one service under a non-empty name."""

        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("service name cannot be blank")
        if normalized_name in self._services:
            raise ValueError(f"service already registered: {normalized_name}")
        self._services[normalized_name] = service

    def get(self, name: str) -> Any:
        """Return a registered service, raising a useful error if unavailable."""

        try:
            return self._services[name]
        except KeyError as error:
            raise LookupError(f"service is not registered: {name}") from error

    def contains(self, name: str) -> bool:
        """Return whether a service has been registered."""

        return name in self._services
