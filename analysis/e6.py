import json, os, numpy as np, pandas as pd
W='/home/claude/polymarket-data/data/0xa19cbababc312f9df185e49d7004c249ed1ade6b'
tr=pd.DataFrame(json.load(open(W+'/trades.json'))); tk=json.load(open(W+'/trades_taker.json'))
tkey=set((t['transaction_hash'],t['token_id'],round(t['size'],4)) for t in tk)
tr['taker']=[(h,tok,round(s,4)) in tkey for h,tok,s in zip(tr.transaction_hash,tr.token_id,tr['size'])]
tr['usd']=tr['size']*tr.price
print('taker fills',tr.taker.sum(),'of',len(tr),' taker $ share',round(tr[tr.taker].usd.sum()/tr.usd.sum(),3))
print('median price taker vs maker',tr.groupby('taker').price.median().to_dict(),'median $',tr.groupby('taker').usd.median().round(1).to_dict())
# markouts
H={}
for fn in os.listdir(W+'/prices'):
    p=json.load(open(f'{W}/prices/{fn}'))
    if p: H[fn[:-5]]=pd.DataFrame(p).sort_values('timestamp')
def at(tok,ts):
    d=H[tok]; i=np.searchsorted(d.timestamp.values,ts,side='right')-1
    return d.price.values[i] if i>=0 else np.nan
m=tr[tr.token_id.isin(H)].copy()
for h in [1,6,24,72]:
    m[f'mo{h}']=[at(tok,ts+h*3600)-p for tok,ts,p in zip(m.token_id,m.timestamp,m.price)]
print('fills with history',len(m),' $ share',round(m.usd.sum()/tr.usd.sum(),3))
cols=['mo1','mo6','mo24','mo72']
print('markout (price change in fill direction, cents), $-weighted:')
for k,x in m.groupby('taker'):
    print(' taker' if k else ' maker', [round(100*np.nansum(x[c]*x.usd)/x.usd[x[c].notna()].sum(),2) for c in cols])
print(' all eq-weighted', (m[cols].mean()*100).round(2).to_dict())
# pnl contribution if marked at +72h
m['pnl72']=m['size']*m.mo72
print('pnl if exited at +72h: maker',round(m[~m.taker].pnl72.sum()),'taker',round(m[m.taker].pnl72.sum()))
# where are maker bids relative to prevailing price? price at fill vs last history point before
m['pre']=[at(tok,ts-1800) for tok,ts in zip(m.token_id,m.timestamp)]
m['vs_pre']=m.price-m.pre
print('fill price minus price 30m before (cents) median: maker',round(100*m[~m.taker].vs_pre.median(),2),'taker',round(100*m[m.taker].vs_pre.median(),2))
tr.to_pickle('tr.pkl')
