"""Offline bounded query processing. No training, catalogue writes or image storage.

The original is always a retrieval branch. Learned restoration supplies only a
bounded low-frequency correction; original detail is never replaced by invented
high-frequency pixels. Scores are similarities, not probabilities.
"""
import base64
import hashlib
import io
from pathlib import Path
import time

VERSION = 'enhancer-1'
WEIGHTS = {'u2netp.onnx': '309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8',
           'dhan.pth': '83f0dfaa68a455e40256fafae0008c29c5ff6d9e3b4d8df584ec96cb8d917fee'}


def jpeg(image):
    output = io.BytesIO(); image.save(output, 'JPEG', quality=92)
    return output.getvalue()


def merge(original, variants):
    """Preserve confirmed original evidence; transformed-only matches stay yellow.

    A correlated second query never creates confirmation, nor are its scores
    summed. An original confirmed item cannot be displaced by processed pixels.
    """
    items = {r['code']: dict(r, query_branch='original') for r in original['items']}
    protected = {r['code'] for r in original['items'] if r.get('similarity_status') == 'confirmed'}
    anchored=set(protected)
    if original['items']:
        first=original['items'][0]
        if first.get('geometry_inliers',0)>=12 and first.get('geometry_support',0)>=.30:
            anchored.add(first['code'])
    for branch, result in variants:
        for row in result['items']:
            code = row['code']; score = round(float(row['score']) - .045, 5)
            if code in anchored or code in items and items[code]['score'] >= score:
                continue
            items[code] = dict(row, score=score, evidence='weak',
                               similarity_status='uncertain' if score >= .72 else 'weak', query_branch=branch)
    ordered = sorted(items.values(), key=lambda r: (r['code'] not in anchored, -r['score'], r.get('relation') != 'direct', r['code']))
    return dict(original, items=ordered, total=len(ordered),
                status='similar' if ordered and ordered[0]['code'] in protected else 'weak' if ordered else 'none',
                ranking_version=original.get('ranking_version', '') + '-enhancer1')


def needs_fallback(result):
    rows = result['items']
    return not rows or rows[0].get('similarity_status') != 'confirmed'


class Enhancer:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        for name, expected in WEIGHTS.items():
            path = self.root / name
            if path.is_symlink() or path.resolve().parent != self.root or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('enhancer_model_checksum')
        self.segmenter = self.restorer = None

    @staticmethod
    def artwork(engine, image, baseline):
        """Locate a known print from mutually consistent original keypoints.

        Candidate-conditioned geometry can reject table/handle without mistaking
        an illustrated face for the entire product. It remains a query proposal.
        """
        import cv2
        import numpy as np
        from PIL import Image
        grey=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY)
        keys,desc=cv2.SIFT_create(nfeatures=768).detectAndCompute(grey,None)
        if desc is None or len(keys)<12:return image,'artwork_not_located'
        points=np.float32([k.pt for k in keys]);best=None;seen=set()
        for item in baseline['items'][:6]:
            refs=[r for r in engine.rows if r['code']==item['code'] and r.get('asset_id')==item.get('asset_id') and r.get('view',{'role':'whole'})==item.get('match_view',{'role':'whole'})]
            for row in refs[:2]:
                feature=row['feature']
                if feature<0 or feature in seen:continue
                seen.add(feature);start,end=engine.offsets[feature:feature+2]
                rp=engine.points[start:end];rd=engine.descriptors[start:end]
                if len(rd)<12:continue
                pairs=cv2.BFMatcher().knnMatch(desc,rd.astype('float32'),k=2)
                good=[a for pair in pairs if len(pair)==2 for a,b in [pair] if a.distance<.68*b.distance]
                if len(good)<12:continue
                src=np.float32([points[m.queryIdx] for m in good]);dst=np.float32([rp[m.trainIdx] for m in good])
                matrix,mask=cv2.findHomography(src,dst,cv2.RANSAC,3,maxIters=1000,confidence=.995)
                if matrix is None or mask is None or not np.isfinite(matrix).all():continue
                selected=mask.ravel().astype(bool);inliers=int(selected.sum())
                ref_extent=np.maximum(rp.max(axis=0),32)
                coverage=cv2.contourArea(cv2.convexHull(dst[selected]))/float(ref_extent.prod()) if inliers>=4 else 0
                if inliers<12 or inliers/len(good)<.65 or coverage<.12:continue
                width,height=(ref_extent*1.05+8).astype(int)
                if min(width,height)<40 or max(width,height)>1200:continue
                try:
                    corners=cv2.perspectiveTransform(np.float32([[[0,0],[width,0],[width,height],[0,height]]]),np.linalg.inv(matrix))[0]
                except (np.linalg.LinAlgError,cv2.error):continue
                fraction=abs(cv2.contourArea(corners))/(image.width*image.height)
                if not cv2.isContourConvex(corners) or not .08<=fraction<=1.15:continue
                if np.any(corners<np.float32([-image.width*.15,-image.height*.15])) or np.any(corners>np.float32([image.width*1.15,image.height*1.15])):continue
                merit=inliers*min(coverage,.6)
                if best is None or merit>best[0]:best=(merit,matrix,(width,height))
        if best is None:return image,'artwork_not_located'
        out=cv2.warpPerspective(np.asarray(image),best[1],best[2],flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=(255,255,255))
        return Image.fromarray(out),'artwork_aligned'

    def segment(self, image):
        """A salient object is a proposal, not an SKU/printed-design detector."""
        import cv2
        import numpy as np
        from PIL import Image
        if self.segmenter is None:
            self.segmenter = cv2.dnn.readNetFromONNX(str(self.root / 'u2netp.onnx'))
            self.segmenter.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.segmenter.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        a = np.asarray(image.resize((320, 320)), dtype=np.float32) / 255
        a = (a - np.array([.485, .456, .406], np.float32)) / np.array([.229, .224, .225], np.float32)
        self.segmenter.setInput(a.transpose(2, 0, 1)[None])
        pred = self.segmenter.forward()[0, 0]
        if not np.isfinite(pred).all() or float(pred.max() - pred.min()) < .4:
            return image, 'segmentation_rejected'
        mask = ((pred - pred.min()) / max(1e-6, pred.max() - pred.min()) > .35).astype('uint8')
        count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
        if count <= 1: return image, 'segmentation_rejected'
        selected = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])); x, y, w, h, area = stats[selected]
        occupancy = area / (320 * 320)
        # Reject small drawings/faces, ambiguous multiple products, and full-frame masks.
        if not (.16 <= occupancy <= .88 and area / max(1, w*h) >= .45 and area >= .85 * mask.sum()
                and w >= 100 and h >= 100 and 65 <= centers[selected][0] <= 255 and 65 <= centers[selected][1] <= 255):
            return image, 'segmentation_rejected'
        # Keep the external silhouette filled: holes can be printed artwork.
        mask = (labels == selected).astype('uint8') * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        mask[:] = 0; cv2.drawContours(mask, contours, -1, 255, cv2.FILLED)
        mask = cv2.dilate(mask, np.ones((13, 13), 'uint8'))
        soft = cv2.resize(mask, image.size, interpolation=cv2.INTER_LINEAR).astype('float32') / 255
        source = np.asarray(image).astype('float32')
        source = source * soft[..., None] + 255 * (1 - soft[..., None])
        pad = 10; sx, sy = image.width/320, image.height/320
        box = (max(0, int((x-pad)*sx)), max(0, int((y-pad)*sy)), min(image.width, int((x+w+pad)*sx)), min(image.height, int((y+h+pad)*sy)))
        return Image.fromarray(source.clip(0, 255).astype('uint8')).crop(box), 'object_mask'

    @staticmethod
    def plane(image):
        """Only a single well-supported convex quadrilateral; never unwrap a mug."""
        import cv2
        import numpy as np
        from PIL import Image
        a = np.asarray(image); h, w = a.shape[:2]
        grey = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(grey, (5, 5), 0), 45, 130)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:6]:
            p = cv2.approxPolyDP(c, .018*cv2.arcLength(c, True), True)
            area = cv2.contourArea(p) / (h*w)
            if len(p) != 4 or not cv2.isContourConvex(p) or not .20 <= area <= .88: continue
            p = p[:, 0].astype('float32'); center = p.mean(axis=0)
            if not (.25*w < center[0] < .75*w and .25*h < center[1] < .75*h): continue
            # Angle-sort, rotate to top-left, preserve handedness.
            p = p[np.argsort(np.arctan2(p[:,1]-center[1], p[:,0]-center[0]))]
            p = np.roll(p, -int(np.argmin(p.sum(axis=1))), axis=0)
            lengths = np.linalg.norm(p-np.roll(p, -1, axis=0), axis=1)
            if min(lengths) < .22*min(w,h) or max(lengths)/min(lengths) > 4: continue
            width = int(max(lengths[0], lengths[2])); height = int(max(lengths[1], lengths[3]))
            # Padded outer border avoids trimming the print.
            target = np.float32([[4,4],[width+3,4],[width+3,height+3],[4,height+3]])
            matrix = cv2.getPerspectiveTransform(p, target)
            out = cv2.warpPerspective(a, matrix, (width+8,height+8), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(255,255,255))
            return Image.fromarray(out), 'plane_rectified'
        return image, 'plane_not_detected'

    def restore(self, image):
        import cv2
        import numpy as np
        import torch
        from PIL import Image
        a = np.asarray(image).astype('float32')
        # Preserve shape with a padded, fixed-size tensor. No variable-size inference.
        from PIL import ImageOps
        padded = ImageOps.pad(image, (256,256), color='white')
        small = np.asarray(padded).astype('float32') / 255
        if self.restorer is None:
            from .vendor.dhan import Model
            model = Model().eval()
            state = torch.load(self.root/'dhan.pth', map_location='cpu', weights_only=True)
            model.load_state_dict(state['state_dict'], strict=True)
            self.restorer = model
        with torch.inference_mode():
            restored = self.restorer(torch.from_numpy(small.transpose(2,0,1).copy())[None])[0].clamp(0,1).numpy().transpose(1,2,0)
        if not np.isfinite(restored).all(): raise ValueError('enhancer_nonfinite')
        # Upsample a low-frequency residual, never the network's invented detail.
        delta = (restored-small)*255
        scale = min(256/image.width,256/image.height)
        rw, rh = round(image.width*scale), round(image.height*scale)
        x, y = (256-rw)//2, (256-rh)//2
        delta = cv2.resize(delta[y:y+rh,x:x+rw], image.size, interpolation=cv2.INTER_LINEAR)
        grey = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
        hsv = cv2.cvtColor((a/255).astype('float32'),cv2.COLOR_RGB2HSV)
        # Broad bright/low-chroma regions may be reflections. This is a proposal;
        # the original branch remains authoritative even if white art is affected.
        glare = ((grey > 185) & (hsv[:,:,1] < .28) & (delta.mean(axis=2) < -7)).astype('float32')
        glare = cv2.GaussianBlur(glare,(0,0),max(1,min(image.size)/100))
        out = a + np.clip(delta,-64,8)*glare[...,None]*.75
        operations = []
        if float(glare.mean()) > .003: operations.append('glare_low_frequency')
        # Mild edge-preserving smoothing, only for unusually strong high frequencies.
        lap = float(cv2.Laplacian(grey,cv2.CV_32F).var())
        if lap > 1100:
            smooth = cv2.bilateralFilter(out.astype('uint8'),5,18,3).astype('float32')
            out = .8*out + .2*smooth; operations.append('texture_mild')
        luminance = float(np.median(grey))
        if luminance < 85:
            gain = min(1.2,100/max(1,luminance)); out *= gain; operations.append('exposure_bounded')
        return Image.fromarray(out.clip(0,255).astype('uint8')), operations

    def prepare(self, body, engine=None, baseline=None):
        from .engine import decode
        original = decode(body)
        # Rectangular print boundaries are more appropriate than salient faces.
        crop, geometry = self.artwork(engine,original,baseline) if engine is not None and baseline is not None else (original,'artwork_not_located')
        if geometry == 'artwork_not_located':crop,geometry=self.plane(original)
        if geometry == 'plane_not_detected': crop, geometry = self.segment(original)
        crop.thumbnail((1024,1024))
        return crop,([geometry] if geometry not in ('plane_not_detected','segmentation_rejected') else [])

    def process(self, body, engine=None, baseline=None):
        start=time.perf_counter();crop,geometry=self.prepare(body,engine,baseline)
        out, operations = self.restore(crop)
        operations = geometry + operations
        return {'image':out,'object_image':crop,'operations':operations,
                'version':VERSION,'elapsed_ms':round((time.perf_counter()-start)*1000,2)}

    def preview(self, body, engine=None, kind=''):
        baseline=engine.search(body,kind) if engine is not None else None
        result = self.process(body,engine,baseline)
        return {k:v for k,v in result.items() if k not in ('image','object_image')} | {
            'image_base64':base64.b64encode(jpeg(result['image'])).decode('ascii'), 'content_type':'image/jpeg'}

    def search(self, engine, body, kind, namespace='portal', baseline=None):
        if baseline is None:baseline=engine.search(body,kind,namespace=namespace)
        start=time.perf_counter();crop,operations=self.prepare(body,engine,baseline);variants=[]
        # At most two extra retrievals, using the same pinned index/model.
        if operations:
            objects=engine.search(jpeg(crop),kind,namespace=namespace);variants.append(('object',objects))
            first=objects['items'][0] if objects['items'] else {}
            # Stop before restoration if real, unpainted detail already provides
            # strong support. It still cannot create a green original confirmation.
            if not baseline.get('enhancement_force') and first.get('score',0)>=.92 and first.get('geometry_inliers',0)>=12 and first.get('geometry_support',0)>=.30:
                return {'variants':variants,'enhancement':{'operations':operations,'version':VERSION,'stage':'object','elapsed_ms':round((time.perf_counter()-start)*1000,2)}}
        out,restoration=self.restore(crop);operations+=restoration
        if restoration:variants.append(('processed',engine.search(jpeg(out),kind,namespace=namespace)))
        return {'variants':variants,'enhancement':{'operations':operations,'version':VERSION,'stage':'restoration','elapsed_ms':round((time.perf_counter()-start)*1000,2)}}
