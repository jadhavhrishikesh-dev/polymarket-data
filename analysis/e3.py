import json, collections, pandas as pd, numpy as np
W='/home/claude/polymarket-data/data/0xa19cbababc312f9df185e49d7004c249ed1ade6b'
tr=json.load(open(W+'/trades.json')); ac=json.load(open(W+'/activity.json'))
pos=sum([json.load(open(f'{W}/{n}.json')) for n in ['positions_closed','positions_open','positions_redeemable','positions_redeemable_lost']],[])
price={p['token_id']:p['current_price'] for p in pos}
for p in pos:
    if p.get('opposite_token_id') and p['opposite_token_id'] not in price: price[p['opposite_token_id']]=1-p['current_price']
by=collections.defaultdict(lambda: collections.defaultdict(lambda:[0.0,0.0,None]))
for t in tr:
    s=by[t['condition_id']][t['outcome_index']]; s[0]+=t['size']; s[1]+=t['size']*t['price']; s[2]=t['token_id']
merged=collections.Counter()
for a in ac:
    if a['type']=='MERGE': merged[a['condition_id']]+=a['size']
spread=dirn=0.0; rows=[]
for c,v in by.items():
    if len(v)==2:
        (q0,c0,t0),(q1,c1,t1)=v[0],v[1]
        q=min(q0,q1); a0,a1=c0/q0,c1/q1
        sp=q*(1-a0-a1)
        rq0,rq1=q0-q,q1-q
        p0=price.get(t0,np.nan); p1=price.get(t1,np.nan)
        d=rq0*(p0-a0)+rq1*(p1-a1)
    else:
        (i,(qq,cc,tt)),=v.items(); sp=0; q=0
        d=qq*(price.get(tt,np.nan)-cc/qq)
    spread+=sp; dirn+=0 if np.isnan(d) else d
    rows.append(dict(cond=c,matched=q,spread=sp,dir=d,merged=merged[c]))
df=pd.DataFrame(rows)
print('spread capture on matched pairs: $',round(spread))
print('directional (mark-to-current-price): $',round(dirn))
print('matched shares',round(df.matched.sum()),' merged shares',round(sum(merged.values())))
print('markets w/ positive spread',(df[df.matched>0].spread>0).mean().round(3))
print(df.sort_values('spread').head(5)[['spread','dir']].round(0).to_string()); print(df.sort_values('spread').tail(5)[['spread','dir']].round(0).to_string())
# merge timing: how long after 2nd leg buy does merge happen
