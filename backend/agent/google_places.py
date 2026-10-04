"""Bounded Places API (New) requests. Returned Google content is ephemeral."""
import asyncio
import json
import math
import os
import re
from dataclasses import dataclass

import httpx

SEARCH_FIELDS = 'places.id,places.displayName,places.formattedAddress,places.addressComponents,places.location,places.types,places.googleMapsUri,places.attributions'
DETAIL_FIELDS = 'id,location,displayName,formattedAddress,googleMapsUri,attributions'


class GooglePlacesError(Exception):
    def __init__(self, code, retry_after=None):
        self.code, self.retry_after = code, retry_after
        super().__init__(code)


@dataclass(frozen=True)
class GoogleCandidate:
    place_id: str
    display_name: str
    formatted_address: str
    address_components: list
    coordinates: tuple[float, float] | None
    types: list
    maps_uri: str | None
    attributions: list

    @classmethod
    def from_payload(cls, value):
        if not isinstance(value, dict) or not valid_place_id(value.get('id')):
            raise GooglePlacesError('invalid_response')
        location = value.get('location')
        coordinates = None
        if location is not None:
            if not isinstance(location, dict):
                raise GooglePlacesError('invalid_response')
            coordinates = (location.get('longitude'), location.get('latitude'))
            if any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in coordinates) or not (-180 <= coordinates[0] <= 180 and -90 <= coordinates[1] <= 90):
                raise GooglePlacesError('invalid_response')
        name = value.get('displayName', {})
        if not isinstance(name, dict):
            raise GooglePlacesError('invalid_response')
        for field in ('types', 'attributions', 'addressComponents'):
            if not isinstance(value.get(field, []), list):
                raise GooglePlacesError('invalid_response')
        return cls(value['id'], name.get('text') or '', value.get('formattedAddress') or '',
                   value.get('addressComponents', []), coordinates, value.get('types', []),
                   value.get('googleMapsUri'), value.get('attributions', []))


def valid_place_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,512}', value))


class GooglePlacesClient:
    def __init__(self, *, client=None, api_key=None):
        self.api_key = os.getenv('GOOGLE_PLACES_API_KEY', '').strip() if api_key is None else api_key.strip()
        self.client, self.owns_client = client, client is None

    async def __aenter__(self):
        if self.client is None:
            self.client = httpx.AsyncClient()
        return self

    async def __aexit__(self, *args):
        if self.owns_client and self.client is not None:
            await self.client.aclose()
            self.client = None

    async def _request(self, method, path, fields, body=None):
        if not self.api_key:
            raise GooglePlacesError('configuration')
        if self.client is None:
            await self.__aenter__()
        try:
            async with asyncio.timeout(8):
                async with self.client.stream(method, 'https://places.googleapis.com'+path, json=body,
                        headers={'X-Goog-Api-Key':self.api_key, 'X-Goog-FieldMask':fields}, timeout=8, follow_redirects=False) as response:
                    code = response.status_code
                    if code != 200:
                        retry_after = None
                        try:
                            retry_after = max(0, float(response.headers.get('Retry-After', '')))
                        except ValueError:
                            pass
                        reason = 'configuration' if code in (400,401,403) else 'rate_limited' if code == 429 else 'not_found' if code == 404 else 'unavailable'
                        raise GooglePlacesError(reason, retry_after)
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 512*1024:
                            raise GooglePlacesError('invalid_response')
            value = json.loads(content, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (httpx.HTTPError, TimeoutError):
            raise GooglePlacesError('unavailable') from None
        except (ValueError, TypeError):
            raise GooglePlacesError('invalid_response') from None

    async def search_text(self, query, *, region_code=None):
        if not isinstance(query, str) or not query.strip() or len(query)>2000:
            raise GooglePlacesError('invalid_response')
        body = {'textQuery':query, 'pageSize':10, 'languageCode':'ja', 'includePureServiceAreaBusinesses':False}
        if region_code:
            body['regionCode'] = region_code
        value = await self._request('POST', '/v1/places:searchText', SEARCH_FIELDS, body)
        places = value.get('places', [])
        if not isinstance(places, list) or len(places)>10:
            raise GooglePlacesError('invalid_response')
        return [GoogleCandidate.from_payload(place) for place in places]

    async def details(self, place_id):
        if not valid_place_id(place_id):
            raise GooglePlacesError('invalid_response')
        candidate = GoogleCandidate.from_payload(await self._request('GET', '/v1/places/'+place_id, DETAIL_FIELDS))
        if candidate.place_id != place_id:
            raise GooglePlacesError('invalid_response')
        return candidate
