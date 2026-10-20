"""Cooperative process lock shared by the API and maintenance commands."""
import os
from contextlib import contextmanager
from pathlib import Path


def lock_path(database_url, artifact_dir):
    from sqlalchemy.engine import make_url
    url = make_url(database_url)
    parent = Path(url.database).resolve().parent if url.get_backend_name() == 'sqlite' and url.database != ':memory:' else Path(artifact_dir).resolve()
    return parent / '.cvti-workspace.lock'


def _acquire_windows_lock(handle, *, shared):
    """Return an unlock callback; the CRT's LK_NBRLCK is not a shared lock."""
    import ctypes
    from ctypes import wintypes
    import msvcrt

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ('Internal', ctypes.c_size_t),
            ('InternalHigh', ctypes.c_size_t),
            ('Offset', wintypes.DWORD),
            ('OffsetHigh', wintypes.DWORD),
            ('hEvent', wintypes.HANDLE),
        ]

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.LockFileEx.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped),
    ]
    kernel32.LockFileEx.restype = wintypes.BOOL
    kernel32.UnlockFileEx.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, ctypes.POINTER(Overlapped),
    ]
    kernel32.UnlockFileEx.restype = wintypes.BOOL
    native_handle = msvcrt.get_osfhandle(handle.fileno())
    overlapped = Overlapped()
    # LOCKFILE_FAIL_IMMEDIATELY (1), plus LOCKFILE_EXCLUSIVE_LOCK (2)
    # for maintenance/worker ownership. The first byte may be beyond EOF.
    flags = 1 | (0 if shared else 2)
    if not kernel32.LockFileEx(native_handle, flags, 0, 1, 0, ctypes.byref(overlapped)):
        raise ctypes.WinError(ctypes.get_last_error())

    def release():
        if not kernel32.UnlockFileEx(native_handle, 0, 1, 0, ctypes.byref(overlapped)):
            raise ctypes.WinError(ctypes.get_last_error())

    return release


@contextmanager
def workspace_lock(database_url, artifact_dir, *, shared=False, name='.cvti-workspace.lock'):
    path = lock_path(database_url, artifact_dir).with_name(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        try:
            if os.name == 'nt':
                release = _acquire_windows_lock(handle, shared=shared)
            else:
                import fcntl
                fcntl.flock(handle, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Workspace is in use. Stop the API and other cvti commands before maintenance.') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                release()
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_UN)
