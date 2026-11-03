"""Versioned, bounded catalogue views. Source pixels are never modified."""
import hashlib
import io
import json
import math
import warnings
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

VERSION = 'views-2.0-dino224'
LAYOUTS = ('auto', 'single', 'left_right', 'top_bottom', 'cylinder', 'collage')
MAX_VIEWS = 9
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SOURCE_PIXELS = 12_000_000


def profile(value=None):
    value = dict(value or {})
    if set(value) - {'layout', 'regions', 'full_wrap', 'margin', 'revision', 'source_policy'}:
        raise ValueError('profile_fields')
    value.setdefault('layout', 'auto'); value.setdefault('revision', 1)
    value.setdefault('regions', []); value.setdefault('margin', 0.)
    value.setdefault('full_wrap', False)
    value.setdefault('source_policy','500')
    if value['source_policy'] not in ('500','original','auto'):raise ValueError('profile_source')
    if value['layout'] not in LAYOUTS or type(value['revision']) is not int or value['revision'] < 1:
        raise ValueError('profile_layout')
    if type(value['full_wrap']) is not bool or not isinstance(value['margin'], (int, float)) or not 0 <= value['margin'] < .2:
        raise ValueError('profile_parameters')
    if not isinstance(value['regions'], list) or len(value['regions']) > 8:
        raise ValueError('profile_regions')
    for box in value['regions']:
        if not isinstance(box, list) or len(box) != 4 or any(type(n) not in (float, int) or not math.isfinite(n) for n in box):
            raise ValueError('profile_region')
        if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
            raise ValueError('profile_region')
    return value


def safe_source(roots, root_id, relative):
    if root_id not in roots or not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('source_scope')
    parts = relative.split('/')
    if any(x in ('', '.', '..') for x in parts): raise ValueError('source_scope')
    root = Path(roots[root_id]).resolve(strict=True)
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('source_link')
    path = path.resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file(): raise ValueError('source_scope')
    return path


def read_source(path):
    before = path.stat()
    if before.st_size > MAX_SOURCE_BYTES: raise ValueError('source_bytes')
    body = path.read_bytes(); after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns): raise ValueError('source_unstable')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(body)) as source:
            if source.format not in ('JPEG','PNG','WEBP','TIFF') or source.width * source.height > MAX_SOURCE_PIXELS:
                raise ValueError('source_format_or_pixels')
            source.load(); image = ImageOps.exif_transpose(source).convert('RGB')
    if min(image.size) < 32: raise ValueError('source_too_small')
    # Exact decoded pixels: EXIF-transposed RGB, original dimensions, no resize.
    pixels = hashlib.sha256(f'RGB:{image.width}:{image.height}:'.encode() + image.tobytes()).hexdigest()
    return image, hashlib.sha256(body).hexdigest(), pixels


def representations(image, settings=None, product_type=None):
    p = profile(settings); w, h = image.size
    from .product_profiles import transforms
    recipe = transforms(product_type, p)
    yield {'role':'whole', 'region':[0,0,1,1], 'transform':'identity'}, image.copy()
    if recipe.get('mirror'):
        yield {'role':'fragment','region':[0,0,1,1],'transform':'mirror','mirrored':True}, ImageOps.mirror(image)
    boxes = p['regions']; m = p['margin']
    if not boxes and p['layout'] == 'left_right': boxes = [[m,m,.5-m,1-m],[.5+m,m,1-m,1-m]]
    if not boxes and p['layout'] == 'top_bottom': boxes = [[m,m,1-m,.5-m],[m,.5+m,1-m,1-m]]
    if not boxes and p['layout'] == 'cylinder':
        boxes = [[x, m, x+.5, 1-m] for x in (0,.125,.25,.375,.5)]
    for n, box in enumerate(boxes):
        crop = image.crop(tuple(round(v * (w if i % 2 == 0 else h)) for i,v in enumerate(box)))
        if min(crop.size) >= 16:
            view = {'role':'side' if p['layout'] in ('left_right','top_bottom') else 'fragment', 'region':box, 'transform':'crop', 'ordinal':n}
            if recipe.get('rotation'):
                crop = crop.rotate(recipe['rotation'], expand=True)
                view.update(transform='crop_rotate',rotation_ccw=recipe['rotation'])
            yield view, crop
            if recipe.get('mirror'):
                yield {**view,'transform':'crop_mirror','mirrored':True}, ImageOps.mirror(crop)
    # Only explicit full circumference profiles permit cylindrical projection.
    if p['layout'] == 'cylinder' and p['full_wrap'] and not p['regions']:
        import cv2
        source = np.asarray(image); size = min(768, max(224,w//2)); height = min(768,h)
        u = np.linspace(-.95,.95,size,dtype='float32')
        angles = np.arcsin(u) / (2*np.pi)
        for center in (.0, 1/3, 2/3):
            x = ((center+angles)%1)*(w-1)
            mapx = np.tile(x,(height,1)).astype('float32')
            mapy = np.tile(np.linspace(0,h-1,height,dtype='float32')[:,None],(1,size))
            projected = cv2.remap(source,mapx,mapy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_WRAP)
            yield {'role':'projection','region':[0,0,1,1],'transform':'cylinder','center':center}, Image.fromarray(projected)


def view_key(sha, view, settings, model_hash):
    return hashlib.sha256(json.dumps([sha, view, profile(settings), VERSION, model_hash],sort_keys=True,separators=(',',':')).encode()).hexdigest()
