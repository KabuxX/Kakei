"""Decode phone photos and render their primary image without changing originals."""
import io
import warnings
from PIL import Image, ImageOps
from pillow_heif import open_heif, register_heif_opener

register_heif_opener(thumbnails=False)

IMAGE_MIMES = {'JPEG': 'image/jpeg', 'MPO': 'image/jpeg', 'HEIF': 'image/heic',
               'PNG': 'image/png', 'WEBP': 'image/webp'}
IMAGE_EXTENSIONS = {'JPEG': ('', '.jpg', '.jpeg'), 'MPO': ('', '.jpg', '.jpeg', '.mpo'),
                    'HEIF': ('', '.heic', '.heif'), 'PNG': ('', '.png'), 'WEBP': ('', '.webp')}
MAX_PIXELS = 30_000_000
MAX_FRAMES = 16
MAX_TOTAL_PIXELS = 60_000_000


def validate_image(data):
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            format = image.format
            frames = getattr(image, 'n_frames', 1)
            if format not in IMAGE_MIMES or not 1 <= frames <= MAX_FRAMES:
                raise ValueError('Unsupported image')
            if format not in ('MPO', 'HEIF') and frames != 1:
                raise ValueError('Animated image')
            if image.width * image.height > MAX_PIXELS:
                raise ValueError('Image too large')
            if format == 'HEIF':
                # Pillow's HEIF seek allocates each frame immediately. Inspect
                # lazy frame descriptors before seeking or decoding any frame.
                container = open_heif(data)
                total = 0
                for frame in container:
                    width, height = frame.size
                    pixels = width * height
                    total += pixels
                    if min(width, height) <= 0 or pixels > MAX_PIXELS or total > MAX_TOTAL_PIXELS:
                        raise ValueError('Image too large')
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            total = 0
            for index in range(frames):
                image.seek(index)
                pixels = image.width * image.height
                total += pixels
                if pixels > MAX_PIXELS or total > MAX_TOTAL_PIXELS:
                    raise ValueError('Image too large')
                image.load()
            return format


def primary_jpeg(data):
    """Return an oriented single JPEG for browsers and vision input."""
    with Image.open(io.BytesIO(data)) as image:
        if image.format == 'HEIF':
            for index in range(image.n_frames):
                image.seek(index)
                if image.info.get('primary'):
                    break
            else:
                raise ValueError('Missing primary image')
        else:
            image.seek(0)
        oriented = ImageOps.exif_transpose(image)
        if 'A' in oriented.getbands() or 'transparency' in oriented.info:
            rgba = oriented.convert('RGBA')
            background = Image.new('RGB', rgba.size, 'white')
            background.paste(rgba, mask=rgba.getchannel('A'))
            oriented = background
        else:
            oriented = oriented.convert('RGB')
        output = io.BytesIO()
        # Remove EXIF from the display/AI copy, including its orientation tag.
        oriented.info.clear()
        oriented.save(output, format='JPEG', quality=95)
        return output.getvalue()
