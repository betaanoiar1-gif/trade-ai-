from __future__ import annotations
import json, os, time
from dataclasses import dataclass
from typing import Any
import httpx
BASE=(os.getenv('KIOSAPI_BASE_URL') or 'https://router.kiosapi.com/v1/').rstrip('/')
KEY=os.getenv('KIOS_API_KEY') or os.getenv('KIOSAPI_API_KEY') or os.getenv('AI_API_KEY','')
MODELS=[x.strip() for x in os.getenv('KIOSAPI_TRADING_BENCHMARK_MODELS','qwen3.8-27b,deepseek-v4-flash-0731,deepseek-v4-flash,glm-5.3-flash,qwen3.8-flash,nemotron-3-super-120b-a12b').split(',') if x.strip()]
INTERVAL=float(os.getenv('KIOSAPI_BENCHMARK_REQUEST_INTERVAL_S','10'))
TIMEOUT=float(os.getenv('KIOSAPI_BENCHMARK_TIMEOUT_S','12'))
TOKENS=int(os.getenv('KIOSAPI_TRADING_BENCHMARK_MAX_TOKENS','1200'))
@dataclass(frozen=True)
class Case:
 name:str; expected:str; snapshot:str; evidence:tuple[str,...]
SCREEN=Case('breakout','LONG','BTCUSDT perpetual. Current 104200. 1D bullish HH/HL. 4H closed above 103500; volume 2.1x average. 1H EMA20>EMA50>EMA200, RSI 64, ADX 29. 15M retest holds 103500-103800. Funding +0.008%, OI +7%. No liquidation data. Invalidation: confirmed 1H close below 103500.',('103500','volume','EMA','RSI','funding','OI'))
DEEP=[Case('bearish','SHORT','ETHUSDT perpetual. Current 3520. 1D bearish. 4H closed below 3600 and retest failed. 1H EMA20<EMA50<EMA200, RSI 34, ADX 31. Selling volume 1.8x. Funding -0.012%, OI +5%. Invalidation: 1H close above 3600.',('3600','volume','EMA','RSI','funding','OI')),Case('range','NO_TRADE','SOLUSDT perpetual. Current 148.2. 4H inside 142-154 range with failed breaks. 1H EMA20/50 flat, ADX 14, RSI 51. Volume 0.8x. Funding +0.001%, OI flat. No clean sweep or BOS. No validated directional edge.',('range','ADX','RSI','volume','OI')),Case('missing_data','NO_TRADE','SOLUSDT perpetual. Current 150. 4H mildly bullish, but funding, open interest and liquidation data are unavailable. Volume 1.1x and RSI 58. Resistance has not broken. Do not invent unavailable data.',('funding','open interest','liquidation','volume','RSI'))]
SYSTEM='You are a deterministic crypto paper-trading decision engine. Use only supplied facts. Never invent data. Return exactly one compact JSON object and nothing else.'
PROMPT='Return ONLY JSON with keys decision,confidence,entry_low,entry_high,stop,take_profit_1,take_profit_2,thesis,invalidation,warnings. Decisions: LONG, SHORT, HOLD, WAIT, NO_TRADE. Numeric prices or null. Confidence 0..1. LONG/SHORT needs valid stop and TP1 with >=1:1 reward/risk. NO_TRADE uses null prices. CASE:\n{snapshot}'
def extract(s:str)->dict[str,Any]|None:
 d=0; st=None; q=False; esc=False
 for i,c in enumerate(s):
  if q:
   if esc: esc=False
   elif c=='\\': esc=True
   elif c=='"': q=False
  elif c=='"': q=True
  elif c=='{':
   if d==0: st=i
   d+=1
  elif c=='}' and d:
   d-=1
   if d==0 and st is not None:
    try:
     x=json.loads(s[st:i+1]); return x if isinstance(x,dict) else None
    except json.JSONDecodeError: st=None
 return None
def parse(data):
 ch=data.get('choices');
 if not isinstance(ch,list) or not ch: raise ValueError('missing choices')
 c=ch[0]
 if c.get('finish_reason')=='length': raise ValueError('finish_reason=length')
 m=c.get('message');
 if not isinstance(m,dict): raise ValueError('missing message')
 for k in ('content','text','output_text'):
  v=m.get(k)
  if isinstance(v,str) and v.strip():
   x=extract(v)
   if x is not None:return x
 raise ValueError('no final JSON')
def num(v):
 try:return None if isinstance(v,bool) else float(v)
 except:return None
def score(o,case):
 req={'decision','confidence','entry_low','entry_high','stop','take_profit_1','take_profit_2','thesis','invalidation','warnings'}
 if req-set(o):return 0
 p=20+(35 if o.get('decision')==case.expected else 0)
 c=num(o.get('confidence')); p+=10 if c is not None and 0<=c<=1 else 0
 p+=5 if isinstance(o.get('thesis'),str) and o['thesis'].strip() else 0
 p+=5 if isinstance(o.get('invalidation'),str) and o['invalidation'].strip() else 0
 text=f"{o.get('thesis','')} {o.get('invalidation','')}".lower();p+=min(15,sum(t.lower() in text for t in case.evidence)*3)
 if case.expected=='NO_TRADE': p+=10 if all(o.get(k) is None for k in ('entry_low','entry_high','stop','take_profit_1','take_profit_2')) else 0
 else:
  v=[num(o.get(k)) for k in ('entry_low','entry_high','stop','take_profit_1')]
  if all(x is not None and x>0 for x in v):
   lo,hi,st,tp=v;e=(lo+hi)/2;r=abs(e-st);rw=tp-e if case.expected=='LONG' else e-tp
   p+=15 if lo<=hi and r>0 and rw>=r and ((case.expected=='LONG' and st<e<tp) or (case.expected=='SHORT' and tp<e<st)) else 0
 return min(p,100)
def call(client,model,case):
 t=time.perf_counter()
 try:
  r=client.post(f'{BASE}/chat/completions',headers={'Authorization':f'Bearer {KEY}'},json={'model':model,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':PROMPT.format(snapshot=case.snapshot)}],'temperature':0,'max_tokens':TOKENS,'response_format':{'type':'json_object'}})
  if r.status_code>=400:raise ValueError(f'HTTP {r.status_code}')
  p=score(parse(r.json()),case);return {'ok':p>=70,'score':p,'latency_s':round(time.perf_counter()-t,2)}
 except Exception as e:return {'ok':False,'score':0,'latency_s':round(time.perf_counter()-t,2),'error':type(e).__name__}
def main():
 if not KEY:raise SystemExit('KIOS_API_KEY missing')
 if not 2<=len(MODELS)<=8:raise SystemExit('use 2-8 models')
 if INTERVAL<8:raise SystemExit('interval must be >=8s')
 print(f'MODELS={json.dumps(MODELS)}');print('STAGE1_CASES=1');print('STAGE2_CASES=3');print(f'INTERVAL={INTERVAL}');print(f'TIMEOUT={TIMEOUT}');print(f'MAX_TOKENS={TOKENS}')
 with httpx.Client(timeout=TIMEOUT) as c:
  screened=[]
  for i,m in enumerate(MODELS):
   x=call(c,m,SCREEN);x['model']=m;screened.append(x);print('SCREEN='+json.dumps(x))
   if i<len(MODELS)-1:time.sleep(INTERVAL)
  finalists=[x['model'] for x in sorted(screened,key=lambda x:(-x['score'],x['latency_s']))[:2]];print('FINALISTS='+json.dumps(finalists))
  summaries=[]
  for m in finalists:
   xs=[next(x for x in screened if x['model']==m)]
   for j,case in enumerate(DEEP):
    x=call(c,m,case);xs.append(x);print('DEEP='+json.dumps({'model':m,'case':case.name,**x}));time.sleep(INTERVAL)
   summaries.append({'model':m,'avg_score':round(sum(x['score'] for x in xs)/4,2),'valid_cases':sum(x['ok'] for x in xs),'cases':4,'avg_latency_s':round(sum(x['latency_s'] for x in xs)/4,2)})
  ranked=sorted(summaries,key=lambda x:(-x['valid_cases'],-x['avg_score'],x['avg_latency_s']));print('RANKING='+json.dumps(ranked));q=[x for x in ranked if x['valid_cases']==4];print('BEST_TRADING_MODEL='+(q[0]['model'] if q else 'INCONCLUSIVE'));print('NOTE=Fast staged benchmark; not a profitability test')
if __name__=='__main__':main()
