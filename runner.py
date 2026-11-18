"""Portable deterministic runner with task-level durable checkpoints."""
from pathlib import Path
from fractions import Fraction as F
import argparse,json,hashlib,os
import solver as S
import allocation
from audit import audit

VERSION='runner-trial-0.1'
REPAIR_CANDIDATES=4
def context(c):
    here=Path(__file__).resolve().parent
    return dict(config=S.encode(S.normalize(c)),programs={name:hashlib.sha256((here/name).read_bytes()).hexdigest()
               for name in ('solver.py','allocation.py','audit.py','runner.py')},runner=VERSION)

def save(path,body):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    data=dict(body=body,sha256=S.digest(body));tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8',newline='\n') as f:
        f.write(S.canon(data));f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def load(path):
    d=json.loads(Path(path).read_text(encoding='utf-8'))
    if S.digest(d['body'])!=d['sha256']:raise ValueError('checkpoint checksum mismatch')
    return d['body']

def make(c):
    base=S.initial(c);lo,hi=base['lower'],base['upper']
    return dict(context=context(c),lower=lo,upper=hi,target=lo,phase='construct',index=0,
                attempts=0,completed=0,uncertain=0,pending=None,attempt_log=[],
                attempt_limit=max(0,hi-lo+1)*(len(S.POLICIES)+REPAIR_CANDIDATES)+c['search']['attempt_reserve'],
                records=[],refinements=[],selected=[],best=base['best'],stop=base['stop'])

def promising(r,p):
    a=r['improved']['audit'];deficits=sorted(max(F(0),p['util']-F(b['util'])) for b in a['bins'])
    penalties=sum((max(F(0),F(b['fb'])-p['fb'])/max(F(1),p['fb'])+max(F(0),F(b['lr'])-p['lr'])/max(F(1),p['lr']) for b in a['bins']),F(0))
    if deficits:deficits=deficits[:-1]
    return (len(a['unassigned']),penalties+10*sum(deficits,F(0)),r['policy'],S.layout_tie(r['improved']['bins']))

def update_best(s,r):
    if r and r['audit']['valid'] and (s['best'] is None or S.result_key(r)<S.result_key(s['best'])):s['best']=r

def finish_target(s):
    if s['best']:s['stop']='portfolio_complete_with_valid_plan'
    elif s['target']>=s['upper']:s['stop']='portfolio_exhausted_no_valid_plan'
    else:s['target']+=1;s['phase']='construct';s['index']=0;s['selected']=[]

def perform(c,s):
    if s['phase']=='construct':
        r=S.run_task(c,s['target'],S.POLICIES[s['index']]);s['records'].append(r);update_best(s,r['best']);s['index']+=1
        if s['index']==len(S.POLICIES):
            candidates=[j for j,r in enumerate(s['records']) if r['target']==s['target'] and not r['improved']['audit']['unassigned']]
            p=S.normalize(c)['parameters'];candidates.sort(key=lambda j:promising(s['records'][j],p))
            # Select one complete seed per anchor family, then best remaining seeds.
            selected=[]
            for anchor in ('ends','center'):
                family=[j for j in candidates if s['records'][j]['policy'][2]==anchor]
                if family:selected.append(family[0])
            for j in candidates:
                if j not in selected and len(selected)<REPAIR_CANDIDATES:selected.append(j)
            s['selected']=selected;s['phase']='refine';s['index']=0
            if not selected:finish_target(s)
    else:
        source=s['selected'][s['index']];r=s['records'][source]
        refined=allocation.refine(c,r['improved']['bins']);refined['audit']=audit(c,refined['bins']);refined['source_record']=source;refined['target']=s['target']
        s['refinements'].append(refined);update_best(s,dict(bins=refined['bins'],audit=refined['audit']));s['index']+=1
        if s['index']==len(s['selected']):finish_target(s)

def execute(c,path,steps=None,crash=False):
    ctx=context(c);path=Path(path)
    if path.exists():
        s=load(path)
        if s['context']!=ctx:raise ValueError('input, configuration or code changed; cannot resume')
    else:s=make(c);save(path,s)
    if s['pending'] is not None:
        a=s['pending'];s['uncertain']+=1;s['attempt_log'][a-1]['status']='uncertain';s['pending']=None;save(path,s)
    if s['stop']=='attempt_budget_exhausted':return s
    count=0
    while not s['stop'] and (steps is None or count<steps):
        if s['attempts']>=s['attempt_limit']:s['stop']='attempt_budget_exhausted';save(path,s);break
        s['attempts']+=1;s['pending']=s['attempts']
        s['attempt_log'].append(dict(attempt=s['attempts'],target=s['target'],phase=s['phase'],index=s['index'],status='started'))
        save(path,s)
        if crash:return s
        perform(c,s);s['completed']+=1;s['attempt_log'][-1]['status']='complete';s['pending']=None;save(path,s);count+=1
    return s

def main():
    ap=argparse.ArgumentParser();ap.add_argument('config');ap.add_argument('state');ap.add_argument('--steps',type=int);ap.add_argument('--crash',action='store_true')
    args=ap.parse_args()
    if args.steps is not None and args.steps<0:ap.error('--steps must be nonnegative')
    c=json.loads(Path(args.config).read_text(encoding='utf-8'));s=execute(c,Path(args.state),args.steps,args.crash)
    print(json.dumps(dict(stop=s['stop'],completed=s['completed'],uncertain=s['uncertain'],target=s['target'],
                         valid=s['best'] is not None,boxes=s['best']['audit']['n'] if s['best'] else None,business_digest=S.digest(s['best'])),ensure_ascii=False))
if __name__=='__main__':main()
