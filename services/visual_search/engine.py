"""Trusted immutable indexes, CPU DINOv2 retrieval and SIFT/RANSAC verification."""
from pathlib import Path
import hashlib
import io
import json
import os
import re
import time
import warnings

os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
import cv2
import numpy as np
from PIL import Image, ImageOps

VERSION = 'vs1-dino224-sift256'
RANKING_VERSION = 'cosine-sift-evidence-1'
MAX_BODY = 2 * 1024 * 1024
MAX_PIXELS = 12_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
cv2.setNumThreads(1)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode(body):
    if not body or len(body) > MAX_BODY:
        raise ValueError('image_size')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(body)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP') or source.width * source.height > MAX_PIXELS:
                    raise ValueError('image_format_or_pixels')
                source.load()
                image = ImageOps.exif_transpose(source).convert('RGB')
        if min(image.size) < 32:
            raise ValueError('image_too_small')
        image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        return image
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('invalid_image') from None


def local_features(image):
    grey = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    keys, descriptors = cv2.SIFT_create(nfeatures=256).detectAndCompute(grey, None)
    points = np.array([k.pt for k in keys], dtype='float32').reshape(-1, 2)
    descriptors = np.zeros((0, 128), 'uint8') if descriptors is None else np.clip(descriptors, 0, 255).astype('uint8')
    return points, descriptors


def geometry(qp, qd, points, descriptors):
    if min(len(qd), len(descriptors)) < 4:
        return 0, 0.0
    pairs = cv2.BFMatcher().knnMatch(qd.astype('float32'), descriptors.astype('float32'), k=2)
    good = [a for pair in pairs if len(pair) == 2 for a, b in [pair] if a.distance < .72 * b.distance]
    if len(good) < 6:
        return 0, 0.0
    src = np.float32([qp[m.queryIdx] for m in good])
    dst = np.float32([points[m.trainIdx] for m in good])
    matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0, maxIters=800, confidence=.99)
    if matrix is None or mask is None or not np.isfinite(matrix).all():
        return 0, 0.0
    count = int(mask.sum())
    # Avoid calling a tiny repeated detail a verified print.
    selected = src[mask.ravel().astype(bool)]
    if len(selected) < 4:
        return 0, 0.0
    hull = cv2.convexHull(selected)
    extent = np.ptp(qp, axis=0)
    coverage = cv2.contourArea(hull) / max(1., float(extent.prod()))
    return count, min(1., count / 24) * min(1., count / len(good)) if coverage >= .025 else 0.0


class Embedder:
    def __init__(self, model_root, threads=2):
        import torch
        from transformers import Dinov2Model
        self.torch = torch
        torch.set_num_threads(threads)
        path = Path(model_root).resolve(strict=True)
        manifest = json.loads((path / 'manifest.json').read_text('utf-8'))
        if manifest['revision'] != 'ed25f3a31f01632728cabb09d1542f84ab7b0056':
            raise ValueError('model_revision')
        for name, expected in manifest['files'].items():
            if name not in {'config.json', 'preprocessor_config.json', 'model.safetensors', 'README.md'} or digest(path / name) != expected:
                raise ValueError('model_checksum')
        # Pin the weight bytes independently of the adjacent manifest.
        if manifest['files']['model.safetensors'] != 'ae1e99fcefd534ed978cdeb8326f08030c96e28b7a81ffcbc98a857c84d14be1':
            raise ValueError('untrusted_weights')
        self.model_hash = digest(path / 'model.safetensors')
        self.model = Dinov2Model.from_pretrained(str(path), local_files_only=True, use_safetensors=True).eval()
        self(np.zeros((224, 224, 3), dtype='uint8'))

    def __call__(self, image):
        return self.batch([image])[0]

    def batch(self, images):
        # Letterbox preserves the whole print; this is versioned, for queries AND catalogue.
        arrays = []
        for image in images:
            image = Image.fromarray(image) if isinstance(image, np.ndarray) else image
            image = ImageOps.pad(image, (224, 224), method=Image.Resampling.BICUBIC, color='white')
            a = np.asarray(image, dtype='float32') / 255
            a = (a - np.array([.485, .456, .406], 'float32')) / np.array([.229, .224, .225], 'float32')
            arrays.append(a.transpose(2, 0, 1))
        t = self.torch.from_numpy(np.stack(arrays))
        with self.torch.inference_mode():
            v = self.model(pixel_values=t).last_hidden_state[:, 0].numpy()
        return (v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)).astype('float32')


def build(catalogue, image_root, index_root, model_root, progress=None):
    """No DB, no network, incremental by image hash; publish pointer only after validation."""
    root = Path(image_root).resolve(strict=True)
    target = Path(index_root).resolve()
    target.mkdir(parents=True, exist_ok=True)
    rows = json.loads(Path(catalogue).read_text('utf-8'))
    embed = Embedder(model_root)
    cache = target / ('cache-' + VERSION)
    cache.mkdir(exist_ok=True)
    accepted, skipped, ids, features, seen = [], [], {}, [], set()
    pending = []

    def flush():
        if not pending:
            return
        vectors = embed.batch([x[2] for x in pending])
        for (key, index, image, points, desc), vector in zip(pending, vectors):
            temporary = cache / (key + '.tmp')
            with temporary.open('wb') as output:
                np.savez(output, points=points, descriptors=desc, vector=vector)
            os.replace(temporary, cache / (key + '.npz'))
            features[index] = (points, desc, vector)
        pending.clear()
    started = time.monotonic()
    for number, row in enumerate(rows):
        code = row.get('code')
        if not isinstance(code, str) or not re.fullmatch(r'[0-9]{5}', code) or code in seen:
            raise ValueError('duplicate_or_invalid_code')
        seen.add(code)
        if any(not isinstance(row.get(k), str) or not row[k].strip() or len(row[k]) > 2000 for k in ('product_type', 'name')):
            raise ValueError('invalid_metadata')
        file = root / (code + '.jpg')
        try:
            if file.is_symlink() or file.resolve().parent != root or file.stat().st_size > MAX_BODY:
                raise ValueError('unsafe_image')
            body = file.read_bytes()
            key = hashlib.sha256(body).hexdigest()
            if key not in ids:
                image = decode(body)
                cached = cache / (key + '.npz')
                ids[key] = len(features)
                if cached.exists():
                    with np.load(cached, allow_pickle=False) as a:
                        features.append((a['points'], a['descriptors'], a['vector']))
                else:
                    points, desc = local_features(image)
                    pending.append((key, len(features), image, points, desc))
                    features.append(None)
                    if len(pending) >= 8:
                        flush()
            accepted.append({k: row.get(k) for k in ('code', 'product_type', 'name', 'fandom')} | {'feature': ids[key], 'sha256': key})
        except (OSError, ValueError):
            skipped.append({'code': code, 'reason': 'missing_or_invalid_image'})
        if progress and (number+1) % 250 == 0:
            progress({'processed': number+1, 'total': len(rows), 'accepted': len(accepted), 'seconds': round(time.monotonic()-started, 1)})
    if not accepted:
        raise ValueError('empty_index')
    flush()
    generation = 'index-' + str(time.time_ns())
    out = target / generation
    out.mkdir()
    offsets = np.cumsum([0] + [len(x[0]) for x in features], dtype='int64')
    arrays = {'vectors': np.stack([x[2] for x in features]), 'points': np.concatenate([x[0] for x in features]),
              'descriptors': np.concatenate([x[1] for x in features]), 'offsets': offsets}
    for name, array in arrays.items():
        np.save(out / (name + '.npy'), array, allow_pickle=False)
    (out / 'products.json').write_text(json.dumps(accepted, ensure_ascii=False), 'utf-8')
    manifest = {'version': VERSION, 'model_hash': embed.model_hash, 'dimension': 384, 'products': len(accepted),
                'unique_images': len(features), 'catalogue_hash': digest(catalogue), 'skipped': skipped,
                'files': {p.name: digest(p) for p in out.iterdir() if p.is_file()}}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
    Engine(out, model_root, embedder=embed)  # Fully validate before switch; prior generation is retained.
    pointer = {'generation': generation, 'sha256': digest(out / 'manifest.json')}
    temporary = target / 'current.tmp'
    temporary.write_text(json.dumps(pointer), 'utf-8')
    os.replace(temporary, target / 'current.json')
    return manifest


def resolve_index(root):
    root = Path(root).resolve(strict=True)
    value = json.loads((root / 'current.json').read_text('utf-8'))
    if not re.fullmatch(r'index-[0-9]+', value['generation']):
        raise ValueError('index_pointer')
    path = root / value['generation']
    if path.is_symlink() or digest(path / 'manifest.json') != value['sha256']:
        raise ValueError('index_pointer_checksum')
    return path


class Engine:
    def __init__(self, generation, model_root, embedder=None):
        path = Path(generation)
        meta = json.loads((path / 'manifest.json').read_text('utf-8'))
        expected = {'vectors.npy', 'points.npy', 'descriptors.npy', 'offsets.npy', 'products.json'}
        if meta['version'] != VERSION or set(meta['files']) != expected or meta['dimension'] != 384:
            raise ValueError('incompatible_index')
        for name, sha in meta['files'].items():
            if (path / name).is_symlink() or digest(path / name) != sha:
                raise ValueError('index_checksum')
        self.embed = embedder or Embedder(model_root)
        if meta['model_hash'] != self.embed.model_hash:
            raise ValueError('index_model_mismatch')
        self.meta, self.index_id = meta, path.name
        self.rows = json.loads((path / 'products.json').read_text('utf-8'))
        self.vectors, self.points, self.descriptors, self.offsets = [np.load(path / (n + '.npy'), mmap_mode='r', allow_pickle=False) for n in ('vectors', 'points', 'descriptors', 'offsets')]
        if self.vectors.shape != (meta['unique_images'], 384) or len(self.rows) != meta['products']:
            raise ValueError('index_shape')
        self.types = {}
        for row in self.rows:
            self.types.setdefault(row['product_type'], {}).setdefault(row['feature'], []).append(row)

    def search(self, body, product_type, mode='hybrid'):
        started = time.perf_counter()
        if product_type not in self.types:
            raise ValueError('unknown_product_type')
        image = decode(body)
        decoded = time.perf_counter()
        qp, qd = local_features(image)
        groups = self.types[product_type]  # Category restriction BEFORE any topK.
        candidates = np.array(list(groups), dtype='int64')
        vector = self.embed(image) if mode != 'sift' else None
        embedded = time.perf_counter()
        similarities = self.vectors[candidates] @ vector if vector is not None else np.zeros(len(candidates))
        order = np.argsort(-similarities, kind='stable')[:48] if mode != 'sift' else np.arange(len(candidates))
        items = []
        for i in order:
            feature = int(candidates[i])
            a, b = self.offsets[feature:feature+2]
            inliers, geo = geometry(qp, qd, self.points[a:b], self.descriptors[a:b]) if mode != 'dino' else (0, 0.)
            sim = float(similarities[i])
            verified = inliers >= 10 and geo >= .30
            # Full-catalogue benchmark: geometry-first ranking promoted shared
            # borders/templates above the correct drawing. Preserve global rank;
            # local features provide evidence, never an unconditional promotion.
            score = sim if mode != 'sift' else geo
            if verified or (mode != 'sift' and sim >= .60):
                # Expand ALL product codes for the image; never deduplicate products.
                for row in groups[feature]:
                    items.append({k: row[k] for k in ('code', 'name', 'product_type', 'fandom')} |
                                 {'score': round(score, 5), 'evidence': 'geometry' if verified else 'weak',
                                  'image_url': '/static/img/' + row['code'] + '.jpg'})
        items.sort(key=lambda r: (-r['score'], r['code']))
        ended = time.perf_counter()
        return {'api_version': 1, 'index_version': self.index_id, 'model_version': VERSION,
                'ranking_version': RANKING_VERSION,
                'status': 'similar' if items and items[0]['evidence'] == 'geometry' else 'weak' if items else 'none',
                'items': items, 'total': len(items), 'candidate_design_limit': 48,
                'timings_ms': {'decode': (decoded-started)*1000, 'features_embedding': (embedded-decoded)*1000,
                               'search_rerank': (ended-embedded)*1000, 'compute': (ended-started)*1000}}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    for name in ('catalogue', 'images', 'index', 'model'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.catalogue, args.images, args.index, args.model, progress=lambda p: print(json.dumps(p), flush=True)), indent=2))
