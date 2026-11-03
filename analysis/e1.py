import pandas as pd, numpy as np
f=pd.read_csv('fills.csv'); r=f[f.won!=''].copy() if f.won.dtype==object else f[f.won.notna()].copy()
r['won']=r.won.astype(float)
print('resolved fills',len(r))
# calibration: brier market vs model
print('Brier market',((r.price-r.won)**2).mean().round(4),'model',((r.fair-r.won)**2).mean().round(4))
# usd-weighted EV per $ of fills
r['pnl']=r['size']*(r.won-r.price)
print('fill-level pnl (hold to resolution)',round(r.pnl.sum()))
print('mean edge (model-price)',round(r.edge.mean(),4),'usd-weighted',round((r.edge*r.usd).sum()/r.usd.sum(),4))
r['eb']=pd.cut(r.edge,[-1,-.2,-.1,-.05,0,.05,.1,.2,1])
g=r.groupby('eb',observed=True).agg(n=('price','size'),usd=('usd','sum'),avgp=('price','mean'),winrate=('won','mean'),pnl=('pnl','sum'))
print(g.round(3))
r['pb']=pd.cut(r.price,[0,.05,.1,.2,.4,.6,.8,.9,.95,1])
g=r.groupby('pb',observed=True).agg(n=('price','size'),avgp=('price','mean'),fair=('fair','mean'),win=('won','mean'),pnl=('pnl','sum'))
print(g.round(3))
print(r.groupby(['asset','kind']).agg(n=('price','size'),usd=('usd','sum'),edge=('edge','mean'),win=('won','mean'),avgp=('price','mean'),pnl=('pnl','sum')).round(3))
# direction of bet: bullish/bearish? yes on up / no on down = bullish
def stance(x):
    up = (x.dir in('up','above'))
    yes = x.outcome=='Yes'
    return 'bull' if up==yes else 'bear'
f['stance']=f.apply(stance,axis=1)
print(f.groupby(['asset','stance']).usd.sum().round())
# moneyness: are they betting price stays (No on far barriers) or moves?
f['far']=f.dist.abs()
f['bet_move']=((f.kind=='touch')&(f.outcome=='Yes'))
print(f.groupby(['kind','outcome']).agg(n=('price','size'),usd=('usd','sum'),avgp=('price','mean'),dist=('far','median'),hrs=('hours_left','median')).round(3))
