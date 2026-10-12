import json
import pytest
from cryptoforge.atomic_reports import write_json_report


def test_invalid_report_preserves_previous_complete_evidence(tmp_path):
    path=tmp_path/'report.json'
    write_json_report(path,{'status':'complete'})
    with pytest.raises(ValueError):write_json_report(path,{'value':float('nan')})
    assert json.loads(path.read_bytes())=={'status':'complete'}
    assert list(tmp_path.iterdir())==[path]


def test_replace_failure_preserves_previous_report_and_cleans_temporary(tmp_path,monkeypatch):
    path=tmp_path/'report.json'
    write_json_report(path,{'status':'complete'})
    def fail(*args):raise OSError('replace failure')
    monkeypatch.setattr('cryptoforge.atomic_reports.os.replace',fail)
    with pytest.raises(OSError):write_json_report(path,{'status':'new'})
    assert json.loads(path.read_bytes())=={'status':'complete'}
    assert list(tmp_path.iterdir())==[path]
    assert path.stat().st_mode & 0o777 == 0o600
