import json
from urllib.parse import urlparse,parse_qs

from scripts.inventory_announcement_categories import relevant_title,main


def test_candidate_filter_separates_products_and_includes_spot_pairs():
    assert relevant_title('Updates on tick size for Spot pairs')
    assert relevant_title('New Spot Trading Pairs: ABC/USDT')
    assert relevant_title('Changes to maximum order size for limit and market orders')
    assert not relevant_title('New listing: SPOTUSDT Perpetual Contract')
    assert not relevant_title('Bybit Alpha listing')


def test_pagination_stops_at_study_boundary_and_records_evidence(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    directory=tmp_path/'.local/state';directory.mkdir(parents=True)
    (directory/'historical-source-inventory.json').write_text(json.dumps({'candidates':[]}))
    import scripts.inventory_announcement_categories as inventory
    monkeypatch.setattr(inventory,'ROOT',tmp_path/'sources')
    monkeypatch.setattr(inventory,'OUTPUT',directory/'category.json')
    monkeypatch.setattr(inventory.time,'sleep',lambda duration:None)
    calls=[]
    def fake_open(request,timeout):
        query=parse_qs(urlparse(request.full_url).query);page=int(query['page'][0]);calls.append(page)
        stamp=inventory.START+100 if page==1 else inventory.START-100
        props={'initialPage':page,'articleInitEntity':{'total':40,'list':[
            {'objectID':str(page),'title':'Bybit to List ABC on Spot','date_timestamp':stamp,
             'is_top':False,'url':'/article/abc-spot/'}]}}
        class Response:
            def read(self):return ('<script id="__NEXT_DATA__">'+json.dumps({'props':{'pageProps':props}})+'</script>').encode()
        return Response()
    monkeypatch.setattr(inventory,'urlopen',fake_open)
    main()
    result=json.loads((directory/'category.json').read_text())
    assert len(result['categories'])==4
    assert all(row['stop_reason']=='passed_study_start' for row in result['categories'])
    assert calls==[1,2]*4
    assert result['candidate_total']==1
    assert result['index_completeness_proven'] is False
