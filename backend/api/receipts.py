"""Bounded multipart receipt upload and local file access."""
from fastapi import Request
from fastapi.responses import Response
from starlette.formparsers import MultiPartParser, MultiPartException
from starlette.datastructures import UploadFile
from api.http import HTTPFailure, json_response
from db.receipt_store import ReceiptStore
from db.store import TrajectoryNotFound
from services.receipt_validation import MAX_BYTES, validate_receipt
from services.validation import ValidationError

def register_receipts(app,store):
    receipts=ReceiptStore(store.db_path)
    @app.post('/api/agent/threads/{thread_id}/receipts')
    async def upload(thread_id:str,request:Request):
        async def bounded():
            size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>MAX_BYTES+65536:raise MultiPartException('レシートは10 MiB以内にしてください。')
                yield chunk
        if not request.headers.get('content-type','').startswith('multipart/form-data;'):
            raise ValidationError('file','レシートファイルを選んでください。')
        try:
            form=await MultiPartParser(request.headers,bounded(),max_files=1,max_fields=0).parse()
        except MultiPartException as error:
            raise HTTPFailure(413,'invalid_upload','1ファイル、10 MiB以内で送信してください。') from error
        try:
            if len(form)!=1 or not isinstance(form.get('file'),UploadFile):
                raise ValidationError('file','レシートを1ファイル選んでください。')
            file=form['file'];data=await file.read(MAX_BYTES+1)
            return json_response(201,receipts.create_pending(thread_id,validate_receipt(data,file.filename)))
        finally:await form.close()

    def file_response(asset):
        return Response(asset['data'],media_type=asset['mime_type'],headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"sandbox; default-src 'none'",'Content-Disposition':'inline; filename="receipt.'+{'image/png':'png','image/jpeg':'jpg','image/webp':'webp','application/pdf':'pdf'}[asset['mime_type']]+'"'})

    @app.get('/api/agent/threads/{thread_id}/receipts/{receipt_id}')
    def preview(thread_id:str,receipt_id:str):
        asset=receipts.get_asset(receipt_id)
        if not asset or asset['thread_id']!=thread_id:raise TrajectoryNotFound('レシートが見つかりません。')
        return file_response(asset)

    @app.get('/api/receipts/{receipt_id}')
    def approved(receipt_id:str):
        asset=receipts.get_asset(receipt_id)
        if not asset or not asset['transaction_id']:raise TrajectoryNotFound('レシートが見つかりません。')
        return file_response(asset)
