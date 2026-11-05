import json,sqlite3
from decimal import Decimal
import pytest
from scripts.audit_execution_cache import audit_cache
from test_live_trade_journal import fill


def test_saved_execution_audit_reconciles_partial_basis_and_retains_original_input(tmp_path):
    cache=tmp_path/'cache.sqlite';output=tmp_path/'audit.json'
    fills=[fill('b','Buy','10','2',fee='1'),fill('s','Sell','4','3',fee='.2',time=2000)]
    with sqlite3.connect(cache) as db:
        db.execute('create table executions(exec_id text primary key,payload text)')
        db.executemany('insert into executions values(?,?)',[(row['execId'],json.dumps(row)) for row in fills])
    report=audit_cache(cache,output)
    assert report['net_pnl_quote']==Decimal('3.4')
    assert report['open_cost_basis']==Decimal('12.6')
    assert not report['current_wallet_verified'] and not report['live_promotion_allowed']
    from cryptoforge.training_snapshot import load_runtime_sources
    assert load_runtime_sources(report['runtime_source_bundle'],report['implementation_hashes'])['automatically_execute_archived_code'] is False
    from pathlib import Path
    snapshot=Path(report['input_reference']);snapshot.write_text('[]')
    with pytest.raises(ValueError,match='immutable'):audit_cache(cache,output)
