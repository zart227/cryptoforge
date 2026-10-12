import json
import pytest

from cryptoforge.announcement_sources import extract_article,classify_article


def html(article):
    data={'props':{'pageProps':{'articleDetail':article}}}
    return ('<script id="__NEXT_DATA__" type="application/json">'+json.dumps(data)+'</script>').encode()


def test_rich_and_html_body_sources_preserve_metadata():
    article={'title':'Bybit to List X on Spot','date':'2025-11-01T08:00:00Z',
             'content':{'json':{'children':[{'text':'Spot trading starts at 10AM UTC.'}]}}}
    parsed=extract_article(html(article))
    assert parsed['published_at']==article['date']
    assert parsed['body_available']
    assert classify_article(parsed['title'],parsed['body'])=='spot_source_pending_event_review'
    article['content']={'json':None};article['content_html']='<p>Spot: trading ends.</p>'
    assert extract_article(html(article))['body']=='Spot: trading ends.'


def test_market_classification_never_confuses_spot_token_or_mixed_notice():
    assert classify_article('SPOTUSDT Perpetual Contract','Spot ticker')=='excluded_non_spot'
    assert classify_article('Spot pairs update','Bybit EU will adjust tick sizes.')=='excluded_other_venue'
    assert classify_article('Delisting X','Spot: trading ends. Futures trading also ends.')=='mixed_requires_section_review'
    assert classify_article('Bybit to List X on Spot','')=='market_or_body_unconfirmed'
    with pytest.raises(ValueError):extract_article(b'<html>no article</html>')


def test_tables_support_both_announcement_generations():
    from cryptoforge.announcement_sources import article_tables
    modern={'content':{'json':None},'content_html':'<table><tr><th>Pair</th><th>Tick</th></tr><tr><td>DOTUSDT</td><td>0.0001</td></tr></table>'}
    assert article_tables(modern)==[['Pair','Tick'],['DOTUSDT','0.0001']]
    legacy={'content':{'json':{'children':[{'type':'tr','children':[
        {'children':[{'text':'DOTUSDT'}]},{'children':[{'text':'0.0001'}]}]}]}}}
    assert article_tables(legacy)==[['DOTUSDT','0.0001']]
