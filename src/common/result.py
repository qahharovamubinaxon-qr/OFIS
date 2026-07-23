"""A tiny ``Result`` type for recoverable operations.

Business operations that can fail *expectedly* (a validation miss, a provider
that is temporarily down) return ``Result[T]`` instead of raising, so the caller
is forced to handle both branches. Truly exceptional situations still raise an
:class:`~src.common.errors.OfisError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from src.common.errors import OfisError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Result(Generic[T]):
    """Either a value (``ok``) or an :class:`OfisError` (``error``)."""

    _value: T | None
    _error: OfisError | None

    @staticmethod
    def ok(value: T) -> "Result[T]":
        return Result(value, None)

    @staticmethod
    def fail(error: OfisError) -> "Result[T]":
        return Result(None, error)

    @property
    def is_ok(self) -> bool:
        return self._error is None

    @property
    def value(self) -> T:
        if self._error is not None:
            raise self._error
        assert self._value is not None
        return self._value

    @property
    def error(self) -> OfisError | None:
        return self._error

    def unwrap_or(self, default: T) -> T:
        return self._value if self.is_ok and self._value is not None else default
