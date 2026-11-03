import json,sys,collections,statistics as st,datetime as dt
D=sys.argv[1]; L=lambda n: json.load(open(f'{D}/{n}.json'))
cl=L('positions_closed'); op=L('positions_open'); tr=L('trades'); ac=L('activity')
# both sides per condition
sides=collections.defaultdict(lambda: collections.defaultdict(lambda:[0.0,0.0]))
for t in tr:
    s=sides[t['condition_id']][t['outcome_index']]; s[0]+=t['size']; s[1]+=t['size']*t['price']
both=[c for c,v in sides.items() if len(v)==2]
print('markets traded',len(sides),'both sides bought',len(both))
sumavg=[]; 
for c in both:
    v=sides[c]; a=[v[i][1]/v[i][0] for i in v]; sumavg.append(sum(a))
print('sum of avg prices (both-sided) median',st.median(sumavg),'share <1:',sum(x<1 for x in sumavg)/len(sumavg))
# merges & redeems
m=[a for a in ac if a['type']=='MERGE']; r=[a for a in ac if a['type']=='REDEEM']
print('merge usdc',round(sum(a['usdc_size'] for a in m)),'redeem usdc',round(sum(a['usdc_size'] for a in r)))
buy=sum(t['size']*t['price'] for t in tr); print('total buy usdc',round(buy))
for k in ['MAKER_REBATE','TAKER_REBATE','REWARD','YIELD']:
    print(k, round(sum(a['usdc_size'] for a in ac if a['type']==k),1))
# timing within both-sided markets: is second side bought later (hedge/exit) or simultaneously?
first=collections.defaultdict(dict)
for t in sorted(tr,key=lambda x:x['timestamp']):
    first[t['condition_id']].setdefault(t['outcome_index'],t['timestamp'])
gaps=[abs(first[c][0]-first[c][1])/3600 for c in both]
print('hrs between first buy of each side median',st.median(gaps),'share within 1h',sum(g<1 for g in gaps)/len(gaps))
# other titles
def iscrypto(t): t=t.lower(); return any(k in t for k in ['bitcoin','ethereum','solana','xrp','btc','eth','doge','crypto'])
oth=collections.Counter(p['title'] for p in cl if not iscrypto(p['title']))
print('\nnon-crypto sample', [k[:60] for k,_ in oth.most_common(25)])
# market wording types
kinds=collections.Counter()
for p in cl:
    t=p['title'].lower()
    k='dip to' if 'dip to' in t else 'reach' if 'reach' in t else 'hit' if ' hit ' in t else 'up or down' if 'up or down' in t else 'above/below' if ('above' in t or 'below' in t) else 'other'
    kinds[k]+=1
print('\nmarket wording',kinds)
asset=collections.Counter()
for t in tr:
    x=t['title'].lower(); a='BTC' if 'bitcoin' in x or 'btc' in x else 'ETH' if 'ethereum' in x else 'SOL' if 'solana' in x else 'XRP' if 'xrp' in x else 'oil' if 'crude' in x or 'oil' in x else 'gold/silver' if 'gold' in x or 'silver' in x else 'other'
    asset[a]+=t['size']*t['price']
print('volume by asset',{k:round(v) for k,v in asset.most_common()})
# open positions
print('\nOPEN',len(op),'value',round(sum(p['current_value'] for p in op)),'cost',round(sum(p['total_cost_usdc'] for p in op)),'unreal',round(sum(p['unrealized_pnl'] for p in op)))
for p in sorted(op,key=lambda p:-p['current_value'])[:10]: print(f"  {p['current_value']:9,.0f} avg {p['avg_price']:.3f} now {p['current_price']:.3f} {p['title'][:60]} [{p['outcome']}]")
# pnl curve monthly
pts=L('user_pnl')['points']; print('\npnl points',len(pts))
mo={}
for q in pts: mo[dt.datetime.fromtimestamp(q['timestamp'],dt.UTC).strftime('%Y-%m-%d')]=q.get('position_pnl') or q['realized_pnl']
ks=sorted(mo); 
for k in ks[::7]+[ks[-1]]: print(k, round(mo[k]))
# eth 2250 detail
e=[t for t in tr if 'dip to $2,250 by December 31' in t['title']]
print('\nETH2250 fills',len(e),'first',dt.datetime.fromtimestamp(min(t['timestamp'] for t in e),dt.UTC),'last',dt.datetime.fromtimestamp(max(t['timestamp'] for t in e),dt.UTC), 'by outcome',collections.Counter(t['outcome'] for t in e), 'usd',round(sum(t['size']*t['price'] for t in e)))
# closed pos hold time
h=[(p['last_event_at']-p['first_entry_at'])/86400 for p in cl if p.get('last_event_at') and p.get('first_entry_at')]
if h: print('closed hold days median',st.median(h),'p75',sorted(h)[int(.75*len(h))])
print('example closed', {k:cl[5][k] for k in ['first_entry_at','last_event_at','end_date']})
