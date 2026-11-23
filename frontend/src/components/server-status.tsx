import {tr} from '../i18n';
import {useEffect,useRef,useState} from 'react';
import {Loader2,Play,Power,RotateCcw} from 'lucide-react';
import {Button} from './ui/button';
import {post,IS_WINDOWS,IS_LINUX} from '../lib';

// A browser tab cannot start programs. «Запустить» opens shortsfactory://start, which macOS hands to
// «VDS Shorts Factory.app» (scripts/build_app.py); the app starts the launchd server.
export type ServerState='online'|'offline'|'starting'|'restarting'|'stopping';
export type Server={state:ServerState;managed:boolean;slow:boolean;start:()=>void;restart:()=>Promise<void>;stop:()=>Promise<void>};

const WAIT_MS=45000;

export function useServer(onRecovered:()=>void):Server{
 const [state,setState]=useState<ServerState>('online'),[managed,setManaged]=useState(false),[slow,setSlow]=useState(false);
 const current=useRef<ServerState>('online'),since=useRef(0),sawDown=useRef(false),recovered=useRef(onRecovered);
 recovered.current=onRecovered;
 const set=(next:ServerState)=>{current.current=next;setState(next)};
 const begin=(next:ServerState)=>{since.current=Date.now();sawDown.current=false;setSlow(false);set(next)};
 useEffect(()=>{
  let alive=true,timer=0;
  const check=async()=>{
   let up=false;
   try{const r=await fetch('/api/health',{cache:'no-store',signal:AbortSignal.timeout(2500)});if(r.ok){up=true;setManaged(!!(await r.json()).managed)}}catch{}
   if(!alive)return;
   const now=current.current,waited=Date.now()-since.current;
   if(!up)sawDown.current=true;
   if(now==='restarting'||now==='stopping'){
    // The old process answers for a moment after the request: wait until it has really gone.
    if(up&&(sawDown.current||waited>WAIT_MS))set('online'),recovered.current();
    else if(!up&&now==='stopping')set('offline');
    else if(!up&&waited>WAIT_MS)set('offline');
   }else if(now==='starting'){
    if(up){set('online');recovered.current()}else if(waited>12000)setSlow(true);
   }else if(up&&now==='offline'){set('online');recovered.current()}
   else if(!up&&now==='online')set('offline');
   timer=window.setTimeout(check,['starting','restarting','stopping'].includes(current.current)?1000:3000);
  };
  check();
  return()=>{alive=false;clearTimeout(timer)};
 },[]);
 return {state,managed,slow,
  start:()=>{begin('starting');window.location.href='shortsfactory://start'},
  restart:async()=>{await post('/system/restart');begin('restarting')},
  stop:async()=>{await post('/system/stop');begin('stopping')}};
}

const LABEL=():Record<ServerState,string>=>({online:tr("Статус: активно"),offline:tr("Статус: остановлен"),starting:tr("Статус: запуск…"),restarting:tr("Статус: перезапуск…"),stopping:tr("Статус: остановка…")});

export function ServerBadge({server,activeJobs}:{server:Server;activeJobs:number}){
 const [open,setOpen]=useState(false),[error,setError]=useState('');
 const box=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(!open)return;const close=(e:MouseEvent)=>{if(!box.current?.contains(e.target as Node))setOpen(false)};document.addEventListener('mousedown',close);return()=>document.removeEventListener('mousedown',close)},[open]);
 const busy=['starting','restarting','stopping'].includes(server.state);
 const confirmJobs=(action:string)=>!activeJobs||confirm(tr("Сейчас в работе задач: {0}. Они встанут на паузу — продолжить их можно в «Очереди». {1}?",[activeJobs,action]));
 const run=async(fn:()=>Promise<void>)=>{setError('');try{await fn();setOpen(false)}catch(e:any){setError(e.message)}};
 return <div className="server-status" ref={box}>
  <button className={'server-pill '+server.state} onClick={()=>server.state==='offline'?server.start():setOpen(!open)} aria-expanded={open} title={LABEL()[server.state]}>
   {busy?<Loader2 size={13} className="spin"/>:<i className="server-dot"/>}<span>{server.state==='offline'?tr("Статус: остановлен · Запустить"):LABEL()[server.state]}</span>
  </button>
  {open&&server.state==='online'&&<div className="server-menu" role="menu">
   <p>{tr("Сервер студии работает на этом компьютере: 127.0.0.1:8765")}</p>
   {server.managed?<>
    <button role="menuitem" onClick={()=>confirmJobs(tr("Перезапустить"))&&run(server.restart)}><RotateCcw size={15}/>{tr("Перезапустить")}</button>
    <button role="menuitem" onClick={()=>confirmJobs(tr("Остановить"))&&run(server.stop)}><Power size={15}/>{tr("Остановить")}</button>
   </>:<p className="muted">{tr("Сервер запущен вручную из терминала — управляйте им там.")}</p>}
   {error&&<p className="inline-error">{error}</p>}
  </div>}
 </div>;
}

export function ServerDownBanner({server}:{server:Server}){
 if(server.state==='online'||server.state==='restarting')return null;
 return <div className="server-down" role="alert">
  <div><strong>{server.state==='starting'?tr("Запускаю сервер…"):server.state==='stopping'?tr("Сервер останавливается…"):tr("Сервер VDS Shorts Factory не запущен")}</strong>
   <p>{server.state==='starting'&&server.slow
     ?tr("Запуск занимает дольше обычного. Если браузер спросил разрешение открыть «VDS Shorts Factory» — разрешите. Или откройте VDS Shorts Factory ")+(IS_WINDOWS?tr("из меню «Пуск» или ярлыком на рабочем столе."):IS_LINUX?tr("из меню приложений."):tr("из Launchpad или папки «Программы»."))
     :tr("Проекты и файлы сохранены. Нажмите «Запустить» — откроется приложение VDS Shorts Factory и запустит сервер. Браузер может один раз спросить разрешение.")}</p></div>
  {server.state==='offline'&&<Button variant="default" onClick={server.start}><Play size={15}/>{tr("Запустить")}</Button>}
  {server.state!=='offline'&&<Loader2 size={20} className="spin"/>}
 </div>;
}
