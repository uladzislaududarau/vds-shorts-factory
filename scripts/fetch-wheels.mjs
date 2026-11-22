// Recovery installer helper. Only artifacts matching official PyPI lock SHA-256
// are accepted; no installer or arbitrary script from a mirror is executed.
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import path from 'node:path';
const manifest=JSON.parse(await fs.readFile('.tools/wheels.json','utf8'));
const directory='.tools/wheels';await fs.mkdir(directory,{recursive:true});
const core=new Set('annotated-doc annotated-types anyio certifi click fastapi h11 httpcore httpx idna iniconfig packaging pillow pluggy pydantic pydantic-core pygments pytest python-multipart sniffio starlette typing-extensions typing-inspection uvicorn'.split(' '));
const inferenceOnly=manifest.filter(w=>!core.has(w.name)&&!['torch','networkx','sympy','mpmath','jinja2','markupsafe'].includes(w.name));
const selected=(process.argv.includes('--core')?manifest.filter(w=>core.has(w.name)):process.argv.includes('--inference')?inferenceOnly:manifest).sort((a,b)=>a.size-b.size);
let pending=[];
const handles=new Map(),done=new Map();
let finished=0;
for(const wheel of selected){
 const dest=path.join(directory,wheel.filename);
 try{const b=await fs.readFile(dest);if(crypto.createHash('sha256').update(b).digest('hex')===wheel.sha256){finished++;continue}}catch{}
 let existing=false;
 try{existing=(await fs.stat(dest+'.partial')).size===wheel.size}catch{}
 const handle=await fs.open(dest+'.partial',existing?'r+':'w');await handle.truncate(wheel.size);handles.set(wheel.name,handle);
 const chunk=262144;
 const parts=Math.ceil(wheel.size/chunk);let remaining=0;
 for(let i=0;i<parts;i++){
  const start=i*chunk,end=Math.min(wheel.size-1,(i+1)*chunk-1);
  if(existing){const b=Buffer.alloc(end-start+1);await handle.read(b,0,b.length,start);if(b.some(byte=>byte!==0))continue;}
  pending.push({wheel,start,end});remaining++;
 }
 done.set(wheel.name,remaining);
 if(!remaining){await handle.close();const b=await fs.readFile(dest+'.partial');if(crypto.createHash('sha256').update(b).digest('hex')!==wheel.sha256){await fs.unlink(dest+'.partial');throw Error('Partial artifact failed hash; run again: '+wheel.name)}await fs.rename(dest+'.partial',dest);finished++;}
}
let cursor=0,totalBytes=0;const began=Date.now();
const progress=setInterval(()=>console.log(`Verified ${finished}/${selected.length}; received ${(totalBytes/1048576).toFixed(1)} MiB; ${(Date.now()-began)/1000|0}s`),30000);
async function task(){
 while(cursor<pending.length){
  const {wheel,start,end}=pending[cursor++];
  const mirrors=['https://mirrors.aliyun.com/pypi','https://pypi.tuna.tsinghua.edu.cn','https://mirrors.cloud.tencent.com/pypi','https://pypi.mirrors.ustc.edu.cn'];
  const mirrorIndex=(start/262144|0)%mirrors.length;
  let bytes;
  for(let attempt=0;attempt<5;attempt++){
   try{
    const url=wheel.url.replace('https://files.pythonhosted.org',mirrors[(mirrorIndex+attempt)%mirrors.length]);
    const response=await fetch(attempt<4?url:wheel.url,{headers:{Range:`bytes=${start}-${end}`},signal:AbortSignal.timeout(90000)});
    if(response.status!==206&&!(response.status===200&&start===0&&end===wheel.size-1))throw Error(`HTTP ${response.status}: ${wheel.name}`);
    bytes=Buffer.from(await response.arrayBuffer());
    if(bytes.length!==end-start+1)throw Error(`Incomplete range: ${wheel.name}`);
    break;
   }catch(error){if(attempt===4)throw Error(`${wheel.name} bytes ${start}-${end}: ${error}`);}
  }
  await handles.get(wheel.name).write(bytes,0,bytes.length,start);totalBytes+=bytes.length;
  const remaining=done.get(wheel.name)-1;done.set(wheel.name,remaining);
  if(remaining===0){
   await handles.get(wheel.name).close();
   const dest=path.join(directory,wheel.filename),buffer=await fs.readFile(dest+'.partial');
   if(crypto.createHash('sha256').update(buffer).digest('hex')!==wheel.sha256)throw Error(`SHA-256 mismatch: ${wheel.name}`);
   await fs.rename(dest+'.partial',dest);finished++;
   console.log(`OK ${wheel.name} ${wheel.version}`);
  }
 }
}
try{await Promise.all(Array.from({length:32},task));console.log('All selected wheels verified.')}finally{clearInterval(progress)}
