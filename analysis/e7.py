import pandas as pd, numpy as np
f=pd.read_pickle('f2.pkl'); tr=pd.read_pickle('tr.pkl')
k=tr.set_index(['timestamp','token_id','price'])['taker']
k=k[~k.index.duplicated()]
f['taker']=[k.get((a,str(b) if False else b,c),np.nan) for a,b,c in zip(f.ts,f.token.astype(str),f.price)]
tr2=tr.assign(token_id=tr.token_id.astype(str))
mp=dict(zip(zip(tr2.timestamp,tr2.token_id,tr2.price),tr2.taker))
f['taker']=[mp.get((a,str(b),c)) for a,b,c in zip(f.ts,f.token,f.price)]
print(f.taker.value_counts(dropna=False))
cols=['a-24','a-4','a-1','a1','a4','a24']
for t,x in f.groupby('taker'):
    print('TAKER' if t else 'MAKER','eq',x[cols].mean().round(1).to_dict())
    print('      $w',(x[cols].mul(x.usd,axis=0).sum()/x.usd.sum()).round(1).to_dict())
r=f[f.won.notna()&(f.won!='')].copy(); r['won']=r.won.astype(float); r['pnl']=r['size']*(r.won-r.price)
print(r.groupby('taker').agg(n=('price','size'),usd=('usd','sum'),win=('won','mean'),avgp=('price','mean'),pnl=('pnl','sum')).round(3))
print(f.groupby(['taker','outcome','kind']).usd.sum().round())
