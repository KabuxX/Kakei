from db.store import Store
from db.agent_store import AgentStore

def active_turn(path, text='軌跡を作成'):
    store = Store(path)
    store.initialize([])
    agent = AgentStore(path)
    thread = agent.create_thread()['id']
    lease = agent.begin_turn(thread, 'one', text)
    return store, agent, {'thread_id': thread, 'client_message_id': 'one', 'run_token': lease['token']}

REQUEST = {'query': 'ドトール 西鉄福岡駅店', 'place_id': 'p'}

def result(identifier, candidates=None):
    return {'searchId': identifier, 'placeId': 'p', 'query': REQUEST['query'], 'candidates': candidates or [],
            'status': 'found' if candidates else 'empty', 'error': None, 'unresolved': [], 'truncated': False}

FUKUOKA = {'kind':'point','coordinates':[130.3994222,33.5892548],'city':'福岡市','district':'天神','country_code':'jp','source_id':'station'}
STATION = {'id':'station','providerId':'station','name':'西鉄福岡 (天神)','address':'福岡市 天神','city':'福岡市','district':'天神','country_code':'jp','coordinates':[130.3994222,33.5892548],'result_type':'amenity','categories':['public_transport.train']}
SHOP = {'id':'shop','providerId':'shop','name':'ドトールコーヒーショップ','address':'福岡市 天神二丁目','city':'福岡市','district':'天神','country_code':'jp','coordinates':[130.3987867,33.589319],'sourceUrl':'https://www.openstreetmap.org/copyright','attribution':'OSM'}
SEARCH = {**REQUEST,'brand':'ドトール','branch':'西鉄福岡駅店','landmark':'西鉄福岡駅'}
