"""Replace mutable diagnostic reports without exposing partial or public files."""
import json
import os
from pathlib import Path
import tempfile


def write_json_report(path, payload, *, default=None):
    # Serialize before touching the destination; invalid numbers are not evidence.
    raw=json.dumps(payload,indent=2,allow_nan=False,default=default).encode('utf-8')
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
            temporary=Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
