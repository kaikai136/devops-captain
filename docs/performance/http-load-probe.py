import asyncio,httpx,time,json,subprocess,pathlib,statistics
out=pathlib.Path('docs/performance');out.mkdir(exist_ok=True)
async def stage(path,c,duration):
 samples=[]; codes={}; lat=[]; stop=False
 async def monitor():
  while not stop:
   p=await asyncio.create_subprocess_exec('ssh','-o','BatchMode=yes','root@172.16.0.161','kubectl top pods -n middleware --containers; kubectl top nodes',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
   stdout,_=await p.communicate();samples.append({'elapsed':round(time.perf_counter()-start,2),'top':stdout.decode()})
   await asyncio.sleep(4)
 async with httpx.AsyncClient(trust_env=False,timeout=10,limits=httpx.Limits(max_connections=c,max_keepalive_connections=c)) as client:
  start=time.perf_counter();deadline=start+duration
  async def worker():
   while time.perf_counter()<deadline:
    t=time.perf_counter()
    try:
     r=await client.get('http://172.16.0.161:30000'+path); code=str(r.status_code)
    except Exception as e:code=type(e).__name__
    codes[code]=codes.get(code,0)+1;lat.append((time.perf_counter()-t)*1000)
    if sum(v for k,v in codes.items() if k!='200')>20: return
  m=asyncio.create_task(monitor());await asyncio.gather(*(worker() for _ in range(c)));elapsed=time.perf_counter()-start;stop=True;await m
 lat.sort();percentile=lambda q:round(lat[int((len(lat)-1)*q)],2)
 result=dict(path=path,concurrency=c,duration_s=round(elapsed,2),requests=len(lat),codes=codes,rps=round(len(lat)/elapsed,2),p50_ms=percentile(.5),p95_ms=percentile(.95),p99_ms=percentile(.99),max_ms=round(max(lat),2),samples=samples)
 print(json.dumps({k:v for k,v in result.items() if k!='samples'}),flush=True)
 return result
async def main():
 results=[]
 for path,c in [('/',50),('/api/health/',50),('/api/auth/slider-challenge/',10),('/api/auth/slider-challenge/',50)]:
  r=await stage(path,c,20);results.append(r)
  out.joinpath('2026-10-23-load-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
  if any(k!='200' for k in r['codes']): print('Stopping higher stages after errors',flush=True);break
  await asyncio.sleep(5)
asyncio.run(main())
