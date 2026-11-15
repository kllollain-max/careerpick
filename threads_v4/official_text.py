"""Extract auditable snippets from official HTML, without treating matches as approval."""
from html.parser import HTMLParser
import re

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
        self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ("script","style","noscript"):
            self.skip+=1
    def handle_endtag(self,tag):
        if tag in ("script","style","noscript") and self.skip:
            self.skip-=1
    def handle_data(self,data):
        if not self.skip:
            self.parts.append(data)

def extract(html, *, terms=None, window=100):
    if not isinstance(html,bytes) or len(html)>2_000_000:
        raise ValueError("HTML_BYTES_INVALID")
    parser=TextExtractor()
    parser.feed(html.decode("utf-8",errors="replace"))
    text=re.sub(r"\s+"," "," ".join(parser.parts)).strip()
    terms=terms or ["한국조세재정연구원","연구위원","10명","정규직","11월 30일","11.30","정정","취소","접수"]
    evidence={}
    if window < 0 or window > 500:
        raise ValueError("INVALID_WINDOW")
    for term in terms:
        m=re.search(re.escape(term),text,re.I)
        evidence[term]={"found":bool(m),"snippet":text[max(0,m.start()-window):m.end()+window] if m else None}
    return {"length":len(text),"evidence":evidence,"status":"SNIPPETS_ONLY_NOT_VERIFIED"}
