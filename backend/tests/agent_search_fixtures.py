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
