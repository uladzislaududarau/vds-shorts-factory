import {useEffect,useRef,useState} from 'react';
import {Check,ChevronDown,Globe} from 'lucide-react';
import {LANGUAGES,setLang,tr,useLang,type Lang} from '../i18n';

// Quick switch in the top bar, next to the server status.
export function LanguageMenu(){
 const [open,setOpen]=useState(false);
 const box=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(!open)return;const close=(e:MouseEvent)=>{if(!box.current?.contains(e.target as Node))setOpen(false)};document.addEventListener('mousedown',close);return()=>document.removeEventListener('mousedown',close)},[open]);
 const lang=useLang();
 const current=LANGUAGES.find(l=>l.id===lang)!;
 return <div className="lang-menu" ref={box}>
  <button className="lang-pill" onClick={()=>setOpen(!open)} aria-expanded={open} aria-haspopup="menu" title={tr("Язык интерфейса")}>
   <Globe size={14}/><span>{current.short}</span><ChevronDown size={13} className={open?'lang-chevron open':'lang-chevron'}/>
  </button>
  {open&&<div className="server-menu lang-dropdown" role="menu">
   {LANGUAGES.map(l=><button key={l.id} role="menuitemradio" aria-checked={l.id===lang} onClick={()=>{setOpen(false);setLang(l.id)}}>
    <b>{l.short}</b>{l.label}{l.id===lang&&<Check size={15} className="lang-check"/>}
   </button>)}
  </div>}
 </div>;
}

// Settings → Language.
export function LanguageSettings(){
 const lang=useLang();
 const choose=(id:Lang)=>setLang(id);
 return <div className="settings-row"><div><h2>{tr("Язык интерфейса")}</h2><p>{tr("Меняет язык меню, кнопок и сообщений. Видео, субтитры и тексты клипов не переводятся. Быстрое переключение — справа вверху.")}</p></div>
  <div className="panel settings-form lang-options">{LANGUAGES.map(l=><button key={l.id} className={'lang-option'+(l.id===lang?' chosen':'')} aria-pressed={l.id===lang} onClick={()=>choose(l.id)}>
   <b>{l.short}</b><span>{l.label}</span>{l.id===lang&&<Check size={17}/>}
  </button>)}</div>
 </div>;
}
