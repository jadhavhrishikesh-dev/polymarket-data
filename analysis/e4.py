import json, collections, pandas as pd, numpy as np
W='/home/claude/polymarket-data/data/0xa19cbababc312f9df185e49d7004c249ed1ade6b'
tr=sorted(json.load(open(W+'/trades.json')),key=lambda t:t['timestamp'])
g=collections.defaultdict(list)
for t in tr: g[t['condition_id']].append(t)
rows=[]
for c,ts in g.items():
    first=ts[0]['outcome_index']
    A=[t for t in ts if t['outcome_index']==first]; B=[t for t in ts if t['outcome_index']!=first]
    if not B: continue
    tb=B[0]['timestamp']
    pre=[t for t in A if t['timestamp']<=tb]
    qa=sum(t['size'] for t in pre); a=sum(t['size']*t['price'] for t in pre)/qa
    qb=sum(t['size'] for t in B); b=sum(t['size']*t['price'] for t in B)/qb
    b0=B[0]['price']
    rows.append(dict(title=ts[0]['title'],a=a,b_first=b0,b_avg=b,implied_first_leg=1-b0,gain=(1-b0)/a-1,
                     lock=1-a-b0,hrs=(tb-ts[0]['timestamp'])/3600,qa=qa,qb=qb,cover=qb/qa,
                     reentries=sum(1 for t in A if t['timestamp']>tb)))
d=pd.DataFrame(rows)
print('markets hedged',len(d))
print('first-leg value change at first hedge fill (gain %) quantiles'); print((d.gain*100).quantile([.05,.1,.25,.5,.75,.9,.95]).round(1))
d['gb']=pd.cut(d.gain,[-1,-.5,-.25,-.1,0,.1,.25,.5,1,100])
print(d.groupby('gb',observed=True).agg(n=('a','size'),cover=('cover','median'),hrs=('hrs','median'),entry=('a','median')).round(2))
print('cover ratio (opp shares / first-leg shares) quantiles'); print(d.cover.quantile([.1,.25,.5,.75,.9]).round(2))
print('hedge happens when first leg up:',(d.gain>0).mean().round(3))
print('entry price of first leg for hedged vs all markets:', d.a.median().round(3))
print('share fully covered (0.9-1.1):',d.cover.between(.9,1.1).mean().round(3))
