"""Authenticated additive image catalog exchange; independent of manual Excel import."""
from pathlib import Path
import hashlib,hmac,json,re,time

VERSION='1.0.0'
MAX_BODY=8*1024*1024

class SyncError(ValueError):pass

def signature(secret,stamp,body):
    return hmac.new(secret,('OKIMG1\n'+stamp+'\n').encode()+body,hashlib.sha256).hexdigest()

def authenticate(secret,stamp,proof,body,clock=None):
    if len(secret)<32 or not re.fullmatch(r'[0-9]{10}',stamp or '') or abs((time.time() if clock is None else clock)-int(stamp))>120:raise SyncError('Invalid authentication')
    if not re.fullmatch('[a-f0-9]{64}',proof or '') or not hmac.compare_digest(signature(secret,stamp,body),proof):raise SyncError('Invalid authentication')

def parse(body):
    if len(body)>MAX_BODY:raise SyncError('Payload too large')
    try:value=json.loads(body)
    except (ValueError,UnicodeError):raise SyncError('Invalid JSON') from None
    if not isinstance(value,dict) or set(value)!={'version','job_id','products'} or value['version']!=1 or not re.fullmatch('[a-f0-9]{32}',str(value['job_id'])):raise SyncError('Invalid request')
    rows=value['products']
    if not isinstance(rows,list) or len(rows)>20000:raise SyncError('Invalid products')
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'code','product_type','fandom','name','sha256'}:raise SyncError('Invalid product fields')
        code=row['code']
        if not isinstance(code,str) or not re.fullmatch('[0-9]{5}',code) or code in seen:raise SyncError('Invalid or duplicate product code')
        seen.add(code)
        for field in ('product_type','fandom','name'):
            text=row[field]
            if field=='fandom' and text is None:continue
            if not isinstance(text,str) or len(text)>2000 or any(ord(c)<32 for c in text) or field in ('product_type','name') and not text.strip():raise SyncError('Invalid product text')
        if not isinstance(row['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',row['sha256']):raise SyncError('Invalid checksum')
    return value

def eligible(rows,root):
    root=Path(root).resolve();accepted=[];rejected=[]
    for row in rows:
        file=root/(row['code']+'.jpg')
        reason=''
        try:
            if file.is_symlink() or not file.is_file():reason='Изображение недоступно ОперПорталу'
            else:
                digest=hashlib.sha256()
                with file.open('rb') as stream:
                    if stream.read(2)!=b'\xff\xd8':reason='Ожидается JPEG с именем КОД.jpg'
                    stream.seek(0)
                    for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
                if not reason and digest.hexdigest()!=row['sha256']:reason='Контрольная сумма изображения не совпала'
        except OSError:reason='Не удалось прочитать изображение'
        if reason:rejected.append({'code':row['code'],'reason':reason})
        else:accepted.append({k:row[k] for k in ('code','product_type','fandom','name')})
    return accepted,rejected

def changes(rows,existing):
    counts={'added':0,'updated':0,'unchanged':0};changed=[]
    for row in rows:
        old=existing.get(row['code'])
        if old is None:counts['added']+=1;changed.append(row)
        elif any(old.get(k)!=row[k] for k in ('product_type','fandom','name')):counts['updated']+=1;changed.append(row)
        else:counts['unchanged']+=1
    return counts,changed
