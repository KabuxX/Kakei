"""Resolve a physical visit without asking the user to select a candidate."""
import asyncio
import re
import time
import unicodedata
from dataclasses import dataclass, replace
from agent.google_places import GooglePlacesError
from services.merchant_address import japanese_parts

BRANDS = ('セブンイレブン','ファミリーマート','ローソン','ドトールコーヒーショップ','ドトール','スターバックス')

@dataclass(frozen=True)
class VisitInput:
    transaction_id: str
    label: str
    address: str | None

@dataclass(frozen=True)
class VisitResolution:
    transaction_id: str
    provider_place_id: str | None = None
    coordinates: tuple[float,float] | None = None
    obtained_at: float | None = None
    reason: str | None = None


def normalize_name(value):
    value=unicodedata.normalize('NFKC',value).casefold()
    return re.sub(r'[\s‐‑‒–—−-]+','',value)


def address_core(value):
    value=japanese_parts(value)[1]
    value=unicodedata.normalize('NFKC',value).casefold()
    digits={c:i for i,c in enumerate('〇一二三四五六七八九')}
    def number(match):
        raw=match[1]
        if '十' in raw:
            left,_,right=raw.partition('十')
            n=digits.get(left,1)*10+digits.get(right,0)
        else:
            n=int(''.join(str(digits[c]) for c in raw))
        return str(n)+match[2]
    value=re.sub(r'([〇一二三四五六七八九十]+)(丁目|番地|番(?!町)|号)',number,value)
    value=re.sub(r'[‐‑‒–—−ー]','-',value)
    value=re.sub(r'(?<=\d)(丁目|番地|番(?!町)|号)','-',value)
    value=re.sub(r'(?<=\d)の(?=\d)','-',value)
    value=re.sub(r'[\s,、]+','',value).strip('-')
    if re.match(r'^[^\d]*[都道府県市区町村][^\d]*\d',value):
        match=re.match(r'^(.*?\d+(?:-\d+)+)',value)
        if match:
            return match[1]
    return value


def _brand(label):
    return next((brand for brand in BRANDS if label.startswith(brand)),None)


def _matches(visit, candidate):
    expected=normalize_name(visit.label); actual=normalize_name(candidate.display_name)
    brand=_brand(expected)
    identity = actual == expected or (brand == expected and actual.startswith(brand) and bool(visit.address))
    if not identity or not candidate.types or all(t in {'street_address','premise','subpremise','locality','political','postal_code','route','sublocality'} for t in candidate.types):
        return False
    if visit.address:
        expected_postal,_=japanese_parts(visit.address)
        actual_postal,_=japanese_parts(candidate.formatted_address)
        if expected_postal and actual_postal and expected_postal!=actual_postal:
            return False
        return address_core(visit.address) == address_core(candidate.formatted_address)
    return True


def query_variants(visit):
    label=unicodedata.normalize('NFKC',visit.label).strip()
    address=visit.address or ''
    core=address_core(address) if address else ''
    normalized=label.replace('‐','-').replace('−','-')
    locality=re.split(r'\d',core,maxsplit=1)[0] if core else ''
    values=[f'{visit.label} {address}'.strip(), f'{normalized} {unicodedata.normalize("NFKC",address)}'.strip(), f'{normalized} {core}'.strip(), f'{normalized} {locality}'.strip()]
    return list(dict.fromkeys(values))


class VisitResolver:
    def __init__(self, client, *, deadline, clock=time.monotonic):
        self.client,self.deadline,self.clock=client,deadline,clock
        self._semaphore=asyncio.Semaphore(3)
        self._jobs={}
        self._stop_reason=None

    async def resolve_many(self, visits):
        return await asyncio.gather(*(self.resolve(visit) for visit in visits))

    async def resolve(self, visit):
        key=(visit.label,visit.address)
        if key not in self._jobs:
            self._jobs[key]=asyncio.create_task(self._resolve(visit))
        return replace(await self._jobs[key],transaction_id=visit.transaction_id)

    async def _resolve(self, visit):
        failure=lambda reason: VisitResolution(visit.transaction_id,reason=reason)
        name=normalize_name(visit.label)
        if not name or (_brand(name)==name and not visit.address):
            return failure('insufficient_identity')
        variants=query_variants(visit); attempts=0; retried=False
        last_reason='not_found'
        async with self._semaphore:
            for query in variants:
                while attempts<4:
                    if self._stop_reason:
                        return failure(self._stop_reason)
                    remaining=self.deadline-self.clock()
                    if remaining<=0:
                        return failure('budget_exceeded')
                    attempts+=1
                    try:
                        candidates=await asyncio.wait_for(self.client.search_text(query,region_code='JP' if visit.address and re.search(r'[都道府県]',visit.address) else None),min(8,remaining))
                    except (GooglePlacesError,TimeoutError) as error:
                        code=error.code if isinstance(error,GooglePlacesError) else 'unavailable'
                        if code=='configuration':
                            self._stop_reason='provider_configuration'
                            return failure(self._stop_reason)
                        last_reason='budget_exceeded' if self.clock()>=self.deadline else 'provider_unavailable'
                        delay=getattr(error,'retry_after',None) or 0
                        if code in ('rate_limited','unavailable') and not retried and attempts<4 and delay<=1 and self.deadline-self.clock()>delay:
                            retried=True
                            if delay:
                                await asyncio.sleep(delay)
                            continue
                        return failure(last_reason)
                    unique={c.place_id:c for c in candidates if _matches(visit,c)}
                    if len(unique)>1:
                        return failure('ambiguous')
                    if len(unique)==1:
                        candidate=next(iter(unique.values()))
                        if candidate.coordinates is not None:
                            return VisitResolution(visit.transaction_id,candidate.place_id,candidate.coordinates,time.time())
                        last_reason='missing_coordinates'
                    elif candidates:
                        last_reason='identity_mismatch'
                    break
                if attempts>=4:
                    break
        return failure(last_reason)
