import pandas as pd, numpy as np
f=pd.read_pickle('f2.pkl')
# per-market size and how adds relate to price moves
f=f.sort_values('ts')
g=f.groupby(['cond','outcome'])
rows=[]
for (c,o),x in g:
    if len(x)<5: continue
    p=x.price.values; sz=x.usd.values
    first=p[0]
    adds_up=(p[1:]>first).mean()  # adding after price rose (pyramiding) vs fell (averaging down)
    rows.append(dict(title=x.title.iloc[0][:55],o=o,n=len(x),usd=sz.sum(),first=first,last=p[-1],avg=np.average(p,weights=x['size']),pyramid=adds_up,days=(x.ts.max()-x.ts.min())/86400))
d=pd.DataFrame(rows).sort_values('usd',ascending=False)
print('markets with 5+ fills on a side',len(d))
print('share of later adds at a HIGHER price than first fill (pyramiding):',np.average(d.pyramid,weights=d.usd).round(3))
print(d.head(15).round(3).to_string())
# size vs features
f['lusd']=np.log10(f.usd.clip(lower=.5))
print('\ncorr of log fill size with features'); print(f[['lusd','price','hours_left','edge','vol_ann']].assign(absdist=f.dist.abs()).corr()['lusd'].round(3))
print('\nfill size by hours left'); print(f.groupby(pd.cut(f.hours_left,[0,6,24,72,168,720,5000]),observed=True).agg(n=('usd','size'),med_usd=('usd','median'),tot=('usd','sum')).round(0))
# ladders: same expiry, multiple strikes same timestamp hour
f['hr']=f.ts//3600
lad=f.groupby(['asset','hr']).cond.nunique()
print('\nhours with fills in >=3 different strike markets of same asset:',(lad>=3).mean().round(3))
