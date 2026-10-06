"""Synthetic phone photos; no personal receipt or metadata is stored in tests."""
import io
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener(thumbnails=False)


def phone_photo(format):
    # HEIF stores orientation in its container; the encoder normalizes EXIF.
    primary = Image.new('RGB', (4, 8) if format == 'HEIF' else (8, 4), 'red')
    exif = Image.Exif()
    exif[274] = 6
    stream = io.BytesIO()
    options = {'exif': exif}
    if format in ('MPO', 'HEIF'):
        options.update(save_all=True, append_images=[Image.new('RGB', (8, 4), 'blue')])
    primary.save(stream, format=format, **options)
    return stream.getvalue()
