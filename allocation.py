"""On-demand joint allocation/placement repair, scoped to independent initial candidates."""
from itertools import combinations
from fractions import Fraction as F
import solver as S

VERSION='allocation-trial-0.1'
def refine(c,bins):
    n=S.normalize(c);p=n['parameters'];items={i['id']:i for i in n['items']};cost=S.empty_cost()
    if sorted(r['id'] for b in bins for r in b)!=sorted(items):
        return dict(bins=bins,events=[],cost=cost,stop='unassigned_requires_construction',cache_hits=0,new_sets=0)
    current=[[dict(r,**{k:S.num(r[k]) for k in ('x','y','l','w')},m=items[r['id']]['m']) for r in b] for b in bins]
    area=lambda b:sum((r['l']*r['w'] for r in b),F(0))/(p['L']*p['W'])
    def error(b):return S.penalty(b,p)[0]
    def objective(boxes):
        deficits=sorted([max(F(0),p['util']-area(b)) for b in boxes])
        if n['mode']=='ordinary' and deficits:deficits.pop()
        return sum((error(b) for b in boxes),F(0))+10*sum(deficits,F(0))
    cache={};hits=0;newsets=0;limit=2*len(items)**2;events=[];exhausted=False
    for b in current:cache[tuple(sorted(r['id'] for r in b))]=b
    def repack(ids):
        nonlocal hits,newsets,exhausted
        key=tuple(sorted(ids))
        if key in cache:hits+=1;return cache[key]
        if newsets>=limit:exhausted=True;return None
        newsets+=1
        goods=[items[i] for i in key]
        if sum(i['m'] for i in goods)>p['payload'] or sum(i['l']*i['w'] for i in goods)>p['L']*p['W']:
            cache[key]=None;return None
        best=None;bestkey=None
        # All configured ordering/fit/anchor combinations; failure is limited to this portfolio.
        for order,fit,anchor in S.POLICIES:
            free=[(F(0),F(0),p['L'],p['W'])];box=[]
            for i in sorted(goods,key=lambda i:S.order_key(i,p,order)):
                choices=S.positions(i,free,p,fit,anchor,cost)
                if not choices:break
                r=choices[0][1];box.append(r);free=S.cut(free,S.rect(r),cost)
            if len(box)!=len(goods):continue
            box=S.translate_balance(box,p,cost)
            k=(*S.penalty(box,p),S.layout_tie([box]))
            if bestkey is None or k<bestkey:bestkey=k;best=box
        if best is not None and error(best)>0:
            best,_=S.repair(best,items,p,n['search'],cost)
        cache[key]=best;return best
    for rnd in range(len(items)):
        old=objective(current)
        if old==0:break
        critical={j for j,b in enumerate(current) if error(b)>0 or area(b)<p['util']}
        best=None
        for a,b in combinations(range(len(current)),2):
            if a not in critical and b not in critical:continue
            aa=tuple(sorted(r['id'] for r in current[a]));bb=tuple(sorted(r['id'] for r in current[b]));partitions=set()
            for x in aa:
                if len(aa)>1:partitions.add((tuple(i for i in aa if i!=x),tuple(sorted(bb+(x,)))))
                for y in bb:partitions.add((tuple(sorted(tuple(i for i in aa if i!=x)+(y,))),tuple(sorted(tuple(i for i in bb if i!=y)+(x,)))))
            if len(bb)>1:
                for y in bb:partitions.add((tuple(sorted(aa+(y,))),tuple(i for i in bb if i!=y)))
            for x,y in sorted(partitions):
                ax=sum(items[i]['l']*items[i]['w'] for i in x)/(p['L']*p['W']);ay=sum(items[i]['l']*items[i]['w'] for i in y)/(p['L']*p['W'])
                if ax>1 or ay>1:continue
                # Exact area-only lower bound on trial penalty permits safe rejection.
                trial_def=sorted(max(F(0),p['util']-v) for v in [area(z) for j,z in enumerate(current) if j not in (a,b)]+[ax,ay])
                if n['mode']=='ordinary':trial_def=trial_def[:-1]
                unchanged=sum((error(z) for j,z in enumerate(current) if j not in (a,b)),F(0))
                if unchanged+10*sum(trial_def,F(0))>=old:continue
                bx=repack(x)
                if bx is None:continue
                by=repack(y)
                if by is None:continue
                trial=[bx if j==a else by if j==b else z for j,z in enumerate(current)]
                score=objective(trial)
                if score>=old:continue
                key=(score,a,b,x,y)
                if best is None or key<best[0]:best=(key,trial)
            if exhausted:break
        if best is None:break
        current=best[1];events.append(dict(round=rnd,before=str(old),after=str(best[0][0]),boxes=list(best[0][1:3]),new_members=list(best[0][3:])))
        if exhausted:break
    current=S.canonical_bins(current,p)
    return dict(bins=S.encode(current),events=events,cost=cost,stop='constraints_repaired' if objective(current)==0 else 'budget_exhausted' if exhausted else 'no_improving_one_move_or_swap',
                cache_hits=hits,new_sets=newsets,set_limit=limit)
