"""Coordinate bounded provider calls with versioned, receipt-scoped confirmations."""
import asyncio
import time
from dataclasses import replace
from agent.google_places import GooglePlacesClient, GooglePlacesError
from db.receipt_location_store import ReceiptLocationStore
from db.merchant_place_store import read_merchant_place
from db.store import TrajectoryConflict, TrajectoryNotFound
from services.google_place_resolution import normalize_name
from services.receipt_location_contracts import normalize_location_input
from services.receipt_location_matching import match_receipt_places, receipt_query_variants
from services.validation import ValidationError
from api.http import HTTPFailure


class ReceiptLocationService:
    def __init__(self, store, *, client_factory=GooglePlacesClient, monotonic=time.monotonic, wall_clock=time.time):
        self.store=store
        self.locations=ReceiptLocationStore(store.db_path)
        self.client_factory=client_factory
        self.monotonic=monotonic
        self.wall_clock=wall_clock

    def _asset(self, thread_id, receipt_id):
        with self.store._connection() as c:
            row=c.execute('SELECT r.* FROM receipt_assets r JOIN agent_threads t ON t.id=r.thread_id WHERE r.id=? AND r.thread_id=?', (receipt_id,thread_id)).fetchone()
            if not row or (row['expires_at'] is not None and row['expires_at'] <= self.wall_clock()):
                raise TrajectoryNotFound('この会話の有効なレシートが見つかりません。')

    def get(self, thread_id, receipt_id):
        self._asset(thread_id,receipt_id)
        return self.locations.get(thread_id,receipt_id,now=self.wall_clock())

    def _prepare(self, thread_id, receipt_id, value, revision):
        self._asset(thread_id,receipt_id)
        value=normalize_location_input(value)
        current=self.locations.get(thread_id,receipt_id,now=self.wall_clock())
        if type(revision) is not int or revision != (current['revision'] if current else 0):
            raise TrajectoryConflict('店舗確認が更新されています。')
        if current is None:
            current=self.locations.seed(thread_id,receipt_id,value,status='needs_input',method=None,now=self.wall_clock())
            if current['revision'] != 1 or current['status'] != 'needs_input':
                raise TrajectoryConflict('店舗確認が更新されています。')
        return value,current

    def _source(self, value, identifier):
        with self.store._connection() as c:
            row=c.execute('SELECT merchant,merchant_address FROM transactions WHERE id=?',(identifier,)).fetchone()
            binding=read_merchant_place(c,identifier)
        if not row or not value['merchant'] or normalize_name(row['merchant'] or '') != normalize_name(value['merchant']):
            raise ValidationError('sourceTransactionId','同じ店舗の保存先を指定してください。')
        return row['merchant_address'],binding

    async def initialize(self, thread_id, receipt_id, candidate, *, deadline, turn_context):
        self._asset(thread_id,receipt_id)
        value=normalize_location_input({'merchant':candidate.merchant or '', 'merchantAddress':candidate.merchant_address})
        current=self.locations.seed(thread_id,receipt_id,value,status='resolved' if value['merchant'] and value['merchantAddress'] else 'needs_input',method='receipt_address' if value['merchant'] and value['merchantAddress'] else None,now=self.wall_clock())
        if current['status'] != 'needs_input' or not value['merchant']:
            return current
        return await self._search(thread_id,receipt_id,value,current['revision'],deadline=deadline,turn_context=turn_context)

    async def search(self, thread_id, receipt_id, input, revision, *, source_transaction_id=None, deadline=None):
        return await self._search(thread_id,receipt_id,input,revision,source_transaction_id=source_transaction_id,deadline=deadline)

    async def _search(self, thread_id, receipt_id, input, revision, *, source_transaction_id=None, deadline=None, turn_context=None):
        value=normalize_location_input(input)
        if not value['merchant']:
            raise ValidationError('merchant','店舗名を入力してください。')
        if source_transaction_id is not None:
            _,binding=self._source(value,source_transaction_id)
            if not binding:
                raise ValidationError('sourceTransactionId','保存済みの地点参照を確認してください。')
            value={**value,'merchantAddress':None}
            value,current=self._prepare(thread_id,receipt_id,value,revision)
            return self.locations.set_existing_google(thread_id,receipt_id,value,current['revision'],binding['placeId'],source_transaction_id,now=self.wall_clock())
        end=min(self.monotonic()+20,deadline) if deadline is not None else self.monotonic()+20
        value,current=self._prepare(thread_id,receipt_id,value,revision)
        # An exhausted turn still creates a recoverable short lease; no request is sent.
        remaining=max(0.001,end-self.monotonic())
        started=self.locations.begin_search(thread_id,receipt_id,value,current['revision'],now=self.wall_clock(),processing_until=self.wall_clock()+min(20,remaining))
        result=dict(status='unavailable',reason='budget_exceeded')
        try:
            if end <= self.monotonic():
                raise TimeoutError()
            candidates=[]
            async with asyncio.timeout(max(0.001,end-self.monotonic())):
                async with self.client_factory() as client:
                    for query in receipt_query_variants(value):
                        remaining=end-self.monotonic()
                        if remaining <= 0: raise TimeoutError()
                        async with asyncio.timeout(min(8,remaining)):
                            found=await client.search_text(query,region_code='JP')
                        candidates.extend(found)
                        # Never consider more than ten provider reference IDs.
                        candidates=list({c.place_id:c for c in candidates}.values())[:10]
                        result=match_receipt_places(value,candidates)
                        if result['status'] in ('resolved','needs_selection'): break
            if self.monotonic() >= end: raise TimeoutError()
        except GooglePlacesError as error:
            result=dict(status='not_found' if error.code=='not_found' else 'unavailable',reason='not_found' if error.code=='not_found' else 'provider_configuration' if error.code=='configuration' else 'provider_unavailable')
        except TimeoutError:
            result=dict(status='unavailable',reason='budget_exceeded')
        except asyncio.CancelledError:
            self._asset(thread_id,receipt_id)
            try:
                self.locations.finish_search(thread_id,receipt_id,started['id'],started['revision'],dict(status='unavailable',reason='cancelled'),now=self.wall_clock(),turn_context=turn_context)
            except TrajectoryConflict: pass
            raise
        self._asset(thread_id,receipt_id)
        # Expired leases are recovered by the store rather than completed late.
        if self.wall_clock() >= started['expiresAt']:
            raise TrajectoryConflict('店舗確認の期限が切れています。')
        if end <= self.monotonic() and result.get('reason')=='budget_exceeded':
            recovered=self.locations.get(thread_id,receipt_id,now=self.wall_clock())
            if recovered['revision'] != started['revision']:
                if recovered['reason']=='budget_exceeded': return recovered
                raise TrajectoryConflict('店舗確認が更新されています。')
        return self.locations.finish_search(thread_id,receipt_id,started['id'],started['revision'],result,now=self.wall_clock(),turn_context=turn_context)

    async def select(self, thread_id, receipt_id, resolution_id, revision, place_id):
        current=self.get(thread_id,receipt_id)
        if not current or type(revision) is not int or current['id'] != resolution_id or current['revision'] != revision or current['status'] != 'needs_selection':
            raise TrajectoryConflict('店舗確認が更新されています。')
        if place_id not in current['placeIds']:
            raise ValidationError('placeId','現在の候補から選択してください。')
        try:
            async with asyncio.timeout(8):
                async with self.client_factory() as client:
                    detail=await client.details(place_id)
        except (GooglePlacesError,TimeoutError) as error:
            reason='provider_configuration' if isinstance(error,GooglePlacesError) and error.code=='configuration' else 'budget_exceeded' if isinstance(error,TimeoutError) else 'provider_unavailable'
            raise HTTPFailure(503,reason,'店舗情報を取得できませんでした。再試行してください。') from None
        # Details' field mask omits types; search already checked store eligibility.
        checked=match_receipt_places(current['input'],[replace(detail,types=detail.types or ['store'])])
        if detail.place_id != place_id or place_id not in checked['placeIds']:
            raise ValidationError('placeId','候補の店舗名と住所を確認してください。')
        self._asset(thread_id,receipt_id)
        return self.locations.set_selection(thread_id,receipt_id,resolution_id,revision,place_id,now=self.wall_clock())

    def confirm_address(self, thread_id, receipt_id, input, revision, *, source_transaction_id=None):
        value=normalize_location_input(input)
        if not value['merchant'] or not value['merchantAddress']:
            raise ValidationError('input','店舗名と住所を入力してください。')
        method='user_address'
        if source_transaction_id is not None:
            address,_=self._source(value,source_transaction_id)
            if not address or address != value['merchantAddress']:
                raise ValidationError('merchantAddress','保存先の住所を確認してください。')
            method='existing_address'
        value,current=self._prepare(thread_id,receipt_id,value,revision)
        return self.locations.set_address(thread_id,receipt_id,value,current['revision'],method=method,source_transaction_id=source_transaction_id,now=self.wall_clock())
