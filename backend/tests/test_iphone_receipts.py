"""Phone photo uploads retain their originals and expose a usable primary image."""
import base64
import hashlib
import io
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from fastapi.testclient import TestClient
from api.app import create_app
from db.agent_store import AgentStore
from db.receipt_store import ReceiptStore
from agent.receipt import extract_receipt
from services.receipt_validation import validate_receipt
from services.receipt_images import primary_jpeg, MAX_PIXELS
from services.validation import ValidationError
from receipt_image_fixtures import phone_photo
from test_receipt_extraction import Model

FORMATS = [('JPEG', 'photo.JPG', 'image/jpeg'), ('JPEG', 'photo.jpeg', 'image/jpeg'),
           ('MPO', 'photo.JPEG', 'image/jpeg'), ('MPO', 'photo.MPO', 'image/jpeg'),
           ('HEIF', 'photo.HEIC', 'image/heic'), ('HEIF', 'photo.heif', 'image/heic')]


def assert_primary_jpeg(test, data):
    with Image.open(io.BytesIO(data)) as image:
        test.assertEqual(image.format, 'JPEG')
        test.assertEqual(image.size, (4, 8))
        test.assertEqual(getattr(image, 'n_frames', 1), 1)
        red, green, blue = image.convert('RGB').getpixel((1, 1))
        test.assertGreater(red, 200)
        test.assertLess(blue, 50)
        test.assertNotIn(274, image.getexif())


class PhoneUploadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.app = create_app(root / 'db', root)
        self.app.state.store.initialize([])
        self.thread = AgentStore(root / 'db').create_thread()['id']
        self.receipts = ReceiptStore(root / 'db')
        self.client = TestClient(self.app, base_url='http://localhost:8765',
                                 headers={'Origin': 'http://localhost:8765'})
        self.addCleanup(self.client.close)

    def test_phone_formats_upload_keep_original_and_render_oriented_primary(self):
        for format, name, mime in FORMATS:
            with self.subTest(name=name):
                data = phone_photo(format)
                response = self.client.post(f'/api/agent/threads/{self.thread}/receipts',
                                            files={'file': (name, data, 'application/octet-stream')})
                self.assertEqual(response.status_code, 201, response.text)
                metadata = response.json()
                self.assertEqual(metadata['mimeType'], mime)
                self.assertEqual(metadata['sha256'], hashlib.sha256(data).hexdigest())
                asset = self.receipts.get_asset(metadata['id'])
                self.assertEqual(asset['data'], data)
                url = f"/api/agent/threads/{self.thread}/receipts/{metadata['id']}"
                original = self.client.get(url)
                self.assertEqual(original.content, data)
                preview = self.client.get(url + '?preview=true')
                self.assertEqual(preview.status_code, 200)
                self.assertEqual(preview.headers['content-type'], 'image/jpeg')
                assert_primary_jpeg(self, preview.content)
                self.assertEqual(self.client.get(url.replace(self.thread, 'wrong') + '?preview=true').status_code, 404)

    def test_saved_heic_keeps_original_and_preview_available_after_approval(self):
        data = phone_photo('HEIF')
        receipt = self.receipts.create_pending(self.thread, validate_receipt(data, 'photo.heic'))
        agent = AgentStore(self.app.state.store.db_path)
        proposal = agent.create_proposal(self.thread, [{'kind': 'transaction.create', 'identity': {},
            'data': {'title': '写真の取引', 'date': '2026-10-06T12:00', 'type': 'expense',
                     'category': '食費', 'amount': 408, 'merchant': '店舗',
                     'paymentMethod': 'cash', 'receiptIds': [receipt['id']]}}])
        self.app.state.store.apply_agent_proposal(proposal['id'], 1)
        url = f"/api/receipts/{receipt['id']}"
        self.assertEqual(self.client.get(url).content, data)
        assert_primary_jpeg(self, self.client.get(url + '?preview=true').content)

    def test_phone_files_reject_corruption_and_mismatched_extensions(self):
        for format in ('MPO', 'HEIF'):
            data = phone_photo(format)
            with self.subTest(format=format):
                with self.assertRaises(ValidationError):
                    validate_receipt(data, 'spoofed.png')
                with self.assertRaises(ValidationError):
                    validate_receipt(data[:len(data)//2], 'photo.jpeg' if format == 'MPO' else 'photo.heic')

    def test_oversized_secondary_heif_is_rejected_before_pixel_allocation(self):
        data = bytearray(phone_photo('HEIF'))
        aperture = data.rfind(b'clap')
        self.assertGreater(aperture, 0)
        data[aperture+4:aperture+12] = struct.pack('>II', 6000, 1)
        data[aperture+12:aperture+20] = struct.pack('>II', 6000, 1)
        allocations = []
        original = Image.core.new

        def guarded_new(mode, size):
            allocations.append(size)
            if size[0] * size[1] > MAX_PIXELS:
                raise RuntimeError('Oversized allocation intercepted')
            return original(mode, size)

        with patch.object(Image.core, 'new', side_effect=guarded_new):
            with self.assertRaises(ValidationError):
                validate_receipt(bytes(data), 'photo.heic')
        self.assertTrue(all(w * h <= MAX_PIXELS for w, h in allocations), allocations)


class PhoneExtractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_transparent_receipt_text_stays_readable_in_preview_and_ai_input(self):
        for format in ('PNG', 'WEBP'):
            with self.subTest(format=format):
                source = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
                source.paste((0, 0, 0, 255), (8, 8, 24, 24))
                stream = io.BytesIO()
                source.save(stream, format=format, lossless=True)
                file = validate_receipt(stream.getvalue(), 'receipt.' + format.lower())
                model = Model({'merchant': '店', 'total': 408})
                await extract_receipt(file, model)
                url = model.messages[1]['content'][1]['image_url']['url']
                for data in (primary_jpeg(file.data), base64.b64decode(url.split(',', 1)[1])):
                    with Image.open(io.BytesIO(data)) as preview:
                        self.assertGreater(min(preview.getpixel((1, 1))), 240)
                        self.assertLess(max(preview.getpixel((16, 16))), 15)

    async def test_ai_receives_oriented_single_jpeg_and_original_stays_intact(self):
        for format, name, mime in FORMATS:
            with self.subTest(name=name):
                data = phone_photo(format)
                file = validate_receipt(data, name)
                model = Model({'merchant': '店', 'total': 408})
                candidate = await extract_receipt(file, model)
                self.assertEqual(candidate.total, 408)
                url = model.messages[1]['content'][1]['image_url']['url']
                self.assertTrue(url.startswith('data:image/jpeg;base64,'))
                assert_primary_jpeg(self, base64.b64decode(url.split(',', 1)[1]))
                self.assertEqual(file.data, data)
