"""Bounded thread-pool fan-out for independent per-item blocking work
(LLM calls, retrieval, web search) shared by verification.py and repair_note.py."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, TypeVar

from backend.common.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T")
R = TypeVar("R")


def run_concurrent(
    items: list[T],
    worker: Callable[[T], R],
    *,
    on_error: Callable[[T, Exception], R],
    max_workers: int | None = None,
) -> list[R]:
    """Run worker(item) for every item, ordered like `items`, isolating failures.

    - 0 or 1 items: runs inline, no thread spun up. This keeps single-item
      call sites -- including nested calls made from inside another worker
      thread -- behaviourally identical to a plain sequential call, and
      prevents nested thread pools when a worker itself calls run_concurrent
      with a single item.
    - `on_error` is mandatory: it converts one item's exception into a
      substitute result instead of letting it kill the whole batch/request.
    """
    if not items:
        return []
    if len(items) == 1:
        try:
            return [worker(items[0])]
        except Exception as exc:
            logger.warning("Concurrent worker failed for %r: %s", items[0], exc)
            return [on_error(items[0], exc)]

    workers = max(1, min(max_workers or settings.m4_verify_max_workers, len(items)))
    results: list[R] = [None] * len(items)  # type: ignore[list-item]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="m4-verify") as pool:
        futures = {pool.submit(worker, item): index for index, item in enumerate(items)}
        for future in as_completed(futures):
            index = futures[future]
            try:
                results[index] = future.result()
            except Exception as exc:
                logger.warning("Concurrent worker failed for %r: %s", items[index], exc)
                results[index] = on_error(items[index], exc)
    return results
