from decimal import Decimal
import json
import pytest

from cryptoforge.market_data import Candle
from cryptoforge.sqlite_archive import SQLiteArchive


class Client:
    calls=0
    fail=False
    def get_klines(self,symbol,interval,limit,*,start_ms,end_ms):
        self.calls+=1
        if self.fail and self.calls==2:
            self.fail=False
            raise RuntimeError('interrupted')
        timestamps=[i*300000 for i in range(1200) if start_ms<=i*300000<=end_ms][-1000:]
        return [Candle(symbol,interval,t,Decimal('1.00000001'),Decimal(2),Decimal(1),
                       Decimal('1.00000002'),Decimal('0.000000001'),Decimal('0.000000002')) for t in timestamps]


def test_streaming_archive_resume_precision_and_manifest(tmp_path):
    archive=SQLiteArchive(tmp_path/'history.sqlite');client=Client();client.fail=True
    try:
        with pytest.raises(RuntimeError,match='interrupted'):
            archive.download(client,'BTCUSDT','5',0,1200*300000,pause=0)
        report=archive.download(client,'BTCUSDT','5',0,1200*300000,pause=0)
        assert report['candles']==1200 and report['status']=='valid'
        rows=archive.read_manifest(report,limit=10)
        assert len(rows)==10 and rows[0].open==Decimal('1.00000001')
        assert rows[0].volume==Decimal('0.000000001')
        calls=client.calls
        repeated=archive.download(client,'BTCUSDT','5',0,1200*300000,pause=0)
        assert client.calls==calls
        assert repeated['sha256']==report['sha256']
        archive.db.execute('UPDATE candles SET volume=? WHERE start_ms=0',('0.1',));archive.db.commit()
        with pytest.raises(ValueError,match='changed'):
            archive.read_manifest(report,limit=10)
    finally:
        archive.close()


def test_incomplete_ranges_are_explicit_and_refused_by_reader(tmp_path):
    archive=SQLiteArchive(tmp_path/'history.sqlite')
    try:
        report=archive.report('BTCUSDT','5',0,600000)
        assert report['missing_candles']==2
        assert report['gaps']==[{'start_ms':0,'end_ms_exclusive':600000,'missing_candles':2}]
        with pytest.raises(ValueError,match='incomplete'):
            archive.read_manifest(report,limit=1)
    finally:
        archive.close()


def test_continuous_segments_do_not_bridge_a_missing_candle(tmp_path):
    archive=SQLiteArchive(tmp_path/'history.sqlite')
    try:
        report=archive.download(Client(),'BTCUSDT','5',0,1200*300000,pause=0)
        archive.db.execute('DELETE FROM candles WHERE start_ms=?',(600*300000,));archive.db.commit()
        incomplete=archive.report('BTCUSDT','5',0,1200*300000)
        segments=archive.continuous_segments(incomplete)
        assert len(segments)==2
        assert [s['candles'] for s in segments]==[600,599]
        assert all(s['status']=='valid' for s in segments)
        assert segments[0]['requested_end_ms_exclusive']==600*300000
        assert segments[1]['requested_start_ms']==601*300000
        assert len(archive.read_manifest(segments[1],limit=1000))==599
    finally:
        archive.close()
