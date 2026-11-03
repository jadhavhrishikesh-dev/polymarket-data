import json,collections,re
D='data/0xa19cbababc312f9df185e49d7004c249ed1ade6b'
tr=json.load(open(D+'/trades.json'))
pat=collections.Counter(); ex={}
for t in tr:
  s=re.sub(r'\$[\d,\.]+k?','$K',t['title']); s=re.sub(r'\d+','N',s)
  s=re.sub(r'(January|February|March|April|May|June|July|August|September|October|November|December)','MON',s)
  s=re.sub(r'(Bitcoin|Ethereum|Solana|XRP)','COIN',s)
  pat[s]+=1; ex.setdefault(s,t['title'])
for k,v in pat.most_common(40): print(v,'|',k,'|',ex[k])
