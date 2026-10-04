"""Recognize one affirmative current creation instruction, excluding quoted data."""
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

@dataclass(frozen=True)
class CreationIntent:
    date: str | None
    needs_date: bool = False


def _instruction_text(text):
    text=re.sub(r'```.*?(?:```|$)', ' ', text, flags=re.DOTALL)
    text=re.sub(r'^\s*>.*$', ' ', text, flags=re.MULTILINE)
    for opening,closing in [('「','」'),('『','』'),('“','”'),('"','"'),("'","'"),('`','`')]:
        text=re.sub(re.escape(opening)+r'.*?(?:'+re.escape(closing)+r'|$)', ' ', text, flags=re.DOTALL)
    return text


def parse_creation_intent(text,*,today):
    if not isinstance(text,str):
        return None
    text=_instruction_text(unicodedata.normalize('NFKC',text))
    end=r'(?=[。!?、,\s]|$)'
    request=r'(?:ください|下さい|ほしい(?:です)?|欲しい(?:です)?|くれ(?:ませんか|る)?|もらえますか)?'
    action=(r'(?:作って|(?:作成|生成)して|軌跡に(?:追加|登録)して)'+request+end
            +r'|(?:作りたい|(?:作成|生成)したい)(?:です)?'+end
            +r'|(?:作成|生成)を(?:お願い(?:します|したい(?:です)?)?|実行して)'+end
            +r'|(?:作る|(?:作成|生成)する|作成|生成)(?=[。!\s]|$)')
    if '軌跡' not in text or not re.search(action,text):
        return None
    prohibited=r'作らない|作るな|(?:作成|生成|追加|登録)しない|保存しない|キャンセル|方法|仕組み|意味|という指示|という例|サンプル|テストコード|(?:作って|(?:作成|生成|追加|登録)して)(?:は(?:いけ|駄目|ダメ)|も(?:大丈夫|いい|良い|よい|よろしい|問題ない))'
    if re.search(prohibited,text):
        return None
    dates=set();invalid=False
    date_pattern=r'(\d{4})[-年](\d{1,2})[-月](\d{1,2})(?:日)?'
    for match in re.finditer(date_pattern,text):
        try:
            dates.add(date(*(int(v) for v in match.groups())).isoformat())
        except ValueError:
            invalid=True
    remaining=re.sub(date_pattern,' ',text)
    # A partial second day/month or numeric range is not silently discarded.
    additional_date=bool(re.search(r'\d{1,2}(?:月(?:\d{1,2}日)?|日)|(?:~|〜|から|と|、|,)\s*\d{1,2}(?:日)?',remaining))
    if '今日' in text:
        dates.add(today.isoformat())
    if '昨日' in text:
        dates.add((today-timedelta(days=1)).isoformat())
    if len(dates)!=1 or invalid or additional_date:
        return CreationIntent(None,True)
    return CreationIntent(next(iter(dates)))
