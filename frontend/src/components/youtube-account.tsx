import {tr} from '../i18n';
import {useEffect,useRef,useState} from 'react';
import {ExternalLink,Loader2,LogIn,RefreshCw,ShieldCheck,Unplug,Upload} from 'lucide-react';
import {Button} from './ui/button';
import {api,post} from '../lib';

export function YouTubeAccount({onChange}:{onChange?:(session:any)=>void}){
 const [session,setSession]=useState<any>(null),[busy,setBusy]=useState(''),[error,setError]=useState(''),[note,setNote]=useState('');
 const upload=useRef<HTMLInputElement>(null);
 const update=(value:any)=>{setSession(value);onChange?.(value)};
 useEffect(()=>{api('/youtube/session').then(update).catch(e=>setError(e.message))},[]);
 const action=async(name:string,fn:()=>Promise<any>)=>{
  setBusy(name);setError('');setNote('');
  try{
   const result=await fn();
   if(name==='login')setNote(result.note);
   else{update(result);setNote(name==='disconnect'?tr("Сессия студии отключена."):result.note)}
  }catch(e){setError(e instanceof Error?e.message:String(e))}
  finally{setBusy('')}
 };
 const connectFile=(file?:File)=>{
  if(!file)return;
  const form=new FormData();form.append('file',file);form.append('consent','true');
  action('file',()=>api('/youtube/cookies',{method:'POST',body:form}));
  if(upload.current)upload.current.value='';
 };
 return <section className="youtube-account" aria-label={tr("Аккаунт YouTube")}>
  <div className="spread"><h3>{tr("Аккаунт YouTube")}</h3><span className="badge">{session?.connected?tr("Сессия подключена"):tr("Без аккаунта")}</span></div>
  <p>{tr("Войдите в YouTube в отдельном окне Chrome, затем подключите сессию. Пароль вводится на странице Google. Студия сохраняет только cookies YouTube на этом компьютере.")}</p>
  <div className="button-row">
   <Button size="sm" disabled={!!busy||session?.browser_available===false} onClick={()=>action('login',()=>post('/youtube/login'))}>
    {busy==='login'?<Loader2 size={14} className="spin"/>:<LogIn size={14}/>}{tr("Войти в YouTube")}<ExternalLink size={12}/>
   </Button>
   <Button size="sm" disabled={!!busy} onClick={()=>action('connect',()=>post('/youtube/connect',{consent:true}))}>
    {busy==='connect'?<Loader2 size={14} className="spin"/>:session?.connected?<RefreshCw size={14}/>:<ShieldCheck size={14}/>}
    {session?.connected?tr("Обновить сессию"):tr("Я вошёл — подключить")}
   </Button>
  </div>
  <details><summary>{tr("Подключить через cookies.txt")}</summary><p>{tr("Экспортируйте cookies только для youtube.com в формате Netscape. При выборе файла студия сохранит его локально для авторизованных загрузок.")}</p><Button size="sm" disabled={!!busy} onClick={()=>upload.current?.click()}><Upload size={14}/>{tr("Выбрать cookies.txt")}</Button><input ref={upload} hidden type="file" accept=".txt" onChange={e=>connectFile(e.target.files?.[0])}/></details>
  {session?.connected&&<div className="spread session-footer"><small>{tr("Обновлено:")} {new Date(session.updated_at*1000).toLocaleString('ru-RU')}</small><Button size="sm" variant="ghost" disabled={!!busy} onClick={()=>action('disconnect',()=>api('/youtube/session',{method:'DELETE'}))}><Unplug size={13}/>{tr("Отключить от студии")}</Button></div>}
  {busy==='connect'&&<p role="status">{tr("Читаю сессию… macOS может запросить доступ к Chrome Safe Storage. Разрешите его, чтобы подключить вход.")}</p>}
  {note&&<p role="status">{note}</p>}
  {error&&<p className="inline-error" role="alert">{error}</p>}
 </section>
}
