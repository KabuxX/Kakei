"""Receipt-owned confirmation endpoints return reference-only state."""
from fastapi import Request
from api.agent import body
from api.http import json_response
from services.receipt_location import ReceiptLocationService


def register_receipt_locations(app, store, *, service_factory=ReceiptLocationService):
    service=service_factory(store)
    base='/api/agent/threads/{thread_id}/receipts/{receipt_id}/location'

    @app.get(base)
    def get(thread_id: str, receipt_id: str):
        return json_response(200,{'locationResolution':service.get(thread_id,receipt_id)})

    @app.post(base+'/search')
    async def search(thread_id: str, receipt_id: str, request: Request):
        value=await body(request)
        result=await service.search(thread_id,receipt_id,value.get('input'),value.get('revision'),source_transaction_id=value.get('sourceTransactionId'))
        return json_response(200,{'locationResolution':result})

    @app.post(base+'/selection')
    async def selection(thread_id: str, receipt_id: str, request: Request):
        value=await body(request)
        result=await service.select(thread_id,receipt_id,value.get('resolutionId'),value.get('revision'),value.get('placeId'))
        return json_response(200,{'locationResolution':result})

    @app.post(base+'/address')
    async def address(thread_id: str, receipt_id: str, request: Request):
        value=await body(request)
        result=service.confirm_address(thread_id,receipt_id,value.get('input'),value.get('revision'),source_transaction_id=value.get('sourceTransactionId'))
        return json_response(200,{'locationResolution':result})
