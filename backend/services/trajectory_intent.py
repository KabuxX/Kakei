"""Recognize a current creation instruction, without executing quoted data."""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

@dataclass(frozen=True)
class CreationIntent:
    date: str | None
    needs_date: bool = False

def parse_creation_intent(text,*,today):
    if not isinstance(text,str):
        return None
    text=unicodedata.normalize('NFKC',text)
    if '軌跡' not in text or not re.search(r'作って|作りたい|(?:作成|生成)(?:して|する(?:[。!！]|$)|を(?:お願い|実行))|作る(?:[。!！]|$)|(?:作成|生成)(?:[。!！]|$)',text):
        return None
    if re.search(r'作らない|作成しない|作るな|保存しない|キャンセル|方法|仕組み|意味|説明|という指示|という例|サンプル|テストコード',text):
        return None
    dates=set(); invalid=False
    for match in re.finditer(r'(\d{4})[-年](\d{1,2})[-月](\d{1,2})(?:日)?',text):
        try:
            dates.add(date(*(int(v) for v in match.groups())).isoformat())
        except ValueError:
            invalid=True
    if '今日' in text:
        dates.add(today.isoformat())
    if '昨日' in text:
        dates.add((today-timedelta(days=1)).isoformat())
    if len(dates)!=1 or invalid:
        return CreationIntent(None,True)
    return CreationIntent(next(iter(dates)))
