from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar, TextIO


class SingleInstanceError(RuntimeError):
    """Raised when another app instance already owns the runtime lock."""


class SingleInstanceLock:
    """Non-blocking lock file used to prevent duplicate USB app instances."""

    _active_paths: ClassVar[set[Path]] = set()

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self._handle: TextIO | None = None
        self._acquired = False

    def __enter__(self) -> "SingleInstanceLock":
        return self.acquire()

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.release()

    def acquire(self) -> "SingleInstanceLock":
        if self._acquired:
            return self
        if self.path in self._active_paths:
            raise SingleInstanceError(f"app lock is already held: {self.path}")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            self._lock_handle(handle)
            handle.seek(0)
            handle.truncate()
            handle.write(f"pid={os.getpid()}\n")
            handle.flush()
        except OSError as exc:
            handle.close()
            raise SingleInstanceError(f"app lock is already held: {self.path}") from exc

        self._handle = handle
        self._acquired = True
        self._active_paths.add(self.path)
        return self

    def release(self) -> None:
        if not self._acquired or self._handle is None:
            return
        try:
            self._unlock_handle(self._handle)
        finally:
            self._handle.close()
            self._handle = None
            self._acquired = False
            self._active_paths.discard(self.path)

    @staticmethod
    def _lock_handle(handle: TextIO) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write("\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_handle(handle: TextIO) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
