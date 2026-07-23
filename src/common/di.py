"""A minimal dependency-injection container.

Wired once in ``app.py`` (the composition root). Every service/controller
receives its collaborators through its constructor, so units are testable with
fakes and there are no global singletons scattered through the code.

Two registration styles:
  * ``register_instance`` — an already-built object (e.g. SettingsService).
  * ``register_factory``  — a zero-arg callable, resolved lazily and cached
    (singleton) unless ``singleton=False``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class Container:
    def __init__(self) -> None:
        self._instances: dict[type, object] = {}
        self._factories: dict[type, tuple[Callable[[], object], bool]] = {}

    def register_instance(self, key: type[T], instance: T) -> None:
        self._instances[key] = instance

    def register_factory(
        self, key: type[T], factory: Callable[[], T], *, singleton: bool = True
    ) -> None:
        self._factories[key] = (factory, singleton)

    def resolve(self, key: type[T]) -> T:
        if key in self._instances:
            return self._instances[key]  # type: ignore[return-value]
        if key in self._factories:
            factory, singleton = self._factories[key]
            obj = factory()
            if singleton:
                self._instances[key] = obj
            return obj  # type: ignore[return-value]
        raise KeyError(f"No registration for {key.__name__}")
