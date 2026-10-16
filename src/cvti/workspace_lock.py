"""Cooperative process lock shared by the API and maintenance commands."""
import os
from contextlib import contextmanager
from pathlib import Path


def lock_path(database_url, artifact_dir):
    from sqlalchemy.engine import make_url
    url = make_url(database_url)
    parent = Path(url.database).resolve().parent if url.get_backend_name() == 'sqlite' and url.database != ':memory:' else Path(artifact_dir).resolve()
    return parent / '.cvti-workspace.lock'


@contextmanager
def workspace_lock(database_url, artifact_dir, *, shared=False, name='.cvti-workspace.lock'):
    path = lock_path(database_url, artifact_dir).with_name(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), (msvcrt.LK_NBRLCK if shared else msvcrt.LK_NBLCK), 1)
            else:
                import fcntl
                fcntl.flock(handle, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Workspace is in use. Stop the API and other cvti commands before maintenance.') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_UN)
