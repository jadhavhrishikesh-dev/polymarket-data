import json, os, numpy as np, pandas as pd
W='/home/claude/polymarket-data/data/0xa19cbababc312f9df185e49d7004c249ed1ade6b'
S='/home/claude/polymarket-data/data/_spot'
f=pd.read_pickle('f2.pkl')
meta=f.groupby('token').agg(asset=('asset','first'),sgn=('sgn','first'),kind=('kind','first'),hrs=('hours_left','max'),ts=('ts','first')).reset_index()
meta['end']=meta.ts+meta.hrs*3600
spot={s:pd.DataFrame(json.load(open(f'{S}/{s}.json')),columns=['ts','o','h','l','c']).sort_values('ts') for s in ['BTC','ETH','WTI','SOL']}
def sp(a,ts):
    d=spot[a]; i=np.searchsorted(d.ts.values,ts,side='right')-1; return d.c.values[np.clip(i,0,None)]
rows=[]
for _,m in meta.iterrows():
    fn=f'{W}/prices/{m.token}.json'
    if not os.path.exists(fn): continue
    p=pd.DataFrame(json.load(open(fn)))
    if len(p)<60: continue
    p=p.sort_values('timestamp'); p=p[p.resolution_seconds<=1800]
    t=p.timestamp.values; px=p.price.values
    ok=(t<m.end-24*3600)&(px>0.03)&(px<0.97)
    for lb in [4]:
        r=np.log(sp(m.asset,t)/sp(m.asset,t-lb*3600))*m.sgn
    j=np.searchsorted(t,t+24*3600)
    valid=ok&(j<len(t))
    fwd=np.where(valid,px[np.clip(j,0,len(t)-1)]-px,np.nan)
    for a,b,c,tt in zip(r[valid],fwd[valid],px[valid],t[valid]):
        rows.append((m.token,m.asset,tt,a,b,c))
d=pd.DataFrame(rows,columns=['token','asset','ts','mom','fwd','px'])
d=d.dropna()
print('bars',len(d),'tokens',d.token.nunique())
cost=0.01
for thr in [0,0.005,0.01,0.02,0.03]:
    s=d[d.mom>thr]
    print(f'BUY when 4h spot move in favour >{thr*100:.1f}%: n={len(s):6d} mean 24h gain {100*(s.fwd.mean()-cost):+.2f}c/share  hit {(s.fwd>cost).mean():.3f}')
print(f'baseline (all bars)          : n={len(d):6d} mean 24h gain {100*(d.fwd.mean()-cost):+.2f}c')
for thr in [0.01,0.02]:
    s=d[d.mom<-thr]
    print(f'FADE: buy when move AGAINST >{thr*100:.0f}% : n={len(s):6d} mean {100*(s.fwd.mean()-cost):+.2f}c')
# by month split to check stability
d['mo']=pd.to_datetime(d.ts,unit='s').dt.to_period('M')
s=d[d.mom>0.01]
print(s.groupby('mo').fwd.agg(['size','mean']).assign(mean=lambda x:((x['mean']-cost)*100).round(2)))
print(s.groupby('asset').fwd.agg(['size','mean']).assign(mean=lambda x:((x['mean']-cost)*100).round(2)))
