"""PACKING trial. Deterministic finite portfolio; no claim of exhaustive search."""
from fractions import Fraction as F
from itertools import combinations
import json, hashlib, math
from audit import audit

VERSION='direct-space-trial-0.1'
ORDERS=('difficult','area','long','heavy')
POLICIES=[(o,f,a) for o in ORDERS for f in ('short_side','waste') for a in ('ends','center')]

def num(v):
    if v is None or isinstance(v,bool):raise ValueError('numeric value missing or boolean')
    try:r=F(str(v))
    except (ValueError,ZeroDivisionError):raise ValueError('numeric value not finite') from None
    return r

def normalize(c):
    if c.get('schema')!='PACKING-TRIAL-1':raise ValueError('schema')
    if c.get('mode') not in ('ordinary','all_qualified'):raise ValueError('mode')
    if c.get('require_all') is not True:raise ValueError('trial supports fixed all-required scope only')
    p=c['parameters']; keys=('L','W','H','payload','fb','lr','util')
    if set(p)-set(keys)-{'height_check'}:raise ValueError('unsupported parameter')
    par={k:num(p[k]) for k in keys}
    if any(par[k]<=0 for k in ('L','W','H','payload','util')) or par['util']>1 or par['fb']<0 or par['lr']<0:raise ValueError('parameter range')
    if type(p.get('height_check')) is not bool:raise ValueError('height_check')
    par['height_check']=p['height_check'];items=[];ids=set()
    for s in c['items']:
        ident=s['id']
        if not isinstance(ident,str) or not ident.strip() or ident in ids:raise ValueError('ID empty, nontext or duplicate')
        ids.add(ident);i={k:num(s[k]) for k in ('l','w','h','m')}
        if min(i.values())<=0:raise ValueError('nonpositive cargo')
        al=s['allowed']
        if not isinstance(al,list) or not al or any(type(v)is not int or v not in (0,90) for v in al):raise ValueError('allowed orientations')
        i.update(id=ident,allowed=sorted(set(al)));items.append(i)
    search=c['search']
    if set(search)!={'repair_rounds','repair_options','attempt_reserve'}:raise ValueError('search configuration')
    if any(type(v)is not int or v<0 for v in search.values()) or search['repair_options']<1:raise ValueError('search configuration range')
    return dict(parameters=par,items=sorted(items,key=lambda i:i['id']),mode=c['mode'],search=search.copy())

def encode(v):
    if isinstance(v,F):return str(v)
    if isinstance(v,dict):return {k:encode(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [encode(x) for x in v]
    return v

def canon(v):return json.dumps(encode(v),sort_keys=True,ensure_ascii=False,separators=(',',':'))
def digest(v):return hashlib.sha256(canon(v).encode()).hexdigest()
def orientations(i,p):
    values=[(o,i['l'] if o==0 else i['w'],i['w'] if o==0 else i['l']) for o in i['allowed']]
    values=[v for v in values if v[1]<=p['L'] and v[2]<=p['W']]
    if i['l']==i['w'] and len(values)==2:values=values[:1]
    return sorted(values,key=lambda v:(v[1]<v[2],v[0]))

def order_key(i,p,kind):
    area=i['l']*i['w'];long=max(i['l'],i['w']);short=min(i['l'],i['w'])
    physical=(len(orientations(i,p)),-short,-long,-area,-i['m'],i['h'])
    key={'difficult':physical,'area':(-area,*physical),'long':(-long,*physical),'heavy':(-i['m'],*physical)}[kind]
    return (*key,i['id'])

def rect(r):return r['x'],r['y'],r['l'],r['w']
def overlaps(a,b):return a[0]<b[0]+b[2] and b[0]<a[0]+a[2] and a[1]<b[1]+b[3] and b[1]<a[1]+a[3]
def cut(frees,r,cost):
    x,y,l,w=r;result=[]
    for f in frees:
        cost['free_split']+=1
        if not overlaps(f,r):result.append(f);continue
        a,b,c,d=f
        if x>a:result.append((a,b,x-a,d))
        if x+l<a+c:result.append((x+l,b,a+c-x-l,d))
        if y>b:result.append((a,b,c,y-b))
        if y+w<b+d:result.append((a,y+w,c,b+d-y-w))
    result=sorted(set(result));keep=[]
    for j,a in enumerate(result):
        contained=False
        for k,b in enumerate(result):
            cost['free_containment']+=1
            if j!=k and b[0]<=a[0] and b[1]<=a[1] and b[0]+b[2]>=a[0]+a[2] and b[1]+b[3]>=a[1]+a[3]:contained=True;break
        if not contained:keep.append(a)
    return keep

def free_of(box,p,cost):
    frees=[(F(0),F(0),p['L'],p['W'])]
    for r in box:frees=cut(frees,rect(r),cost)
    return frees

def positions(i,frees,p,fit,anchor,cost):
    found={}
    for o,l,w in orientations(i,p):
        for x,y,a,b in frees:
            cost['free_fit']+=1
            if l>a or w>b:continue
            xs=[x,x+a-l];ys=[y,y+b-w]
            if anchor=='center':xs.append(x+(a-l)/2);ys.append(y+(b-w)/2)
            for xx in sorted(set(xs)):
                for yy in sorted(set(ys)):
                    cost['positions']+=1
                    waste=a*b-l*w;short=min(a-l,b-w);long=max(a-l,b-w)
                    spatial=(short,long,waste) if fit=='short_side' else (waste,short,long)
                    # Center family explicitly prefers centered free-space placement.
                    loc=(abs(xx+l/2-p['L']/2),abs(yy+w/2-p['W']/2)) if anchor=='center' else (xx,yy)
                    key=(*spatial,*loc,l<w,o,xx,yy)
                    r=dict(id=i['id'],x=xx,y=yy,l=l,w=w,m=i['m'],ori=o)
                    ident=(o,xx,yy)
                    if ident not in found or key<found[ident][0]:found[ident]=(key,r)
    return sorted(found.values(),key=lambda t:t[0])

def balance_values(box,p):
    weight=sum((r['m'] for r in box),F(0))
    left=sum((r['m']*max(F(0),min(r['x']+r['l'],p['L']/2)-r['x'])/r['l'] for r in box),F(0))
    fb=abs(weight-2*left)
    lr=abs(sum((r['m']*(r['y']+r['w']/2) for r in box),F(0))/weight-p['W']/2) if weight else F(0)
    return fb,lr

def translate_balance(box,p,cost):
    if not box:return []
    cost['balance']+=1
    lo=-min(r['x'] for r in box);hi=p['L']-max(r['x']+r['l'] for r in box)
    mass=sum(r['m'] for r in box);mid=p['L']/2
    def signed(dx):return mass-2*sum(r['m']*min(r['l'],max(F(0),mid-r['x']-dx))/r['l'] for r in box)
    breaks=sorted({lo,hi}|{v for r in box for v in (mid-r['x']-r['l'],mid-r['x']) if lo<=v<=hi})
    candidates=set(breaks)
    for a,b in zip(breaks,breaks[1:]):
        fa,fb=signed(a),signed(b)
        if fa<=0<=fb and fb!=fa:candidates.add(a-fa*(b-a)/(fb-fa))
    dx=min(candidates,key=lambda v:(abs(signed(v)),abs(v),v))
    cog=sum(r['m']*(r['y']+r['w']/2) for r in box)/mass
    dy=max(-min(r['y'] for r in box),min(p['W']-max(r['y']+r['w'] for r in box),p['W']/2-cog))
    return [dict(r,x=r['x']+dx,y=r['y']+dy) for r in box]

def penalty(box,p):
    fb,lr=balance_values(box,p)
    return (max(F(0),fb-p['fb'])/max(F(1),p['fb'])+max(F(0),lr-p['lr'])/max(F(1),p['lr']),fb,lr)

def repair(box,items,p,search,cost):
    current=translate_balance(box,p,cost);events=[]
    if not current:return current,events
    for rnd in range(search['repair_rounds']):
        old=penalty(current,p)
        if old[0]==0:break
        choices=[]
        members=sorted(current,key=lambda r:(-r['m'],r['id']))
        # Same-footprint swaps jointly relocate two real cargos, without precombination.
        for a,b in combinations(members,2):
            if (a['l'],a['w'])!=(b['l'],b['w']):continue
            trial=[dict(r,x=b['x'],y=b['y']) if r['id']==a['id'] else dict(r,x=a['x'],y=a['y']) if r['id']==b['id'] else r for r in current]
            trial=translate_balance(trial,p,cost);cost['repair_evaluations']+=1
            choices.append((penalty(trial,p),('swap',a['id'],b['id']),trial))
        # Single release and reinsertion, then rebalance all members simultaneously.
        for r in members:
            fixed=[s for s in current if s['id']!=r['id']];free=free_of(fixed,p,cost)
            opts=positions(items[r['id']],free,p,'waste','center',cost)
            cost['repair_options_omitted']+=max(0,len(opts)-search['repair_options'])
            for k,(_,v) in enumerate(opts[:search['repair_options']]):
                trial=translate_balance(fixed+[v],p,cost);cost['repair_evaluations']+=1
                choices.append((penalty(trial,p),('reinsert',r['id'],str(k)),trial))
        if not choices:break
        best=min(choices,key=lambda c:(c[0],c[1]))
        if best[0]>=old:break
        current=best[2];events.append(dict(round=rnd,action=best[1],before=encode(old),after=encode(best[0])))
    return current,events

def empty_cost():return {k:0 for k in ('free_split','free_containment','free_fit','positions','balance','repair_evaluations','repair_options_omitted')}

def canonical_bins(bins,p):
    boxes=[sorted(b,key=lambda r:r['id']) for b in bins if b]
    return sorted(boxes,key=lambda b:(sum(r['l']*r['w'] for r in b)<p['util']*p['L']*p['W'],tuple(r['id'] for r in b)))

def layout_tie(bins):
    boxes=sorted([sorted(b,key=lambda r:r['id']) for b in bins],key=lambda b:tuple(r['id'] for r in b))
    return (tuple(tuple(r['id'] for r in b) for b in boxes),tuple(r['ori'] for b in boxes for r in b),tuple((num(r['x']),num(r['y'])) for b in boxes for r in b))

def result_key(r):
    a=r['audit'];return (a['n'],-num(a['front_mean']) if a['front_mean'] is not None else F(0),layout_tie(r['bins']))

def run_task(c,target,policy):
    norm=normalize(c);p=norm['parameters'];byid={i['id']:i for i in norm['items']};o,fit,anchor=policy
    ordered=sorted(norm['items'],key=lambda i:order_key(i,p,o));cost=empty_cost();boxes=[];frees=[];masses=[];events=[];missing=[]
    for i in ordered:
        selected=None
        for b in range(min(len(boxes)+1,target)):
            is_new=b==len(boxes)
            if (F(0) if is_new else masses[b])+i['m']>p['payload']:continue
            free=[(F(0),F(0),p['L'],p['W'])] if is_new else frees[b]
            opts=positions(i,free,p,fit,anchor,cost)
            if opts:selected=(b,opts[0][1],is_new);break
        if selected is None:missing.append(i['id']);events.append(dict(action='unplaced',id=i['id']));continue
        b,r,new=selected
        if new:boxes.append([]);frees.append([(F(0),F(0),p['L'],p['W'])]);masses.append(F(0))
        boxes[b].append(r);masses[b]+=r['m'];frees[b]=cut(frees[b],rect(r),cost)
        events.append(dict(action='place',bin=b,id=i['id'],placement=encode(r),remaining_free=len(frees[b])))
    baseline=canonical_bins([translate_balance(b,p,cost) for b in boxes],p)
    bresult=dict(bins=encode(baseline),audit=audit(c,encode(baseline)))
    modified=[];repairs=[]
    for bi,b in enumerate(baseline):
        fixed,log=repair(b,byid,p,norm['search'],cost);modified.append(fixed)
        repairs.extend(dict(bin=bi,**e) for e in log)
    improved=canonical_bins(modified,p)
    rresult=dict(bins=encode(improved),audit=audit(c,encode(improved)))
    valid=[r for r in (bresult,rresult) if r['audit']['valid']]
    return dict(target=target,policy=list(policy),order=[i['id'] for i in ordered],events=events,repairs=repairs,cost=cost,
                baseline=bresult,improved=rresult,best=min(valid,key=result_key) if valid else None)

def bounds(c):
    n=normalize(c);p=n['parameters'];items=n['items'];a=sum((i['l']*i['w'] for i in items),F(0));m=sum((i['m'] for i in items),F(0))
    lower=max(math.ceil(a/(p['L']*p['W'])),math.ceil(m/p['payload']))
    upper=math.floor(a/(p['L']*p['W']*p['util']))+(1 if n['mode']=='ordinary' else 0)
    return lower,min(len(items),upper)

def initial(c):
    n=normalize(c);lo,hi=bounds(c)
    oversized=[i['id'] for i in n['items'] if not orientations(i,n['parameters']) or i['m']>n['parameters']['payload'] or (n['parameters']['height_check'] and i['h']>n['parameters']['H'])]
    state=dict(version=VERSION,lower=lo,upper=hi,target=lo,policy_index=0,records=[],best=None,stop=None)
    if oversized:state.update(stop='proven_single_item_constraint',blocked_ids=oversized)
    elif lo>hi:state['stop']='proven_bounds_conflict'
    elif not n['items']:state.update(stop='empty',best=dict(bins=[],audit=audit(c,[])))
    return state

def advance(c,state):
    if state['stop']:return
    r=run_task(c,state['target'],POLICIES[state['policy_index']]);state['records'].append(r)
    if r['best'] and (not state['best'] or result_key(r['best'])<result_key(state['best'])):state['best']=r['best']
    state['policy_index']+=1
    if state['policy_index']==len(POLICIES):
        if state['best']:state['stop']='portfolio_complete_with_valid_plan'
        elif state['target']>=state['upper']:state['stop']='portfolio_exhausted_no_valid_plan'
        else:state['target']+=1;state['policy_index']=0

def run_all(c):
    state=initial(c)
    while not state['stop']:advance(c,state)
    return state
