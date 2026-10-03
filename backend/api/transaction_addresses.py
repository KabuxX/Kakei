"""Address-only writes and saved place context."""
from fastapi import Request
from api.http import json_response,read_json


def register_transaction_addresses(app, store):
    @app.get('/api/transaction-addresses')
    def list_addresses():
        return json_response(200,{'addresses':store.get_transaction_addresses()})

    @app.get('/api/transaction-addresses/{transaction_id:path}')
    def get_address(transaction_id: str):
        return json_response(200,{'address':store.get_transaction_addresses(transaction_id)[0]})

    @app.patch('/api/transaction-addresses/{transaction_id:path}')
    async def update_address(transaction_id: str, request: Request):
        payload=await read_json(request,16384)
        return json_response(200,{'transaction':store.update_merchant_address(transaction_id,payload)})
