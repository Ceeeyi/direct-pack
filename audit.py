"""Independent exact audit. Does not import solver or trust its metrics."""
from fractions import Fraction as Q

def number(v):
    if v is None or isinstance(v,bool): raise ValueError('invalid numeric value')
    try: return Q(str(v))
    except (ValueError,ZeroDivisionError): raise ValueError('invalid numeric value') from None

def audit(config,bins):
    p=config['parameters']; L,W,H,P,FB,LR,U=[number(p[k]) for k in ['L','W','H','payload','fb','lr','util']]
    source={i['id']:i for i in config['items']}
    if len(source)!=len(config['items']):raise ValueError('duplicate source ID')
    seen=[]; reports=[]; errors=[]
    for box in bins:
        if not box:errors.append('empty_bin')
        weight=Q(0); area=Q(0); volume=Q(0); left=Q(0); moment_y=Q(0);fail=[]; rects=[]
        for r in box:
            ident=r['id'];seen.append(ident)
            if ident not in source:fail.append('unknown_ID');continue
            s=source[ident]; x,y,l,w=[number(r[k]) for k in ['x','y','l','w']];m=number(s['m']);h=number(s['h'])
            ori=r['ori'];allowed=s['allowed']; orig=(number(s['l']),number(s['w']))
            expected=orig if ori==0 else orig[::-1]
            if ori not in (0,90) or ori not in allowed:fail.append('orientation')
            if (l,w)!=expected:fail.append('source_dimensions')
            if l<=0 or w<=0:fail.append('nonpositive');continue
            if x<0 or y<0 or x+l>L or y+w>W:fail.append('boundary')
            if number(r.get('z',0))!=0:fail.append('stacking')
            if p.get('height_check',False) and h>H:fail.append('height')
            if 'm' in r and number(r['m'])!=m:fail.append('source_mass')
            weight+=m; area+=number(s['l'])*number(s['w']);volume+=number(s['l'])*number(s['w'])*h
            # Integrate uniform linear mass density over the left half.
            intersection=max(Q(0),min(x+l,L/2)-max(x,Q(0)))
            left+=m*intersection/l;moment_y+=m*(y+w/2)
            rects.append((ident,x,y,x+l,y+w))
        # Independent sweep along X, active rectangles checked in Y.
        active=[]
        for r in sorted(rects,key=lambda a:(a[1],a[2],a[0])):
            active=[a for a in active if a[3]>r[1]]
            if any(max(a[2],r[2])<min(a[4],r[4]) for a in active):fail.append('overlap')
            active.append(r)
        fb=abs(weight-2*left);lr=abs(moment_y/weight-W/2) if weight else Q(0)
        if weight>P:fail.append('payload')
        if fb>FB:fail.append('FB')
        if lr>LR:fail.append('LR')
        util=area/(L*W);low=util<U
        reports.append(dict(ids=sorted(r['id'] for r in box),failures=sorted(set(fail)),
                            mass=str(weight),area_mm2=str(area),volume_mm3=str(volume),util=str(util),
                            mass_util=str(weight/P),volume_util=str(volume/(L*W*H)),fb=str(fb),lr=str(lr),low_area=low,
                            height_check='checked' if p.get('height_check',False) else 'not_verified'))
    if len(set(seen))!=len(seen):errors.append('duplicate_placement')
    missing=sorted(set(source)-set(seen));unknown=sorted(set(seen)-set(source))
    if missing:errors.append('unassigned')
    if unknown:errors.append('unknown_ID')
    lows=[i for i,r in enumerate(reports) if r['low_area']]
    if config['mode']=='all_qualified' and lows:errors.append('all_qualified_area')
    if config['mode']=='ordinary' and (len(lows)>1 or (lows and lows[0]!=len(reports)-1)):errors.append('tail_area_rule')
    if any(r['failures'] for r in reports):errors.append('box_constraints')
    valid=not errors
    qualified=[r for r in reports if not r['failures'] and not r['low_area']]
    front=sum((Q(r['area_mm2']) for r in qualified),Q(0))/(len(qualified)*L*W) if qualified else None
    return dict(valid=valid,errors=sorted(set(errors)),n=len(bins),unassigned=missing,bins=reports,
                front_mean=None if front is None else str(front),overall_mean=str(sum((Q(r['area_mm2']) for r in reports),Q(0))/(len(bins)*L*W)) if bins else None,
                stage=('waiting_human_tail' if lows else 'complete') if valid else 'search_incomplete')
