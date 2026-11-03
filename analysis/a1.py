import json,sys,collections,statistics as st,datetime as dt,re
D=sys.argv[1]
L=lambda n: json.load(open(f'{D}/{n}.json'))
cl=L('positions_closed'); op=L('positions_open'); tr=L('trades'); ac=L('activity')
print('closed keys',list(cl[0].keys()))
print('trade keys',list(tr[0].keys()))
def cat(t):
    t=t.lower()
    if 'up or down' in t: return 'crypto up/down (short-term)'
    if any(k in t for k in ['bitcoin','ethereum','solana','xrp','btc','eth ','crypto','doge']): 
        if any(k in t for k in ['dip to','reach','above','below','hit','price of','between']): return 'crypto price levels'
        return 'crypto other'
    if any(k in t for k in [' vs',' vs.','win on','nba','nfl','mlb','nhl','ufc','premier','fc ','o/u','spread','match','game']): return 'sports'
    if any(k in t for k in ['election','trump','president','senate','governor','mayor','republican','democrat','vote','house']): return 'politics'
    if any(k in t for k in ['fed','rate','cpi','inflation','gdp','jobs','recession']): return 'macro'
    return 'other'
ty=collections.Counter(a['type'] for a in ac); print('activity types',ty)
c=collections.defaultdict(lambda:[0,0,0.0,0.0])
for p in cl:
    k=cat(p['title']); c[k][0]+=1; c[k][1]+= p['realized_pnl']>0; c[k][2]+=p['realized_pnl']; c[k][3]+=p['total_cost_usdc']
print('\nCLOSED by category: n, win%, pnl, cost')
for k,v in sorted(c.items(),key=lambda x:-x[1][2]): print(f'{k:30s} {v[0]:5d} {100*v[1]/v[0]:5.1f}% {v[2]:12,.0f} {v[3]:12,.0f}')
tot=sum(p['realized_pnl'] for p in cl); print('total realized closed',round(tot), 'win rate', sum(p['realized_pnl']>0 for p in cl)/len(cl))
s=sorted(cl,key=lambda p:-p['realized_pnl'])
print('\nTOP 12 winners'); [print(f"{p['realized_pnl']:11,.0f} avg {p['avg_price']:.3f} size {p['total_size']:10,.0f} {p['title'][:70]} [{p.get('outcome')}]") for p in s[:12]]
print('\nTOP 8 losers'); [print(f"{p['realized_pnl']:11,.0f} avg {p['avg_price']:.3f} {p['title'][:70]} [{p.get('outcome')}]") for p in s[-8:]]
print('share of pnl from top 10:', sum(p['realized_pnl'] for p in s[:10])/tot)
# entry price buckets on closed positions
b=collections.defaultdict(lambda:[0,0,0.0])
for p in cl:
    x=p['avg_price']; k=min(int(x*10),9)/10
    b[k][0]+=1; b[k][1]+=p['realized_pnl']>0; b[k][2]+=p['realized_pnl']
print('\nENTRY PRICE bucket: n win% pnl')
for k in sorted(b): v=b[k]; print(f'{k:.1f}-{k+.1:.1f} {v[0]:5d} {100*v[1]/v[0]:5.1f}% {v[2]:12,.0f}')
# outcome side
oc=collections.Counter((p.get('outcome') or '?') for p in cl); print('\noutcomes',oc.most_common(8))
# trades
side=collections.Counter(t['side'] for t in tr); print('trade sides',side)
usd=[t['size']*t['price'] for t in tr]; print('trade $ median',st.median(usd),'mean',st.mean(usd),'p90',sorted(usd)[int(.9*len(usd))],'max',max(usd))
ts=[t['timestamp'] for t in tr]; print('first',dt.datetime.utcfromtimestamp(min(ts)),'last',dt.datetime.utcfromtimestamp(max(ts)))
days=collections.Counter(dt.datetime.utcfromtimestamp(t).date() for t in ts); print('active days',len(days),'trades/day median',st.median(days.values()))
hr=collections.Counter(dt.datetime.utcfromtimestamp(t).hour for t in ts); print('UTC hour',sorted(hr.items()))
tc=collections.Counter(cat(t['title']) for t in tr); print('trades by cat',tc.most_common())
tv=collections.defaultdict(float)
for t in tr: tv[cat(t['title'])]+=t['size']*t['price']
print('volume by cat',{k:round(v) for k,v in tv.items()})
# holding: per condition first/last trade
g=collections.defaultdict(list)
for t in tr: g[t['condition_id']].append(t['timestamp'])
spans=[(max(v)-min(v))/3600 for v in g.values()]; print('per-market trade span hrs median',st.median(spans),'p75',sorted(spans)[int(.75*len(spans))])
fills=[len(v) for v in g.values()]; print('fills per market median',st.median(fills),'max',max(fills),'markets',len(g))
# sells vs redeem
print('SELL share of trade $', sum(t['size']*t['price'] for t in tr if t['side']=='SELL')/sum(usd))
