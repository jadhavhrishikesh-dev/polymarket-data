import pandas as pd, numpy as np, json, bisect
f=pd.read_csv('fills.csv')
R='/home/claude/polymarket-data/data/_spot'
sp={s:pd.DataFrame(json.load(open(f'{R}/{s}.json')),columns=['ts','o','h','l','c']).sort_values('ts') for s in ['BTC','ETH','WTI','SOL']}
def px(a,ts):
    d=sp[a]; i=np.searchsorted(d.ts.values,ts,side='right')-1
    return d.c.values[i] if 0<=i<len(d) else np.nan
up=(f.dir.isin(['up','above'])); yes=f.outcome.eq('Yes')
f['sgn']=np.where(up==yes,1,-1)  # +1 bullish bet
for h in [-24,-4,-1,1,4,24]:
    f[f'r{h}']=[ (px(a,t+h*3600)/px(a,t)-1) if h>0 else (px(a,t)/px(a,t+h*3600)-1) for a,t in zip(f.asset,f.ts)]
    f[f'a{h}']=f[f'r{h}']*f.sgn*1e4  # bps in favour of bet
cols=[c for c in f.columns if c.startswith('a') and c[1:].lstrip('-').isdigit()]
print('mean spot move in favour of bet (bps), equal-weighted:'); print(f[cols].mean().round(1))
print('usd-weighted:'); print(f[cols].mul(f.usd,axis=0).sum().div(f.usd.sum()).round(1))
print('share where prior 4h move aligned with bet',(f['a-4']>0).mean().round(3),' prior 24h',(f['a-24']>0).mean().round(3))
print(f.groupby('asset')[cols].mean().round(1))
# stance vs recent trend: do they bet bear after drops?
f['trend24']=np.sign(f['r-24'])
print(pd.crosstab(f.trend24,f.sgn,values=f.usd,aggfunc='sum',normalize='index').round(3))
f.to_pickle('f2.pkl')
