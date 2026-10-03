"""Coordinate authority comes from fetched, store-bound public material."""
import copy,json,re,uuid
from html.parser import HTMLParser
from urllib.parse import urljoin
from agent.map_links import parse_map_link
from agent.place_matching import compact
from agent.place_http import PlaceProviderError
from agent.limits import SearchLimit
from services.coordinate_evidence import valid_coordinates
from services.merchant_address import addresses_match, normalize_address
from services.place_evidence import safe_source_url
from services.validation import ValidationError

class Node:
    def __init__(self,tag,attrs=()):self.tag=tag;self.attrs=dict(attrs);self.children=[];self.parts=[]
    def text(self):return ' '.join(self.parts+[n.text() for n in self.children if n.tag not in ('script','style')])
    def walk(self):
        yield self
        for n in self.children:yield from n.walk()
class Document(HTMLParser):
    def __init__(self,body):
        super().__init__(convert_charrefs=True);self.root=Node('root');self.stack=[self.root];self.feed(body)
    def handle_starttag(self,tag,attrs):
        n=Node(tag,attrs);self.stack[-1].children.append(n)
        if tag not in ('meta','link','img','input','br','hr','source','area','wbr'):self.stack.append(n)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:self.stack=self.stack[:i];break
    def handle_data(self,text):self.stack[-1].parts.append(text)

def matches(row,name,address):
    expected=compact(row['name']);branch=compact(row.get('branch',''))
    return expected in compact(name) and (not branch or branch in compact(name)) and (addresses_match(row['address'],address) or bool(re.search(re.escape(normalize_address(row['address']))+r'(?![\d-])',normalize_address(address))))

def empty():return {'candidates':[],'anchors':[],'unresolved':[],'identityVerified':False,'verifiedHints':[],'links':[],'pages':[]}

def emit(out,row,source,kind,excerpt,coords):
    observation={'sourceId':source['id'],'kind':kind,'excerpt':excerpt[:2048],'coordinates':coords}
    if row.get('role')=='anchor':
        out['anchors'].append({'name':row['name'],'address':row['address'],'coordinates':coords,'sources':[copy.deepcopy(source)],'observations':[observation]});return
    if kind=='map_viewport':return
    out['candidates'].append({'id':str(uuid.uuid4()),'name':row['name'],'address':row['address'],'coordinates':coords,'sources':[copy.deepcopy(source)],'sourceUrl':source['url'],'attribution':source['title'],'matchReasons':['store_and_address_verified'],'coordinateEvidence':{'version':1,'status':'published','method':kind,'sourceIds':[source['id']],'retrievedAt':source['retrievedAt'],'precision':'point','note':'掲載位置。実際の入口・誤差範囲は未確認。','verification':'needs_confirmation','observations':[observation]}})

def verify_page(row,page,source):
    out=empty();body=page['body'].decode('utf-8',errors='replace');doc=Document(body)
    def structured(value):
        if isinstance(value,list):
            for v in value:structured(v)
        elif isinstance(value,dict):
            addr=value.get('address','')
            if isinstance(addr,dict):addr=''.join(str(addr.get(k,'')) for k in ('addressRegion','addressLocality','streetAddress'))
            if matches(row,str(value.get('name','')),str(addr)):
                out['identityVerified']=True;geo=value.get('geo',{})
                if isinstance(geo,dict):
                    try:
                        values=[geo['longitude'],geo['latitude']]
                        coords=[float(v) for v in values] if all(type(v) in (str,int,float) for v in values) else None
                    except (KeyError,ValueError,TypeError):coords=None
                    if valid_coordinates(coords):emit(out,row,source,'structured_geo',json.dumps({k:value[k] for k in ('name','address','geo') if k in value},ensure_ascii=False),coords)
            if '@graph' in value:structured(value['@graph'])
    if page['content_type'] in ('application/json','application/ld+json','application/geo+json'):
        try:structured(json.loads(body))
        except ValueError:pass
    for n in doc.root.walk():
        if n.tag=='script' and n.attrs.get('type')=='application/ld+json':
            try:structured(json.loads(''.join(n.parts)))
            except ValueError:pass
    # Only the smallest matching record may supply coordinates or outgoing links.
    # A matching ancestor also contains neighbouring stores and is not authority.
    matching=[n for n in doc.root.walk() if n.tag in ('root','body','main','div','article','section','li','tr') and matches(row,n.text(),n.text())]
    matching_set=set(matching)
    units=[n for n in matching if not any(child in matching_set for child in list(n.walk())[1:])]
    records=[]
    for unit in units:
        headings=[child for child in unit.children if child.tag in ('h1','h2','h3','h4','h5','h6')]
        if len(headings)<2:records.append(unit);continue
        # Bare sibling headings are also record boundaries on simple listings.
        section=Node('record')
        for child in unit.children:
            if child in headings:
                if section.children:records.append(section)
                section=Node('record')
            section.children.append(child)
        if section.children:records.append(section)
    for n in records:
        text=n.text()
        if not matches(row,text,text):continue
        out['identityVerified']=True
        for hint in row.get('hints',[]):
            if source['id'] in hint['relationSourceIds'] and compact(hint['relationExcerpt']) in compact(text) and hint not in out['verifiedHints']:out['verifiedHints'].append(copy.deepcopy(hint))
        for m in re.finditer(r'(?:緯度|latitude|lat)\s*[:：=]?\s*(-?[\d.]+)[\s,、・;/]*?(?:経度|longitude|lon|lng)\s*[:：=]?\s*(-?[\d.]+)',text,re.I):
            try:coords=[float(m[2]),float(m[1])]
            except ValueError:continue
            if valid_coordinates(coords):emit(out,row,source,'page_text',m[0],coords)
        for link in n.walk():
            if link.tag!='a' or not link.attrs.get('href'):continue
            url=urljoin(page['final_url'],link.attrs['href'])
            try:safe_source_url(url)
            except ValidationError:continue
            parsed=parse_map_link(url)
            if parsed and parsed['targetName'] and compact(parsed['targetName']) not in compact(row['name']):continue
            out['links'].append(url)
            if parsed:emit(out,row,source,parsed['kind'],url,parsed['coordinates'])
    return out

class WebCoordinateVerifier:
    def __init__(self,pages,budget):self.pages=pages;self.budget=budget;self.cache={}
    async def verify(self,row,*,timeout):
        result=empty();queue=[(s['url'],s,None) for s in row['sources']];seen=set()
        for url in row.get('urls',[]):
            if url in row.get('discoveredUrls',[]) and url not in {s['url'] for s in row['sources']}:
                queue.append((url,{'id':str(uuid.uuid4()),'title':'Web検索で取得した公開ページ','url':url,'kind':'unknown','retrievedAt':row['sources'][0]['retrievedAt']},None))
        while queue and len(seen)<16:
            url,source,context=queue.pop(0)
            if url in seen:continue
            seen.add(url)
            try:
                if url not in self.cache:self.cache[url]=await self.pages.fetch(url,allowed_urls=seen,budget=self.budget,timeout=timeout)
                page=self.cache[url]
            except (PlaceProviderError,SearchLimit) as e:
                code=e.code if isinstance(e,PlaceProviderError) else str(e)
                records=getattr(e,'page_requests',[{'url':url,'result':code}])
                result['pages'].extend({**record,'sourceId':source['id']} for record in records)
                result['unresolved'].append(code)
                if isinstance(e,SearchLimit):break
                continue
            verified=verify_page(row,page,source)
            records=page.get('requests',[{'url':url,'finalUrl':page['final_url'],'redirects':page['redirects'],'result':'read'}])
            result['pages'].extend({**record,'sourceId':source['id'],'verification':'verified' if verified['identityVerified'] or context else 'identity_unverified'} for record in records)
            if context:
                parsed=parse_map_link(page['final_url'])
                if parsed and (not parsed['targetName'] or compact(parsed['targetName']) in compact(row['name'])):
                    # The original page proves which store this outgoing map link belongs to.
                    obs_source={**source,'url':page['final_url'],'retrievedAt':page['retrieved_at']}
                    emit(verified,row,obs_source,parsed['kind'],page['final_url'],parsed['coordinates'])
                    for candidate in verified['candidates']:
                        candidate['sources'].append(copy.deepcopy(context));candidate['coordinateEvidence']['sourceIds'].append(context['id'])
                    for anchor in verified['anchors']:anchor['sources'].append(copy.deepcopy(context))
            for key in ('candidates','anchors','unresolved','verifiedHints'):result[key].extend(verified[key])
            result['identityVerified']|=verified['identityVerified']
            for link in verified['links']:
                # Follow only outgoing map service links; ordinary pages must be search sources.
                from urllib.parse import urlsplit
                if urlsplit(link).hostname not in ('maps.app.goo.gl','maps.apple.com','www.google.com','maps.google.com','www.openstreetmap.org'):continue
                if parse_map_link(link):continue
                child={**source,'id':str(uuid.uuid4()),'url':link}
                queue.append((link,child,source))
        return result
