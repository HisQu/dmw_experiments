"""Small standard-library helpers for dmw_experiments.

Keep this module for generic helpers that are genuinely useful across the
project. Configuration is handled by AppRC and logging should use the standard
library instead of local utility code.
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import reduce
from operator import getitem
from typing import Any

import time


def deep_get(d: dict, keypath: tuple, default=None) -> Any:
    """Read a nested dictionary value without branching at every level.

    :param d: Mapping tree to inspect.
    :param keypath: Ordered dictionary keys from root to leaf.
    :param default: Value returned when any key is missing.
    :return: Leaf value or ``default``.
    """
    try:
        return reduce(getitem, keypath, d)
    except (KeyError, TypeError):
        return default


def deep_set(
    d: dict,
    keypath: tuple,
    value: Any,
) -> None:
    """Write a nested dictionary value and create missing parent mappings.

    :param d: Mapping tree to mutate.
    :param keypath: Ordered dictionary keys from root to leaf.
    :param value: Value stored at the final key.
    """
    for k in keypath[:-1]:
        d = d.setdefault(k, {})
    d[keypath[-1]] = value


def deep_right_merge(a: dict, b: dict) -> dict:
    """Merge two nested dictionaries and let ``b`` win conflicts.

    :param a: Base dictionary that should remain untouched.
    :param b: Overlay dictionary whose leaves replace matching leaves in ``a``.
    :return: New merged dictionary.
    """
    out = a.copy()
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_right_merge(out[k], v)
        else:
            out[k] = v
    return out


@contextmanager
def timer(name: str = "block"):
    """Print elapsed wall time when a manual diagnostic block exits.

    :param name: Label printed with the elapsed duration.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        print(f"{name} finished in {elapsed:0.4f}s")
