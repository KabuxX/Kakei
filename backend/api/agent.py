"""Local-only agent conversation and explicit review endpoints."""
import asyncio
from fastapi import Request
from fastapi.responses import Response
from agent.runtime import AgentRunner, TurnLimit, configuration
from agent.limits import TURN_SECONDS
from api.http import HTTPFailure, json_response, read_json
from db.agent_store import AgentStore
from db.store import TrajectoryConflict, TrajectoryNotFound
from services.validation import ValidationError

async def body(request):
    value = await read_json(request, 512 * 1024)
    if not isinstance(value, dict):
        raise ValidationError('body', 'オブジェクトを指定してください。')
    return value


def register_agent(app, store, runner_factory=None):
    repository = AgentStore(store.db_path)

    @app.get('/api/agent/status')
    def status():
        return json_response(200, {'available': True, 'missing': [], 'message': '利用できます。'} if runner_factory else configuration())

    @app.post('/api/agent/threads')
    async def create_thread(request: Request):
        await body(request)
        return json_response(201, {'thread': repository.create_thread()})

    @app.get('/api/agent/threads')
    def list_threads():
        return json_response(200, {'threads': repository.list_threads()})

    @app.get('/api/agent/threads/{thread_id}')
    def get_thread(thread_id: str):
        thread = repository.get_thread(thread_id)
        if thread is None:
            raise TrajectoryNotFound('会話が見つかりません。')
        return json_response(200, {'thread': thread})

    @app.delete('/api/agent/threads/{thread_id}')
    def delete_thread(thread_id: str):
        repository.delete_thread(thread_id)
        return Response(status_code=204, headers={'Cache-Control':'no-store'})

    @app.post('/api/agent/threads/{thread_id}/messages')
    async def send_message(thread_id: str, request: Request):
        payload = await body(request)
        client_id = payload.get('clientMessageId')
        lease = repository.begin_turn(thread_id, client_id, payload.get('text'), payload.get('receiptId'))
        if 'cached' in lease:
            return json_response(200, lease['cached'])
        try:
            runner = runner_factory(store) if runner_factory else AgentRunner(store)
            result = await asyncio.wait_for(runner.run_turn(thread_id, repository.get_thread(thread_id)['messages'], payload.get('receiptId'), turn_context={'thread_id':thread_id,'client_message_id':client_id,'run_token':lease['token']}), TURN_SECONDS)
            try:
                response=repository.complete_turn(thread_id, client_id, lease, result)
            except TrajectoryConflict:
                reprepare=result.get('_reprepareCreation')
                if not reprepare:
                    raise
                result['preparedCreation']=await reprepare()
                try:
                    response=repository.complete_turn(thread_id, client_id, lease, result)
                except TrajectoryConflict:
                    from services.trajectory_creation import REASONS
                    import copy
                    failure=copy.deepcopy(result['preparedCreation'].result)
                    failure['excluded'] += [{**item,'reason':'source_conflict','message':REASONS['source_conflict']} for item in failure['saved']]
                    failure['saved']=[];failure['counts']['saved']=0;failure['counts']['excluded']=len(failure['excluded']);failure['status']='failed'
                    response=repository.complete_turn(thread_id,client_id,lease,{'text':'保存できませんでした。','creationFailure':failure})
            return json_response(200,response)
        except BaseException as error:
            repository.fail_turn(thread_id, client_id, lease['token'])
            if isinstance(error, (HTTPFailure, ValidationError, TrajectoryConflict, TrajectoryNotFound, asyncio.CancelledError)):
                raise
            if isinstance(error, TimeoutError):
                raise HTTPFailure(504, 'agent_timeout', '応答が時間内に完了しませんでした。再送できます。') from None
            if isinstance(error, TurnLimit):
                raise HTTPFailure(422, 'agent_limit', str(error)) from None
            if not isinstance(error, Exception):
                raise
            raise HTTPFailure(502, 'agent_error', 'AIの応答を取得できませんでした。設定を確認して再送してください。') from None

    @app.get('/api/agent/proposals/{proposal_id}')
    def get_proposal(proposal_id: str):
        return json_response(200, {'proposal': repository.get_proposal(proposal_id)})

    @app.put('/api/agent/proposals/{proposal_id}')
    async def revise(proposal_id: str, request: Request):
        payload = await body(request)
        return json_response(200, {'proposal': repository.revise_proposal(proposal_id, payload.get('revision'), payload.get('commands'))})

    @app.post('/api/agent/proposals/{proposal_id}/approve')
    async def approve(proposal_id: str, request: Request):
        payload = await body(request)
        return json_response(200, {'result': store.apply_agent_proposal(proposal_id, payload.get('revision'))})

    @app.post('/api/agent/proposals/{proposal_id}/reject')
    async def reject(proposal_id: str, request: Request):
        payload = await body(request)
        if type(payload.get('revision')) is not int:
            raise ValidationError('revision', '確認した版を指定してください。')
        return json_response(200, {'proposal': repository.reject_proposal(proposal_id, payload['revision'])})

    @app.post('/api/agent/proposals/{proposal_id}/places/selection')
    async def choose_place(proposal_id: str, request: Request):
        payload = await body(request)
        if not {'revision','candidateId'}<=set(payload) or set(payload)-{'revision','candidateId','confirmed'}:
            raise ValidationError('candidateId', '候補ID、版、必要な場合は位置の確認結果を指定してください。')
        return json_response(200, {'proposal': repository.select_place_candidate(proposal_id, payload['revision'], payload['candidateId'], confirmed=payload.get('confirmed',False))})

    @app.post('/api/agent/proposals/{proposal_id}/places/manual')
    async def manual_place(proposal_id: str, request: Request):
        payload = await body(request)
        return json_response(200, {'proposal': repository.select_place_candidate(proposal_id, payload.get('revision'), manual=payload.get('place'), place_id=payload.get('placeId'))})

    @app.post('/api/agent/proposals/{proposal_id}/order/confirmation')
    async def confirm_order(proposal_id: str, request: Request):
        payload = await body(request)
        return json_response(200, {'proposal': repository.confirm_trajectory_order(proposal_id, payload.get('revision'))})
