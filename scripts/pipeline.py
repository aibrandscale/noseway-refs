#!/usr/bin/env python3
"""Durable image queue. Worker owns results; coordinator owns requests/reviews/sheet.
No Meta writes. No generated image enters sheet.json without a versioned QA review.
"""
import argparse, datetime as dt, hashlib, io, json, os, re, subprocess, time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = 'https://raw.githubusercontent.com/aibrandscale/noseway-refs/main'
REF = 'https://raw.githubusercontent.com/aibrandscale/noseway-refs/009d8f2fa099cf4fac72a085e5ad01746952845c'
PACK = REF + '/nose/pack/nose-strips-pack.png'
STRIP = REF + '/nose/strip/nose-strips.png'
PDP = 'https://noseway.bg/produkti/lepenki-za-nos/'
ANCHOR = dt.datetime(2026, 9, 8, 17, 30, tzinfo=dt.timezone.utc)
OFFER = 'Вземи 2 опаковки, третата е подарък'
FRAMEWORKS = ['AIDA','PAS','4 Ps','FAB',"4 U's",'BAB','STAR','PPP',"5 C's"]

def now(): return dt.datetime.now(dt.timezone.utc)
def stamp(): return now().isoformat(timespec='seconds')
def read(path, default=None):
    p = ROOT/path
    return json.loads(p.read_text()) if p.exists() else default
def write(path, obj):
    p=ROOT/path; p.parent.mkdir(parents=True, exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def digest(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
def git(*args): return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def checkpoint(paths, message):
    """Only stage owned files. Rebase disjoint cloud changes; never reset shared data."""
    git('add','--',*paths)
    if not git('diff','--cached','--name-only'): return
    git('commit','-m',message)
    for _ in range(4):
        try:
            git('pull','--rebase','origin','main');git('push','origin','HEAD:main');return
        except subprocess.CalledProcessError:
            if (ROOT/'.git/rebase-merge').exists() or (ROOT/'.git/rebase-apply').exists():
                raise RuntimeError('Concurrent edit conflict: preserve work and request attention')
            time.sleep(2)
    raise RuntimeError('Cannot persist pipeline checkpoint')
def batch_id(at=None):
    at=at or now()
    return None if at<ANCHOR else 'batch-'+str(int((at-ANCHOR).total_seconds()//172800)+1).zfill(4)
def due():
    b=batch_id();return {'batch_id':b,'due':bool(b and not (ROOT/f'jobs/batches/{b}.json').exists()),'count':10}
def validate_spec(s):
    for k in ['title','prompt','copy','framework']:
        if not isinstance(s.get(k),str) or not s[k].strip(): raise ValueError('Missing '+k)
    if s['framework'] not in FRAMEWORKS:raise ValueError('Unknown copy framework')
    if OFFER.casefold() not in s['copy'].casefold():raise ValueError('Copy must spell out the offer in packs')
    if not s['copy'].rstrip().endswith(PDP):raise ValueError('Copy must end in product URL')
    if len(s['prompt'])>3300:raise ValueError('Prompt too long; do not truncate rules')
def enqueue_batch(specs):
    d=due()
    if not d['due']:return {'created':0,**d}
    if len(specs)!=10:raise ValueError('Exactly 10 new concepts required')
    for s in specs:
        validate_spec(s);payload(dict(s,refs=[PACK,STRIP]))
    if len({s['prompt'] for s in specs})!=10:raise ValueError('Concepts must be distinct')
    b=d['batch_id'];ids=[]
    for i,s in enumerate(specs,1):
        rid=f'{b}-{i:02d}';ids.append(rid)
        write(f'jobs/requests/{rid}.json',dict(s,id=rid,kind='batch',batch_id=b,
              key=f'cr-{rid}',created_at=stamp(),refs=[PACK,STRIP]))
    write(f'jobs/batches/{b}.json',{'id':b,'created_at':stamp(),'request_ids':ids})
    return {'created':10,'batch_id':b}
def enqueue_rework(s):
    validate_spec(s)
    row=next(r for r in read('sheet.json')['rows'] if r['key']==s['key'] and r['kind']=='creative')
    if not s.get('feedback','').strip():raise ValueError('Rework requires specific feedback')
    if s['base_link']!=row['link']:raise ValueError('Stale creative version')
    rid='rework-'+digest([s['key'],s['base_link'],s['feedback']])
    if (ROOT/f'jobs/requests/{rid}.json').exists():return {'id':rid,'created':False}
    if not s['base_link'].startswith(RAW+'/creatives-'):raise ValueError('Unexpected creative URL')
    payload(dict(s,refs=[PACK,STRIP,s['base_link']]))
    write(f'jobs/requests/{rid}.json',dict(s,id=rid,kind='rework',created_at=stamp(),
        batch_id=row.get('batch_id','batch-legacy-001'),base_copy=row.get('copy',''),refs=[PACK,STRIP,s['base_link']]))
    return {'id':rid,'created':True}
def payload(req, feedback=''):
    instructions=(
      'Create a premium Bulgarian static advertisement. Exactly ONE large front-facing hero pouch. '
      'Image 1 is the authoritative REAL packaging. Reproduce its white NOSEWAY lettering, separate '
      'turquoise flourish, adult male line-drawing face, white strip, colors, layout and ALL packaging '
      'text faithfully. Image 2 is the real strip. Never redesign packaging or use a kids variant. '
      'If image 3 exists, it is the old ad for composition only; fix the requested issues. '
      'No added prices, currency, reviews, testimonials, stars, ratings, customer counts. '
      'No extra pouches anywhere, including in the background. No code compositing. '
      'Use large correctly spelled Bulgarian advertising text. The offer MUST be exactly: '
      '"'+OFFER+'". This list concerns ad text, not the original packaging lettering.\n')
    prompt=instructions+'CONCEPT AND EXACT AD TEXT:\n'+req['prompt']
    if req.get('feedback'):prompt+='\nUSER CORRECTION (visual requirements only):\n'+req['feedback']
    if feedback:prompt+='\nQA CORRECTION:\n'+feedback
    if len(prompt)>5000:raise ValueError('Payload exceeds 5000 characters; shorten concept, retain packaging rules')
    return {'model':'nano-banana-pro','input':{'prompt':prompt,'image_input':req['refs'],
            'aspect_ratio':'1:1','resolution':'1K','output_format':'png'}}
def api(path, body=None):
    key=os.environ.get('KIE_API_KEY')
    if not key:raise RuntimeError('Missing KIE_API_KEY')
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request('https://api.kie.ai/api/v1/'+path,data=data,
            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)
def save_result(r):
    p=f'jobs/results/{r["id"]}.json';write(p,r);checkpoint([p],'pipeline: '+r['id']+' '+r['status'])
def worker():
    month=now().strftime('%Y-%m');ledger=read(f'jobs/budgets/{month}.json',{'reserved':0})
    pending=[];failures=[]
    for f in sorted((ROOT/'jobs/requests').glob('*.json')):
        req=json.loads(f.read_text());rid=req['id'];r=read(f'jobs/results/{rid}.json',{'id':rid,'attempt':0,'status':'queued'})
        if r['status'] in ['submitting','submission_unknown']:
            failures.append(rid+': submission needs reconciliation');continue
        review=read(f'jobs/reviews/{rid}.json',{})
        retry=(review.get('decision')=='retry' and review.get('attempt')==r.get('attempt'))
        if r['status']=='generated' and not retry:continue
        if r['status'] in ['failed','blocked'] and not retry:continue
        if r.get('task_id') and r['status']=='submitted':pending.append((req,r));continue
        if r['attempt']>=3:failures.append(rid+': retry limit');continue
        if ledger['reserved']>=300:failures.append('monthly submission cap reached');break
        balance=api('chat/credit')
        if balance.get('code')!=200:raise RuntimeError('Cannot verify credits')
        if float(balance['data'])<18:failures.append('Insufficient credits');break
        body=payload(req,review.get('feedback','') if retry else '')
        r={'id':rid,'attempt':r['attempt']+1,'status':'submitting','started_at':stamp(),
           'payload_hash':digest(body),'refs':req['refs']}
        ledger['reserved']+=1;write(f'jobs/budgets/{month}.json',ledger)
        write(f'jobs/results/{rid}.json',r)
        checkpoint([f'jobs/budgets/{month}.json',f'jobs/results/{rid}.json'],'pipeline: reserve '+rid)
        try:
            response=api('jobs/createTask',body)
            task=(response.get('data') or {}).get('taskId')
            if not task:raise RuntimeError('createTask returned no taskId; do not auto-resubmit')
            r.update(task_id=task,status='submitted');save_result(r);pending.append((req,r))
        except Exception as e:
            r.update(status='submission_unknown',error=str(e)[:200]);save_result(r);failures.append(rid)
    deadline=time.monotonic()+1200
    while pending and time.monotonic()<deadline:
        next_pending=[]
        for req,r in pending:
            try:
                d=(api('jobs/recordInfo?taskId='+r['task_id']).get('data') or {})
                if d.get('state')=='success':
                    urls=json.loads(d.get('resultJson') or '{}').get('resultUrls',[])
                    if not urls:raise ValueError('No result URL')
                    with urllib.request.urlopen(urllib.request.Request(urls[0],headers={'User-Agent':'Mozilla/5.0'}),timeout=120) as response:
                        image_bytes=response.read(30_000_001)
                    if len(image_bytes)>30_000_000:raise ValueError('Image too large')
                    from PIL import Image
                    with Image.open(io.BytesIO(image_bytes)) as im:
                        if im.width!=im.height or im.width<1024:raise ValueError('Image must be square and at least 1024px')
                        path=f'creatives-{req["created_at"][:10]}/{r["id"]}-v{r["attempt"]}.jpg'
                        (ROOT/path).parent.mkdir(exist_ok=True)
                        im.convert('RGB').resize((1080,1080),Image.Resampling.LANCZOS).save(ROOT/path,quality=95)
                    r.update(status='generated',link=RAW+'/'+path,completed_at=stamp())
                    write(f'jobs/results/{r["id"]}.json',r)
                    checkpoint([path,f'jobs/results/{r["id"]}.json'],'pipeline: candidate '+r['id'])
                elif d.get('state') in ['fail','failed','error']:
                    r.update(status='failed',error=d.get('failMsg','Generation failed'));save_result(r);failures.append(r['id'])
                else:next_pending.append((req,r))
            except Exception as e:
                r['last_poll_error']=str(e)[:200];next_pending.append((req,r))
        pending=next_pending
        if pending:time.sleep(8)
    if pending:failures.append('Unfinished tasks remain submitted for next run; no duplicate charge')
    if failures:raise RuntimeError('; '.join(failures))
def review(s):
    r=read(f'jobs/results/{s["id"]}.json')
    if not r or (r['status']!='generated' and not (r['status']=='failed' and s['decision']=='retry')):raise ValueError('No reviewable candidate')
    if s['attempt']!=r['attempt'] or s.get('link')!=r.get('link'):raise ValueError('Stale QA review')
    if s['decision'] not in ['accept','retry','reject']:raise ValueError('Invalid decision')
    if not s.get('feedback','').strip():raise ValueError('QA must record visual evidence')
    if s['decision']=='accept' and not all(s.get('checks',{}).get(k) is True for k in
       ['packaging','logo','one_pack','bulgarian_text','offer','feedback_applied']):raise ValueError('All QA checks required')
    write(f'jobs/reviews/{s["id"]}.json',dict(s,reviewed_at=stamp()))
def publish(rid):
    req=read(f'jobs/requests/{rid}.json');r=read(f'jobs/results/{rid}.json');q=read(f'jobs/reviews/{rid}.json',{})
    if q.get('decision')!='accept' or q.get('attempt')!=r.get('attempt') or q.get('link')!=r.get('link'):raise ValueError('Unreviewed version')
    if not all(q.get('checks',{}).get(k) is True for k in ['packaging','logo','one_pack','bulgarian_text','offer','feedback_applied']):raise ValueError('Incomplete QA evidence')
    sheet=read('sheet.json');rows=sheet['rows'];old=next((x for x in rows if x['key']==req['key']),None)
    if old and old.get('link')==r['link']:return {'published':False,'reason':'already published'}
    if req['kind']=='rework':
        if not old or old['link']!=req['base_link'] or old.get('copy','')!=req['base_copy']:raise ValueError('Stale rework; original changed')
        name=old['name'];new=dict(old)
    else:
        if old:raise ValueError('Duplicate creative key')
        name=req['title'];new={k:None for k in ['cpa','roas','cpc','spend','impressions','results']}
    new.update(key=req['key'],kind='creative',name=name,link=r['link'],copy=req['copy'],
       framework=req['framework'],batch_id=req['batch_id'],created_at=(old.get('created_at') or (re.search(r'creatives-(\d{4}-\d{2}-\d{2})',old['link']).group(1) if re.search(r'creatives-(\d{4}-\d{2}-\d{2})',old['link']) else req['created_at'])) if old else req['created_at'],updated_at=stamp(),
       version=r['attempt'],generation_id=rid,reworked=req['kind']=='rework',status='On hold',qa=q)
    if old:rows[rows.index(old)]=new
    else:rows.append(new)
    sheet['updated_at']=stamp();write('sheet.json',sheet)
    write(f'jobs/published/{rid}.json',{'published_at':stamp(),'link':r['link'],'key':req['key'],
            'feedback':req.get('feedback'),'batch_id':req['batch_id']})
    return {'published':True,'key':req['key'],'link':r['link']}
def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['due','batch','rework','worker','review','publish','status']);p.add_argument('input',nargs='?');a=p.parse_args()
    if a.command=='due':out=due()
    elif a.command=='worker':worker();out={'worker':'complete'}
    elif a.command=='status':out=[json.loads(f.read_text()) for f in sorted((ROOT/'jobs/results').glob('*.json'))]
    elif a.command=='publish':out=publish(a.input)
    else:
        data=json.loads(Path(a.input).read_text());out={'batch':enqueue_batch,'rework':enqueue_rework,'review':review}[a.command](data)
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
