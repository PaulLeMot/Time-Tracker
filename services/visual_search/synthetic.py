"""Deterministic synthetic fixtures only; never opens a business database."""
from pathlib import Path
import argparse
import json
import shutil
import numpy as np
from PIL import Image, ImageDraw
from .engine import build


def prepare(root, model):
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError('synthetic_destination_must_be_empty')
    images = root / 'images'
    images.mkdir(parents=True)
    rows = []
    for number in range(12):
        rng = np.random.default_rng(1200+number)
        image = Image.new('RGB', (320, 320), 'white')
        draw = ImageDraw.Draw(image)
        for _ in range(65):
            x, y = rng.integers(10, 280, 2).tolist()
            color = tuple(rng.integers(0, 225, 3).tolist())
            draw.ellipse((x, y, x+25, y+25), outline=color, width=4)
            draw.line((x, y, 160, 160), fill=color, width=2)
        draw.text((50, 145), f'SYNTHETIC DESIGN {number:02}', fill='black', stroke_width=1)
        code = str(97000+number)
        image.save(images/(code+'.jpg'), quality=95)
        rows.append({'code': code, 'product_type': 'Тестовый вид А', 'name': f'Синтетический рисунок {number}', 'fandom': 'SYNTHETIC'})
    # More than a page of exact duplicate images, plus the same image in a rare category.
    for number in range(55):
        code = str(98000+number)
        shutil.copyfile(images/'97000.jpg', images/(code+'.jpg'))
        rows.append({'code': code, 'product_type': 'Тестовый вид Б' if number == 54 else 'Тестовый вид А',
                     'name': 'Синтетический дубль '+str(number), 'fandom': 'SYNTHETIC'})
    catalogue = root/'catalogue.json'
    catalogue.write_text(json.dumps(rows, ensure_ascii=False), 'utf-8')
    (root/'DATA_CLASS.txt').write_text('SYNTHETIC\n', 'utf-8')
    return build(catalogue, images, root/'index', model)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--model', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, args.model), indent=2))
