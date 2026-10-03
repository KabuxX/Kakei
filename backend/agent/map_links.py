"""Recognize only documented pin/viewport URL forms, never generic numbers."""
import re
from urllib.parse import urlsplit, parse_qs, unquote
from services.coordinate_evidence import valid_coordinates

def parse_map_link(url):
    try:
        u=urlsplit(url); host=(u.hostname or '').lower(); q=parse_qs(u.query)
        if u.scheme!='https' or any(len(v)!=1 for v in q.values()):return None
        raw=unquote(u.path); kind='map_viewport'; label=None; pair=None
        if host in ('www.google.com','maps.google.com','www.google.co.jp','maps.google.co.jp') and '/maps' in raw:
            pairs=re.findall(r'!3d(-?[\d.]+)!4d(-?[\d.]+)',raw+unquote(u.query))
            if len(pairs)>1:return None
            if pairs:pair=pairs[0];kind='map_pin_url'
            elif 'query' in q and 'query_place_id' not in q:pair=q['query'][0].split(',');kind='map_pin_url'
            else:
                m=re.search(r'/@(-?[\d.]+),(-?[\d.]+),',raw)
                if m:pair=m.groups()
        elif host=='maps.apple.com' and 'll' in q:
            pair=q['ll'][0].split(',');label=q.get('q',[None])[0]
            if label:kind='map_pin_url'
        elif host in ('www.openstreetmap.org','openstreetmap.org'):
            if 'mlat' in q and 'mlon' in q:pair=[q['mlat'][0],q['mlon'][0]];kind='map_pin_url'
            else:
                m=re.fullmatch(r'map=[\d.]+/(-?[\d.]+)/(-?[\d.]+)',u.fragment)
                if m:pair=m.groups()
        if not pair or len(pair)!=2:return None
        coords=[float(pair[1]),float(pair[0])]
        if not valid_coordinates(coords):return None
        return {'coordinates':coords,'kind':kind,'targetName':label}
    except (ValueError,TypeError):return None
