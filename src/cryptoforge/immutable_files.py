"""Install fully written local evidence once; preserve existing original bytes."""
import os,tempfile
from pathlib import Path


def install_original(path,raw):
    path=Path(path)
    if path.exists():
        if path.read_bytes()!=raw:raise ValueError('original collection file has changed')
        return
    path.parent.mkdir(parents=True,exist_ok=True);temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
            temporary=Path(stream.name);stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
