import {clsx,type ClassValue} from 'clsx';
import {twMerge} from 'tailwind-merge';
export function cn(...inputs:ClassValue[]){return twMerge(clsx(inputs))}
export async function api<T=any>(path:string,options:RequestInit={}):Promise<T>{
 const response=await fetch('/api'+path,{...options,headers:{'X-Factory-Client':'local',...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...options.headers}});
 if(!response.ok){const error=await response.json().catch(()=>({detail:response.statusText}));throw new Error(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail));}
 return response.json();
}
export const post=(path:string,body:unknown={})=>api(path,{method:'POST',body:JSON.stringify(body)});
export const time=(s:number)=>`${Math.floor(s/60).toString().padStart(2,'0')}:${Math.floor(s%60).toString().padStart(2,'0')}`;
export const bytes=(n:number)=>n>=1024**3?`${(n/1024**3).toFixed(1)} ГБ`:`${Math.round(n/1024**2)} МБ`;
export type Source={id:string;name:string;duration:number;width:number;height:number;status:string;kind:string;size:number;thumbnail_url:string|null;media_url:string|null;clip_count:number;rights:{status:string;license:string;origin:string};transcript?:any;clips?:Clip[];scenes?:any[];url?:string;};
export type Clip={id:string;source_id:string;title:string;start:number;end:number;score:number;provider:string;approved:number;media_url:string|null;poster_url?:string|null;stale:boolean;revision:number;render_revision:number;data:any;plan:any;qc:any;source?:Source;transcript?:any;};
export type Job={id:string;source_id:string|null;clip_id:string|null;source_name:string;clip_title:string|null;kind:string;status:string;stage:string;progress:number;error:string|null;logs:{time:number;message:string}[];checkpoints?:any;output?:{filename:string;path:string;download_url:string}|null;};

// The studio UI always runs in a browser on the same computer as the server.
export const IS_WINDOWS=typeof navigator!=='undefined'&&/Windows/.test(navigator.userAgent);
export const IS_LINUX=typeof navigator!=='undefined'&&/Linux/.test(navigator.userAgent)&&!/Android/.test(navigator.userAgent);
export const REVEAL_LABEL=IS_WINDOWS?'Показать в Проводнике':IS_LINUX?'Показать в папке':'Показать в Finder';
export const REVEALED=IS_WINDOWS?'Файл выделен в Проводнике':IS_LINUX?'Папка с файлом открыта':'Файл выделен в Finder';
