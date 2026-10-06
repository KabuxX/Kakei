"""Bounded byte-level receipt validation; never trust the supplied MIME."""
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import struct
from pypdf import PdfReader
from services.validation import ValidationError
from api.http import HTTPFailure
from services.receipt_images import IMAGE_EXTENSIONS, IMAGE_MIMES, validate_image

MAX_BYTES=10*1024*1024
@dataclass(frozen=True)
class ReceiptFile:
    data: bytes
    mime_type: str
    sha256: str
    page_count: int


def validate_receipt(data, filename=None):
    if len(data)>MAX_BYTES:
        raise HTTPFailure(413,'body_too_large','レシートは10 MiB以内にしてください。')
    suffix=Path(filename or '').suffix.lower()
    try:
        if data.startswith(b'%PDF-'):
            if suffix not in ('','.pdf') or not data.rstrip().endswith(b'%%EOF'):
                raise ValueError()
            reader=PdfReader(io.BytesIO(data),strict=True)
            if reader.is_encrypted or not 1<=len(reader.pages)<=3:
                raise ValueError()
            root=reader.trailer['/Root']
            if any(key in root for key in ('/OpenAction','/AA')) or '/EmbeddedFiles' in root.get('/Names',{}):
                raise ValueError()
            mime,pages='application/pdf',len(reader.pages)
        else:
            fmt=validate_image(data)
            if suffix not in IMAGE_EXTENSIONS[fmt]:raise ValueError()
            if fmt in ('JPEG','MPO') and (not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9')):raise ValueError()
            if fmt=='PNG':
                end=8
                while end<len(data):
                    size=struct.unpack('>I',data[end:end+4])[0];kind=data[end+4:end+8];end+=12+size
                    if kind==b'IEND':break
                if end!=len(data) or kind!=b'IEND':raise ValueError()
            if fmt=='WEBP' and (data[:4]!=b'RIFF' or struct.unpack('<I',data[4:8])[0]+8!=len(data)):raise ValueError()
            mime,pages=IMAGE_MIMES[fmt],1
    except Exception as error:
        raise ValidationError('file','有効なJPEG・MPO・HEIC・HEIF・PNG・WebP、または暗号化されていない3ページ以内のPDFを選んでください。拡張子と内容も一致させてください。') from error
    return ReceiptFile(data,mime,hashlib.sha256(data).hexdigest(),pages)
