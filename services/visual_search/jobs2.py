"""Durable bounded metadata jobs. Query photos are never written to job storage."""
from pathlib import Path
import hashlib, json, os, re, subprocess, sys, time, uuid
import threading
from .index2 import atomic_json

TERMINAL={'complete','partial','failed','cancelled'}


def read_json(path):
    deadline=time.monotonic()+2
    while True:
        try:return json.loads(Path(path).read_text('utf-8'))
        except OSError as error:
            if getattr(error,'winerror',None) not in (5,32,33) or time.monotonic()>=deadline:raise
            time.sleep(.025)


def acquire_execution(root):
    handle=(Path(root)/'execution.lock').open('a+b')
    if handle.tell()==0:handle.write(b'0');handle.flush()
    handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return handle
    except OSError:handle.close();return None


def release_execution(handle):
    handle.seek(0)
    if os.name=='nt':
        import msvcrt
        msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
    else:
        import fcntl
        fcntl.flock(handle,fcntl.LOCK_UN)
    handle.close()


class Jobs:
    def __init__(self,config):
        self.config=config;self.root=Path(config['jobs']);self.root.mkdir(parents=True,exist_ok=True)
        self.process=None;self.current=None;self.summaries={};self.queue_lock=threading.Lock()
        # A crashed process cannot resume a partially published generation.
        for path in self.root.glob('*.json'):
            value=read_json(path)
            if value.get('status')=='running':value['status']='queued';atomic_json(path,value)

    def get(self,identifier):
        if not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('job_id')
        return read_json(self.root/(identifier+'.json'))

    def all(self):
        values=[]
        for path in self.root.glob('*.json'):
            stamp=path.stat().st_mtime_ns;old=self.summaries.get(path.name)
            if not old or old[0]!=stamp:
                full=read_json(path)
                summary={k:v for k,v in full.items() if k not in ('payload','catalogue_ref','results','decision_history')}
                self.summaries[path.name]=(stamp,summary)
            values.append(self.summaries[path.name][1])
        return sorted(values,key=lambda x:x['created'],reverse=True)[:100]

    def create(self,kind,payload):
        with self.queue_lock:return self._create(kind,payload)

    def _create(self,kind,payload):
        if kind not in ('index','batch'):raise ValueError('job_kind')
        if len([x for x in self.all() if x['status'] not in TERMINAL])>=8:raise ValueError('job_queue_full')
        encoded=json.dumps([kind,payload],sort_keys=True,ensure_ascii=False).encode();key=hashlib.sha256(encoded).hexdigest()
        for old in self.all():
            if old['key']==key and old['status'] in ('queued','running'):return self.public(old)
        if kind=='batch':
            files=payload.get('files',[])
            if not isinstance(files,list) or not 1<=len(files)<=2000:raise ValueError('batch_limit')
            for item in files:
                if set(item)-{'root','relative','id','sha256'}:raise ValueError('batch_fields')
                from .views import safe_source
                safe_source(self.config['source_roots'],item['root'],item['relative'])
        identifier=uuid.uuid4().hex;now=time.time()
        value={'id':identifier,'kind':kind,'status':'queued','created':now,'updated':now,'key':key,'progress':{},'results':[],'attempts':0}
        if kind=='index':
            catalogues=self.root/'catalogues';catalogues.mkdir(exist_ok=True)
            stored=catalogues/(key+'.json')
            if not stored.exists():atomic_json(stored,payload)
            value['catalogue_ref']=key
        else:value['payload']=payload
        atomic_json(self.root/(identifier+'.json'),value);return self.public(value)

    def public(self,value):
        return {k:v for k,v in value.items() if k not in ('payload','key','catalogue_ref')}

    def cancel(self,identifier):
        value=self.get(identifier)
        (self.root/(identifier+'.cancel')).touch()
        if value['status']=='queued':value['status']='cancelled';atomic_json(self.root/(identifier+'.json'),value)
        return self.public(value)

    def resume(self,identifier):
        value=self.get(identifier)
        if value['status'] not in TERMINAL:raise ValueError('job_not_terminal')
        (self.root/(identifier+'.cancel')).unlink(missing_ok=True)
        value['status']='queued';value['attempts']=0;value.pop('not_before',None);value.pop('error',None);atomic_json(self.root/(identifier+'.json'),value)
        return self.public(value)

    def tick(self):
        if self.process and self.process.poll() is None:return
        if self.current:
            value=self.get(self.current)
            if value['status']=='running':value.update(status='failed',error='job_process_exited');atomic_json(self.root/(self.current+'.json'),value)
            self.current=None;self.process=None
        queued=sorted([x for x in self.all() if x['status']=='queued' and x.get('not_before',0)<=time.time()],key=lambda x:x['created'])
        if not queued:return
        # Avoid native-library/model startup while employee requests are active.
        now=time.time()
        if now-queued[0]['created']<3:return
        for name,quiet in (('query-active',9),('query-last',3)):
            signal=self.root/name
            if signal.exists() and now-signal.stat().st_mtime<quiet:return
        probe=acquire_execution(self.root)
        if probe is None:return
        release_execution(probe)
        self.current=queued[0]['id']
        # Explicit protected config file, never credentials in arguments or output.
        executable=Path(sys._base_executable)
        if os.name=='nt':executable=executable.with_name('pythonw.exe')
        self.process=subprocess.Popen([str(executable),'-B','-m','services.visual_search.jobs2','--config',self.config['_config_file'],'--job',self.current],
            env=os.environ.copy(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)


def execute(config,identifier):
    handle=acquire_execution(config['jobs'])
    if handle is None:return
    try:return _execute(config,identifier)
    finally:release_execution(handle)


def _execute(config,identifier):
    import io
    root=Path(config['jobs']);path=root/(identifier+'.json');value=json.loads(path.read_text('utf-8'))
    cancel=lambda:(root/(identifier+'.cancel')).exists()
    def save():value['updated']=time.time();atomic_json(path,value)
    def progress(p):value['progress']=p;save()
    def throttle():
        if cancel():raise ValueError('cancelled')
        busy=root/'query-active'
        last=root/'query-last'
        while busy.exists() and time.time()-busy.stat().st_mtime<9 or last.exists() and time.time()-last.stat().st_mtime<3:
            if cancel():raise ValueError('cancelled')
            time.sleep(.1)
        time.sleep(.01)
    background=False
    try:
        if os.name=='nt':
            import ctypes
            from ctypes import wintypes
            ctypes.windll.kernel32.SetErrorMode(0x8003)
            ctypes.windll.kernel32.GetCurrentProcess.restype=wintypes.HANDLE
            ctypes.windll.kernel32.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD]
            background=bool(ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x00100000))
        from .resources import restrict_compute
        resource_handle=restrict_compute(memory_mb=config.get('job_memory_mb',1536),cpu_percent=config.get('job_cpu_percent',5))
        throttle()
        from .engine import Engine,resolve_index
        from .views import safe_source,read_source
        if value.get('error'):value['last_error']={k:value.pop(k) for k in ('error','error_code','error_frames') if k in value}
        value['status']='running';value['attempts']=value.get('attempts',0)+1;save()
        payload=json.loads((root/'catalogues'/(value['catalogue_ref']+'.json')).read_text('utf-8')) if value.get('catalogue_ref') else value['payload']
        if value['kind']=='index':
            from .index2 import build
            value['candidate']=build(payload['rows'],config['source_roots'],config['index'],config['model'],payload.get('profiles'),progress=progress,cancelled=cancel,throttle=throttle,publish=False)
            value['status']='partial' if value['candidate']['manifest']['skipped'] else 'complete'
        else:
            engine=Engine(resolve_index(config['index']),config['model']);value['index_version']=engine.index_id
            known_bytes={};known_pixels={}
            for row in engine.rows:
                if row.get('namespace','portal')!='operkontur':continue
                known_bytes.setdefault(row['sha256'],set()).add((row['code'],row.get('asset_id')))
                if row.get('pixel_sha256'):known_pixels.setdefault(row['pixel_sha256'],set()).add((row['code'],row.get('asset_id')))
            seen_bytes={};seen_pixels={};batch_vectors=[];batch_details=[];prior={r['id']:r for r in value.get('results',[]) if r.get('status')=='checked'};results=[]
            for n,item in enumerate(payload['files']):
                throttle()
                file_id=item.get('id') or hashlib.sha256(json.dumps([item['root'],item['relative']]).encode()).hexdigest()
                def exact(lookup,digest):
                    return next((code for code,asset in sorted(lookup.get(digest,()),key=lambda x:x[0]) if asset!=item.get('id')),None)
                try:
                    source=safe_source(config['source_roots'],item['root'],item['relative']);image,sha,pixels=read_source(source)
                    if item.get('sha256') and sha!=item['sha256']:raise ValueError('source_changed')
                    if file_id in prior and prior[file_id]['sha256']==sha:
                        result=prior[file_id]
                    else:
                        buf=io.BytesIO();query=image.copy();query.thumbnail((960,960));query.save(buf,'JPEG',quality=90)
                        result=engine.search(buf.getvalue(),payload.get('product_type',''),namespace='operkontur')
                        result={k:result[k] for k in ('items','total','status','index_version')}
                        result['items']=result['items'][:10]
                        duplicate=exact(known_bytes,sha) or seen_bytes.get(sha)
                        pixel_duplicate=exact(known_pixels,pixels) or seen_pixels.get(pixels)
                        result.update(id=file_id,name=item['relative'],status='checked',sha256=sha,pixel_sha256=pixels,
                                      root=item['root'],relative=item['relative'],
                                      match_type='exact_file' if duplicate else 'exact_pixels' if pixel_duplicate else 'visual' if result['items'] else 'none',
                                      exact_reference=duplicate or pixel_duplicate,decision='needs_review')
                    result['within_batch_reference']=seen_bytes.get(sha) or seen_pixels.get(pixels)
                    result['catalogue_exact_reference']=exact(known_bytes,sha) or exact(known_pixels,pixels)
                    # Compare new designs with the preceding files as well as the catalogue.
                    import numpy as np
                    from .engine import local_features,geometry
                    small=image.copy();small.thumbnail((1024,1024));vector=engine.embed(small);points,descriptors=local_features(small)
                    similar=[]
                    if batch_vectors:
                        similarities=np.asarray(batch_vectors)@vector
                        for k in np.argsort(-similarities)[:5]:
                            if similarities[k]<.75:continue
                            reference,reference_points,reference_desc=batch_details[k]
                            inliers,geo=geometry(points,descriptors,reference_points,reference_desc)
                            similar.append({'file_id':reference,'score':round(float(similarities[k]),5),'status':'confirmed' if similarities[k]>=.92 and inliers>=10 and geo>=.30 else 'uncertain'})
                    result['within_batch_similar']=similar
                    batch_vectors.append(vector);batch_details.append((file_id,points,descriptors))
                    seen_bytes[sha]=file_id;seen_pixels[pixels]=file_id
                    # Keep own index asset out of visual duplicate candidates.
                    result['items']=[r for r in result['items'] if not (r.get('asset_id')==item.get('id') and item.get('id'))]
                    results.append(result)
                except (OSError,ValueError) as error:
                    results.append({'id':file_id,'name':item['relative'],'status':'unreadable','error':'source_unavailable_or_invalid'})
                value['results']=results;progress({'processed':n+1,'total':len(payload['files'])})
            value['status']='partial' if any(x['status']!='checked' for x in results) else 'complete'
        save()
    except Exception as error:
        import traceback
        value.update(status='cancelled' if cancel() else 'queued' if value.get('attempts',0)<3 else 'failed',error='cancelled' if cancel() else type(error).__name__,
                     error_code=getattr(error,'winerror',None),error_frames=[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(error.__traceback__)[-3:]],
                     not_before=time.time()+min(300,15*2**value.get('attempts',0)));save()
    finally:
        if background:ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x00200000)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--job',required=True);a=p.parse_args()
    config=json.loads(Path(a.config).read_text('utf-8-sig'));execute(config,a.job)
