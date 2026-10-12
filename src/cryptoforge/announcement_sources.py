"""Extract source metadata; classification is not factual event ingestion."""
from html.parser import HTMLParser
import json
import re


class _Text(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,data):self.parts.append(data)


def rich_text(node):
    if not isinstance(node,dict):return ''
    return node.get('text','')+' '.join(rich_text(child) for child in node.get('children',[]))


def extract_article(raw: bytes) -> dict:
    match=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',raw.decode(),re.S)
    if not match:raise ValueError('source has no article data')
    article=json.loads(match.group(1)).get('props',{}).get('pageProps',{}).get('articleDetail')
    if not article or not article.get('title') or not article.get('date'):
        raise ValueError('source lacks title/publication metadata')
    body=rich_text((article.get('content') or {}).get('json'))
    if not body.strip():
        parser=_Text();parser.feed(article.get('content_html') or '');body=' '.join(parser.parts)
    return {'title':article['title'],'published_at':article['date'],'body':body,
            'body_available':bool(body.strip()),'article':article}


def classify_article(title: str,body: str) -> str:
    title=title.casefold();body=body.casefold()
    if 'bybit eu' in title or 'bybit eu' in body:
        return 'excluded_other_venue'
    if any(term in title for term in ('perpetual','futures','bybit alpha')):
        return 'excluded_non_spot'
    spot_in_title=any(term in title for term in ('on spot','spot pair','spot trading','spot and margin'))
    spot_section=any(term in body for term in ('spot:', 'spot trading', 'spot platform','spot pairs','spot and margin'))
    derivatives_in_body=any(term in body for term in ('perpetual contract','futures trading'))
    if (spot_in_title or spot_section) and derivatives_in_body:
        return 'mixed_requires_section_review'
    if body.strip() and (spot_in_title or spot_section):
        return 'spot_source_pending_event_review'
    return 'market_or_body_unconfirmed'


class _Tables(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        if tag in ('td','th'):self.cell=''
    def handle_data(self,value):
        if self.cell is not None:self.cell+=value
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.row is not None and self.cell is not None:
            self.row.append(self.cell.strip());self.cell=None
        if tag=='tr' and self.row:self.rows.append(self.row);self.row=None


def article_tables(article: dict) -> list[list[str]]:
    def walk(node):
        if isinstance(node,dict):
            yield node
            for child in node.get('children',[]):yield from walk(child)
    root=(article.get('content') or {}).get('json')
    rows=[[rich_text(cell).strip() for cell in node.get('children',[])] for node in walk(root) if node.get('type')=='tr']
    if not rows:
        parser=_Tables();parser.feed(article.get('content_html') or '');rows=parser.rows
    return rows
