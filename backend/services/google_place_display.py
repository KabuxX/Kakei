"""Hydrate only the API response; never promote Google content into history."""
import asyncio
import copy
from agent.google_places import GooglePlacesError
from db.google_place_cache import read_cached_coordinates, write_cached_coordinates

class GooglePlaceDisplay:
    def __init__(self,store,client):
        self.store,self.client=store,client

    async def hydrate(self,timeline,*,now):
        result=copy.deepcopy(timeline)
        semaphore=asyncio.Semaphore(3)
        async def hydrate_place(place):
            if place.get('provider')!='google':
                return
            identifier=place['providerPlaceId']
            with self.store._connection() as connection:
                coordinates=read_cached_coordinates(connection,identifier,now)
            # Attribution is response-only and must be refreshed even on a coordinate hit.
            place['attributions']=[]
            async with semaphore:
                try:
                    candidate=await self.client.details(identifier)
                    place['attributions']=candidate.attributions
                    if coordinates is None:
                        coordinates=candidate.coordinates
                        if coordinates:
                            with self.store._connection() as connection:
                                write_cached_coordinates(connection,identifier,coordinates,now)
                except GooglePlacesError:
                    # Never display cached Google coordinates without the required attribution.
                    coordinates=None
            place['coordinates']=list(coordinates) if coordinates is not None else None
            place['locationResolution']='resolved' if coordinates is not None else 'unavailable'
        await asyncio.gather(*(hydrate_place(p) for p in result['places'].values()))
        return result
