"""No-store Google display data, protected by the app's local-only middleware."""
from agent.google_places import valid_place_id, GooglePlacesClient, GooglePlacesError
from api.http import HTTPFailure, json_response

def register_google_places(app):
    @app.get('/api/places/google/{place_id}')
    async def google_place(place_id:str):
        if not valid_place_id(place_id):
            raise HTTPFailure(400,'invalid_place','地点の指定が正しくありません。')
        try:
            async with GooglePlacesClient() as client:
                value=await client.details(place_id)
        except GooglePlacesError:
            raise HTTPFailure(502,'place_unavailable','Googleの地点情報を取得できませんでした。再試行できます。') from None
        return json_response(200,{'placeId':value.place_id,'name':value.display_name,'address':value.formatted_address,
            'googleMapsUri':value.maps_uri,'attributions':value.attributions,'provider':'google'})
