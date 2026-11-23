/// <reference types="vite/client" />
// Interface language. Russian strings are the keys; locales/<lang>.json maps them to a translation.
// To add a language: put locales/xx.json next to en.json and add it to LANGUAGES.
// Dictionaries are loaded on demand, so each language adds nothing to the startup bundle.
import {useSyncExternalStore} from 'react';

export type Lang='ru'|'en'|'es'|'pt'|'fr'|'de'|'it'|'tr'|'zh'|'ja'|'ko'|'hi';
export const LANGUAGES:{id:Lang;label:string;short:string}[]=[
 {id:'en',label:'English',short:'EN'},
 {id:'ru',label:'Русский',short:'RU'},
 {id:'es',label:'Español',short:'ES'},
 {id:'pt',label:'Português',short:'PT'},
 {id:'fr',label:'Français',short:'FR'},
 {id:'de',label:'Deutsch',short:'DE'},
 {id:'it',label:'Italiano',short:'IT'},
 {id:'tr',label:'Türkçe',short:'TR'},
 {id:'zh',label:'简体中文',short:'ZH'},
 {id:'ja',label:'日本語',short:'JA'},
 {id:'ko',label:'한국어',short:'KO'},
 {id:'hi',label:'हिन्दी',short:'HI'},
];
const LOADERS=import.meta.glob<Record<string,string>>('./locales/*.json',{import:'default'});
const loaded=new Map<Lang,Record<string,string>>();
const STORAGE='factory-lang';
const supported=(id:string|null):id is Lang=>!!id&&LANGUAGES.some(l=>l.id===id);

function detect():Lang{
 try{const saved=localStorage.getItem(STORAGE);if(supported(saved))return saved}catch{}
 const browser=typeof navigator!=='undefined'?navigator.languages||[navigator.language]:[];
 for(const tag of browser){
  const base=tag.toLowerCase().split('-')[0];
  if(['uk','be','kk'].includes(base))return 'ru';
  if(supported(base))return base;
 }
 return 'en';
}
let current:Lang=detect();
let dict:Record<string,string>|null=null;
const listeners=new Set<()=>void>();

async function load(lang:Lang){
 if(lang==='ru')return null;
 if(!loaded.has(lang))loaded.set(lang,await LOADERS[`./locales/${lang}.json`]());
 return loaded.get(lang)!;
}
// Called once before the first render.
export async function initLang(){
 try{dict=await load(current)}catch{current='ru';dict=null}
 document.documentElement.lang=current;
}

export const getLang=()=>current;
// Switches in place: every component using useLang() re-renders with the new texts, no page reload.
export async function setLang(lang:Lang){
 if(lang===current)return;
 const next=await load(lang);
 current=lang;dict=next;
 try{localStorage.setItem(STORAGE,lang)}catch{}
 document.documentElement.lang=lang;
 listeners.forEach(listener=>listener());
}
export function useLang():Lang{
 return useSyncExternalStore(listener=>{listeners.add(listener);return()=>{listeners.delete(listener)}},getLang);
}

const fill=(s:string,args?:unknown[])=>args?s.replace(/\{(\d+)\}/g,(_,i)=>String(args[+i]??'')):s;
export function tr(text:string,args?:unknown[]):string{return fill(dict?.[text]??text,args)}

// Server messages are Russian. Exact matches are looked up; messages with values use the {n} templates.
const CYR=/[А-Яа-яЁё]/;
// Only templates with enough fixed words: «{0} из {1}» would otherwise rewrite ordinary sentences.
const PATTERNS=new Map<Lang,{re:RegExp;names:number[];target:string}[]>();
const buildPatterns=(dict:Record<string,string>)=>Object.keys(dict).filter(k=>/\{\d\}/.test(k)&&(k.replace(/\{\d\}/g,'').match(/[А-Яа-яЁё]/g)||[]).length>=6).map(k=>{
 const names:number[]=[];
 const source=k.split(/(\{\d\})/).map(part=>{const m=part.match(/^\{(\d)\}$/);if(m){names.push(+m[1]);return '([\\s\\S]+?)'}return part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}).join('');
 return {re:new RegExp('^'+source+'$'),names,target:dict[k]};
});
const patterns=()=>{if(!dict)return [];if(!PATTERNS.has(current))PATTERNS.set(current,buildPatterns(dict));return PATTERNS.get(current)!};
export function translateServer(message:string):string{
 if(!dict||!message||!CYR.test(message))return message;
 const exact=dict[message.trim()];
 if(exact)return exact;
 for(const p of patterns()){
  const m=message.match(p.re);
  if(m){const args:string[]=[];p.names.forEach((n,i)=>{args[n]=translateServer(m[i+1])});return fill(p.target,args)}
 }
 return message;
}
// Translates known server texts inside an API response (labels, statuses, errors, logs).
// User content — titles, speech, file names, AI texts — is never touched.
const CONTENT=new Set(['text','word','words','title','titles','name','summary','description','keywords','hashtags','tags','transcript','segments','quote','prompt','filename','path','url','source_name','clip_title','title_alternatives','caption']);
export function translateResponse<T>(value:T):T{
 if(!dict)return value;
 const walk=(v:any,key=''):any=>CONTENT.has(key)?v:typeof v==='string'?(v.length<600&&CYR.test(v)?translateServer(v):v):Array.isArray(v)?v.map(x=>walk(x)):v&&typeof v==='object'?Object.fromEntries(Object.entries(v).map(([k,x])=>[k,walk(x,k)])):v;
 return walk(value);
}
