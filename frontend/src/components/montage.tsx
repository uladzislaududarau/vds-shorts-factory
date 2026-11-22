import React,{useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {ArrowLeft,ArrowDown,ArrowUp,AudioLines,Check,CheckCircle2,Clapperboard,Download,Film,FolderOpen,Library,Loader2,Music,Pause,Play,Plus,Scissors,Subtitles,Trash2,Upload,Volume2,VolumeX,X,Monitor,Smartphone,AlertCircle,Sparkles} from 'lucide-react';
import {Button} from './ui/button';
import {api,post,time,REVEAL_LABEL,type Clip,type Job,type Source} from '../lib';

type ClipItem={id:string;media_kind:'upload'|'source'|'render';media_id:string;start:number;end:number;volume:number;muted:boolean;captions:boolean};
type AudioItem={id:string;kind:'file'|'music';label?:string;media_id:string;at:number;offset:number;duration:number;volume:number;fade_in:number;fade_out:number};
type Style={enabled:boolean;template:string;color:string;accent:string;size:number;uppercase:boolean;words:number;outline:number;position:number};
type Word={word:string;start:number;end:number};
type Plan={format:'9:16'|'16:9';fit:'blur'|'fill'|'fit';fps:30|60;quality:number;normalize:boolean;clips:ClipItem[];audio:AudioItem[];subtitles:Style;language:string;caption_edits:Record<string,Word[]>};
type MediaInfo={title:string;duration:number;has_audio?:boolean;media_url:string|null;thumbnail_url?:string|null;error?:string};
type Project={id:string;title:string;revision:number;duration:number;clip_count:number;format:string;video_url:string|null;stale:boolean;thumbnail_url:string|null;updated_at:number;plan?:Plan;media?:Record<string,MediaInfo>;words?:Record<string,Word[]|null>;jobs?:Record<string,{id:string;stage:string;progress:number;status:string}|null>;last_render?:{id:string;status:string;error:string|null;qc:any}|null;music_variants?:Variant[]};
type Variant={id:string;label:string;duration:number;media_url:string;created_at:number;job_id:string};
type Template={id:string;label:string;hint:string;defaults:Partial<Style>};

const uid=()=>'i'+Date.now().toString(36)+Math.random().toString(36).slice(2,8);
const seconds=(n:number)=>`${n.toFixed(1).replace('.',',')} с`;
const clamp=(v:number,lo:number,hi:number)=>Math.min(hi,Math.max(lo,v));
const STORE='montage-project';
const RIGHTS='montage-rights-confirmed';
const read=(key:string)=>{try{return localStorage.getItem(key)}catch{return null}};
const write=(key:string,value:string|null)=>{try{value===null?localStorage.removeItem(key):localStorage.setItem(key,value)}catch{}};
const FONT:Record<string,{family:string;weight:number}>={bold:{family:'"Arial Black", Arial, sans-serif',weight:900},box:{family:'"Avenir Next", Avenir, "Segoe UI", sans-serif',weight:700},single:{family:'Impact, "Arial Black", sans-serif',weight:400},clean:{family:'"Helvetica Neue", "Segoe UI", Helvetica, Arial, sans-serif',weight:500},neon:{family:'"Helvetica Neue", "Segoe UI", Helvetica, Arial, sans-serif',weight:900}};
const ACCENT_LABEL:Record<string,string>={bold:'Цвет активного слова',box:'Цвет плашки',single:'Второй цвет',clean:'Цвет акцента',neon:'Цвет свечения'};

function Field({label,children,hint}:{label:string;children:React.ReactNode;hint?:string}){return <label className="field"><span>{label}</span>{children}{hint&&<small>{hint}</small>}</label>}
function Toggle({label,checked,onChange,description}:{label:string;checked:boolean;onChange:(v:boolean)=>void;description?:string}){return <label className="toggle-row"><div><span>{label}</span>{description&&<small>{description}</small>}</div><input type="checkbox" role="switch" checked={checked} onChange={e=>onChange(e.target.checked)}/></label>}

export function MontagePage({clips,sources,jobs,toast,onQueue}:{clips:Clip[];sources:Source[];jobs:Job[];toast:(t:string,e?:boolean)=>void;onQueue:()=>void}){
 const [projectId,setProjectId]=useState<string|null>(()=>read(STORE));
 const open=(id:string|null)=>{setProjectId(id);write(STORE,id)};
 if(projectId)return <MontageEditor key={projectId} projectId={projectId} onClose={()=>open(null)} clips={clips} sources={sources} jobs={jobs} toast={toast} onQueue={onQueue}/>;
 return <ProjectList onOpen={open} toast={toast}/>;
}

function ProjectList({onOpen,toast}:{onOpen:(id:string)=>void;toast:(t:string,e?:boolean)=>void}){
 const [projects,setProjects]=useState<Project[]|null>(null);
 const load=()=>api('/montage/projects').then(setProjects).catch(e=>toast(e.message,true));
 useEffect(()=>{load()},[]);
 const create=async()=>{try{const p=await post('/montage/projects',{title:`Монтаж ${new Date().toLocaleDateString('ru-RU')}`});onOpen(p.id)}catch(e:any){toast(e.message,true)}};
 const remove=async(p:Project)=>{if(!confirm(`Удалить монтаж «${p.title}»? Готовые MP4 останутся на диске.`))return;try{await api('/montage/projects/'+p.id,{method:'DELETE'});load()}catch(e:any){toast(e.message,true)}};
 return <>
  <div className="page-title"><div><h1>Монтаж</h1><p>Склейте несколько коротких роликов в одно видео: обрезка, музыка, субтитры.</p></div><Button variant="default" onClick={create}><Plus size={16}/>Новый монтаж</Button></div>
  {!projects?<div className="skeleton block"/>:projects.length?<div className="montage-projects">{projects.map(p=><article className="montage-project" key={p.id}>
   <button className="montage-project-cover" onClick={()=>onOpen(p.id)} aria-label={`Открыть ${p.title}`}>{p.thumbnail_url?<img src={p.thumbnail_url} alt=""/>:<Film size={34} strokeWidth={1}/>}<span className="cover-time">{time(p.duration)}</span></button>
   <div className="montage-project-body"><button className="card-title" onClick={()=>onOpen(p.id)}>{p.title}</button><small>{p.clip_count} клипов · {p.format==='16:9'?'Full HD 16:9':'Вертикальное 9:16'}</small>
    <div className="spread"><span className={'badge '+(p.video_url&&!p.stale?'positive':'')}>{p.video_url?(p.stale?'Есть изменения':'Видео готово'):'Черновик'}</span><Button size="icon" variant="ghost" aria-label="Удалить монтаж" onClick={()=>remove(p)}><Trash2 size={15}/></Button></div></div>
  </article>)}</div>:<div className="empty montage-empty"><Clapperboard size={30} strokeWidth={1}/><h3>Соберите первое видео из нескольких клипов</h3>
   <ol className="montage-steps"><li><b>1</b>Добавьте 3–10 клипов с компьютера или из библиотеки</li><li><b>2</b>Обрежьте лишнее и расставьте по порядку</li><li><b>3</b>Добавьте музыку и субтитры — и создайте MP4</li></ol>
   <Button variant="default" onClick={create}><Plus size={16}/>Новый монтаж</Button></div>}
 </>;
}

function MontageEditor({projectId,onClose,clips,sources,jobs,toast,onQueue}:{projectId:string;onClose:()=>void;clips:Clip[];sources:Source[];jobs:Job[];toast:(t:string,e?:boolean)=>void;onQueue:()=>void}){
 const [project,setProject]=useState<Project|null>(null),[plan,setPlan]=useState<Plan|null>(null),[title,setTitle]=useState(''),[media,setMedia]=useState<Record<string,MediaInfo>>({});
 const [saveState,setSaveState]=useState<'saved'|'dirty'|'saving'|'error'>('saved'),[saveError,setSaveError]=useState('');
 const [tab,setTab]=useState('clips'),[selected,setSelected]=useState<string|null>(null),[selectedAudio,setSelectedAudio]=useState<string|null>(null);
 const [templates,setTemplates]=useState<Template[]>([]),[pickerOpen,setPickerOpen]=useState(false),[showResult,setShowResult]=useState(false),[busy,setBusy]=useState(false);
 const [playhead,setPlayhead]=useState(0);
 const player=useRef<PlayerHandle>(null);
 const version=useRef(0);

 const apply=(p:Project,replacePlan:boolean)=>{setProject(p);setMedia(m=>({...m,...(p.media||{})}));if(replacePlan&&p.plan){setPlan(p.plan);setTitle(p.title)}};
 // The AI music job writes its track into the server plan; everything else is owned by the editor.
 const withServerMusic=(local:Plan,server?:Plan)=>({...local,audio:[...local.audio.filter(a=>a.kind!=='music'),...(server?.audio||[]).filter(a=>a.kind==='music')]});
 const load=useCallback(async(mode:'replace'|'keep'|'merge'='keep')=>{try{const p:Project=await api('/montage/projects/'+projectId);apply(p,mode==='replace');if(mode==='merge'&&p.plan)setPlan(local=>local&&withServerMusic(local,p.plan))}catch(e:any){toast(e.message,true);if(String(e.message).includes('не найден'))onClose()}},[projectId]);
 useEffect(()=>{load('replace');api('/montage/templates').then(setTemplates).catch(()=>{})},[projectId]);

 const put=(current:Plan,revision:number)=>api('/montage/projects/'+projectId,{method:'PUT',body:JSON.stringify({title:title.trim()||'Без названия',plan:current,revision})});
 const saveResolving=async(current:Plan):Promise<{p:Project;plan:Plan;merged:boolean}>=>{
  try{return {p:await put(current,project!.revision),plan:current,merged:false}}
  catch(e:any){
   if(e.message!=='revision-conflict')throw e;
   const server:Project=await api('/montage/projects/'+projectId);
   const merged=withServerMusic(current,server.plan);
   return {p:await put(merged,server.revision),plan:merged,merged:true};
  }
 };
 // Autosave: the local plan is the source of truth; the server answer only refreshes media/words/status.
 useEffect(()=>{
  if(!plan||!project||saveState!=='dirty')return;
  const mine=++version.current;
  const id=setTimeout(async()=>{
   setSaveState('saving');
   try{const r=await saveResolving(plan);if(mine===version.current){apply(r.p,false);if(r.merged)setPlan(r.plan);setSaveState('saved');setSaveError('')}}
   catch(e:any){if(mine===version.current){setSaveState('error');setSaveError(e.message)}}
  },700);
  return()=>clearTimeout(id);
 },[plan,title,saveState]);
 const update=(fn:(p:Plan)=>Plan)=>{setPlan(p=>p&&fn(p));setSaveState('dirty')};
 const flush=async()=>{if(saveState==='saved'||!plan)return true;try{version.current++;const r=await saveResolving(plan);apply(r.p,false);if(r.merged)setPlan(r.plan);setSaveState('saved');return true}catch(e:any){setSaveState('error');setSaveError(e.message);toast(e.message,true);return false}};

 // Background jobs (render / speech / music) are tracked through the global queue poll.
 const trackedJob=(kind:string)=>{const id=project?.jobs?.[kind]?.id;return id?jobs.find(j=>j.id===id):undefined};
 const renderJob=trackedJob('montage'),wordsJob=trackedJob('montage_words'),musicJob=trackedJob('montage_music');
 const watched=useRef<Record<string,string>>({});
 // project.jobs lists only jobs that were active at the last load, so a finished one is reported exactly once.
 useEffect(()=>{for(const job of [renderJob,wordsJob,musicJob]){
  if(!job||!['Completed','Failed','Cancelled'].includes(job.status)||watched.current[job.id]===job.status)continue;
  watched.current[job.id]=job.status;
  load(job.kind==='montage_music'?'merge':'keep');
  if(job.status==='Completed'&&job.kind==='montage'){toast('Видео готово');setShowResult(true)}
  if(job.status==='Completed'&&job.kind==='montage_music'){toast('Музыка готова и добавлена на всю длину монтажа');setShowResult(false)}
  if(job.status==='Failed')toast(job.error||'Задача завершилась с ошибкой',true);
 }},[jobs]);
 const isActive=(job?:Job)=>!!job&&['Queued','Running','Paused'].includes(job.status);
 const activeRender=isActive(renderJob),activeWords=isActive(wordsJob);

 if(!plan||!project)return <><div className="page-title"><h1>Монтаж</h1></div><div className="skeleton block"/></>;
 const total=plan.clips.reduce((n,c)=>n+c.end-c.start,0);
 const starts:number[]=[];plan.clips.reduce((n,c)=>{starts.push(n);return n+c.end-c.start},0);
 const selectedClip=plan.clips.find(c=>c.id===selected)||null;

 const addClips=(items:{kind:ClipItem['media_kind'];id:string;start:number;end:number;info:MediaInfo;captions:boolean}[])=>{
  const created=items.map(i=>({id:uid(),media_kind:i.kind,media_id:i.id,start:i.start,end:i.end,volume:1,muted:false,captions:i.captions} as ClipItem));
  setMedia(m=>({...m,...Object.fromEntries(created.map((c,n)=>[c.id,items[n].info]))}));
  update(p=>({...p,clips:[...p.clips,...created]}));
  if(created.length)setSelected(created[created.length-1].id);
 };
 const changeClip=(id:string,patch:Partial<ClipItem>)=>update(p=>({...p,clips:p.clips.map(c=>c.id===id?{...c,...patch}:c)}));
 const moveClip=(id:string,delta:number)=>update(p=>{const list=[...p.clips];const i=list.findIndex(c=>c.id===id);const j=i+delta;if(i<0||j<0||j>=list.length)return p;[list[i],list[j]]=[list[j],list[i]];return {...p,clips:list}});
 const reorder=(from:number,to:number)=>update(p=>{const list=[...p.clips];const [item]=list.splice(from,1);list.splice(to,0,item);return {...p,clips:list}});
 const removeClip=(id:string)=>update(p=>{const edits={...p.caption_edits};delete edits[id];return {...p,clips:p.clips.filter(c=>c.id!==id),caption_edits:edits}});
 const changeAudio=(id:string,patch:Partial<AudioItem>)=>update(p=>({...p,audio:p.audio.map(a=>a.id===id?{...a,...patch}:a)}));
 const style=(patch:Partial<Style>)=>update(p=>({...p,subtitles:{...p.subtitles,...patch}}));

 const createVideo=async()=>{
  if(!plan.clips.length){toast('Добавьте хотя бы один клип',true);return}
  setBusy(true);
  try{if(!(await flush()))return;await post(`/montage/projects/${projectId}/render`);await load('keep');toast('Видео поставлено в очередь. Можно продолжать работу.')}
  catch(e:any){toast(e.message,true)}finally{setBusy(false)}
 };
 const recognize=async()=>{
  setBusy(true);
  try{if(!(await flush()))return;const r=await post(`/montage/projects/${projectId}/recognize`);await load('keep');toast(r.ready?'Текст уже распознан':'Распознаю речь на этом компьютере…')}
  catch(e:any){toast(e.message,true)}finally{setBusy(false)}
 };
 const generateMusic=async(body:{style:string;tempo:string;notes:string;consent:true})=>{
  setBusy(true);
  try{if(!(await flush()))return false;await post(`/montage/projects/${projectId}/music`,body);await load('keep');toast('ElevenLabs сочиняет музыку. Можно продолжать монтаж.');return true}
  catch(e:any){toast(e.message,true);return false}finally{setBusy(false)}
 };
 const applyVariant=(v:Variant)=>{
  const current=plan.audio.find(a=>a.kind==='music');
  const length=+Math.max(.5,Math.min(v.duration,total||v.duration)).toFixed(2);
  const item:AudioItem={id:uid(),kind:'music',label:v.label,media_id:v.id,at:0,offset:0,duration:length,volume:current?.volume??.35,fade_in:0,fade_out:+Math.min(2,length/4).toFixed(2)};
  setMedia(m=>({...m,[item.id]:{title:`AI-музыка · ${v.label}`,duration:v.duration,media_url:v.media_url}}));
  update(p=>({...p,audio:[...p.audio.filter(a=>a.kind!=='music'),item]}));
  setSelectedAudio(item.id);
 };
 const reveal=async()=>{if(!project.last_render)return;try{await post(`/jobs/${project.last_render.id}/reveal`)}catch(e:any){toast(e.message,true)}};

 const wordsFor=(c:ClipItem)=>plan.caption_edits[c.id]||(project.words?.[c.id]??null);
 const needWords=plan.subtitles.enabled?plan.clips.filter(c=>c.captions&&!plan.caption_edits[c.id]&&project.words?.[c.id]==null):[];

 return <>
  <div className="montage-header">
   <Button size="icon" variant="ghost" aria-label="Все монтажи" onClick={async()=>{await flush();onClose()}}><ArrowLeft size={18}/></Button>
   <input className="montage-title" aria-label="Название монтажа" value={title} maxLength={120} onChange={e=>{setTitle(e.target.value);setSaveState('dirty')}}/>
   <span className={'save-state '+saveState} title={saveError}>{saveState==='saving'?<><Loader2 size={13} className="spin"/>Сохраняю…</>:saveState==='dirty'?'Изменено':saveState==='error'?<><AlertCircle size={13}/>Не сохранено</>:<><Check size={13}/>Сохранено</>}</span>
   <div className="montage-header-actions">
    <span className="muted">{plan.clips.length} клипов · {time(total)}</span>
    <Button variant="default" disabled={busy||!!activeRender||!plan.clips.length} onClick={createVideo}>{activeRender?<Loader2 size={15} className="spin"/>:<Clapperboard size={15}/>}{activeRender?'Создаётся…':'Создать видео'}</Button>
   </div>
  </div>
  {saveState==='error'&&<div className="error-banner"><AlertCircle size={16}/><span>{saveError}</span></div>}

  <div className="montage-grid">
   <div className="montage-preview">
    <Player ref={player} plan={plan} media={media} starts={starts} total={total} wordsFor={wordsFor} result={showResult&&project.video_url?project.video_url+'?v='+project.revision+(project.last_render?.id||''):null} onTime={setPlayhead}/>
    <RenderStatus project={project} job={renderJob} showResult={showResult} setShowResult={setShowResult} onReveal={reveal} onQueue={onQueue}/>
   </div>

   <div className="edit-panel montage-panel">
    <div className="editor-tabs">{[['clips','1 · Клипы',Scissors],['audio','2 · Звук',AudioLines],['subtitles','3 · Субтитры',Subtitles],['format','4 · Формат',Monitor]].map(([id,label,Icon]:any)=><button key={id} className={tab===id?'selected':''} onClick={()=>setTab(id)}><Icon size={16}/>{label}</button>)}</div>
    <div className="edit-content">
     {tab==='clips'&&<ClipsPanel plan={plan} media={media} selected={selectedClip} onSelect={id=>{setSelected(id);const i=plan.clips.findIndex(c=>c.id===id);if(i>=0)player.current?.seek(starts[i])}} onAdd={addClips} onChange={changeClip} onMove={moveClip} onRemove={removeClip} onPicker={()=>setPickerOpen(true)} toast={toast} playhead={playhead} starts={starts}/>}
     {tab==='audio'&&<AudioPanel music={<MusicGenerator total={total} job={musicJob} variants={project.music_variants||[]} current={plan.audio.find(a=>a.kind==='music')} busy={busy} onGenerate={generateMusic} onUse={applyVariant}/>} plan={plan} media={media} setMedia={setMedia} total={total} playhead={playhead} selected={selectedAudio} onSelect={setSelectedAudio} onAdd={item=>{update(p=>({...p,audio:[...p.audio,item]}));setSelectedAudio(item.id)}} onChange={changeAudio} onRemove={id=>update(p=>({...p,audio:p.audio.filter(a=>a.id!==id)}))} onNormalize={v=>update(p=>({...p,normalize:v}))} toast={toast}/>}
     {tab==='subtitles'&&<SubtitlesPanel plan={plan} media={media} templates={templates} style={style} needWords={needWords} wordsFor={wordsFor} recognizing={!!activeWords} wordsJob={wordsJob} busy={busy} onRecognize={recognize} onLanguage={v=>update(p=>({...p,language:v}))} onEdit={(id,words)=>update(p=>{const edits={...p.caption_edits};if(words)edits[id]=words;else delete edits[id];return {...p,caption_edits:edits}})}/>}
     {tab==='format'&&<FormatPanel plan={plan} onChange={patch=>update(p=>({...p,...patch}))}/>}
    </div>
   </div>
  </div>

  <Timeline plan={plan} media={media} total={total} starts={starts} playhead={playhead} selected={selected} selectedAudio={selectedAudio}
   onSeek={t=>player.current?.seek(t)} onSelectClip={id=>{setSelected(id);setTab('clips')}} onSelectAudio={id=>{setSelectedAudio(id);setTab('audio')}} onReorder={reorder}/>

  {pickerOpen&&<LibraryPicker clips={clips} sources={sources} onClose={()=>setPickerOpen(false)} onAdd={items=>{addClips(items);toast(`Добавлено клипов: ${items.length}`)}}/>}
 </>;
}

/* ------------------------------------------------------------ player */

type PlayerHandle={seek:(t:number)=>void};
const Player=React.forwardRef<PlayerHandle,{plan:Plan;media:Record<string,MediaInfo>;starts:number[];total:number;wordsFor:(c:ClipItem)=>Word[]|null;result:string|null;onTime:(t:number)=>void}>(function Player({plan,media,starts,total,wordsFor,result,onTime},ref){
 const video=useRef<HTMLVideoElement>(null),frame=useRef<HTMLDivElement>(null);
 const audios=useRef<Record<string,HTMLAudioElement|null>>({});
 const [index,setIndex]=useState(0),[playing,setPlaying]=useState(false),[now,setNow]=useState(0),[frameWidth,setFrameWidth]=useState(300);
 const pending=useRef<number|null>(null);
 const clip=plan.clips[index];
 const info=clip?media[clip.id]:undefined;
 useEffect(()=>{if(index>=plan.clips.length)setIndex(0)},[plan.clips.length]);
 useEffect(()=>{const el=frame.current;if(!el)return;const ro=new ResizeObserver(()=>setFrameWidth(el.clientWidth));ro.observe(el);return()=>ro.disconnect()},[result]);
 const report=(t:number)=>{setNow(t);onTime(t)};
 const seek=(t:number)=>{
  t=clamp(t,0,Math.max(0,total-.01));
  let i=starts.findIndex((s,n)=>t>=s&&t<s+plan.clips[n].end-plan.clips[n].start);if(i<0)i=Math.max(0,plan.clips.length-1);
  const c=plan.clips[i];if(!c)return;
  const local=c.start+(t-starts[i]);
  if(i!==index){pending.current=local;setIndex(i)}else if(video.current)video.current.currentTime=local;
  report(t);syncAudio(t,false);
 };
 React.useImperativeHandle(ref,()=>({seek}));
 const syncAudio=(t:number,play:boolean)=>{
  for(const item of plan.audio){
   const el=audios.current[item.id];if(!el)continue;
   const inside=t>=item.at&&t<item.at+item.duration;
   el.volume=clamp(item.volume,0,1);
   if(inside&&play){const want=item.offset+(t-item.at);if(Math.abs(el.currentTime-want)>.3)el.currentTime=want;if(el.paused)el.play().catch(()=>{})}
   else if(!el.paused)el.pause();
   if(!play&&inside)el.currentTime=item.offset+(t-item.at);
  }
 };
 const onLoaded=()=>{const el=video.current;if(!el||!clip)return;el.currentTime=pending.current??clip.start;pending.current=null;if(playing)el.play().catch(()=>{})};
 const onTick=()=>{
  const el=video.current;if(!el||!clip)return;
  el.volume=clip.muted?0:clamp(clip.volume,0,1);
  if(el.currentTime<clip.start-.3&&!el.seeking){el.currentTime=clip.start;return}
  const t=starts[index]+clamp(el.currentTime-clip.start,0,clip.end-clip.start);
  report(t);syncAudio(t,playing);
  if(el.currentTime>=clip.end-.04){
   if(index+1<plan.clips.length){pending.current=plan.clips[index+1].start;setIndex(index+1)}
   else{el.pause();setPlaying(false);syncAudio(t,false)}
  }
 };
 const toggle=()=>{
  const el=video.current;if(!el||!clip)return;
  if(playing){el.pause();setPlaying(false);syncAudio(now,false);return}
  if(now>=total-.05)seek(0);
  setPlaying(true);el.play().catch(()=>{});
 };
 useEffect(()=>{if(!playing)return;const id=setInterval(onTick,120);return()=>clearInterval(id)},[playing,index,plan]);
 const aspect=plan.format==='9:16'?'9 / 16':'16 / 9';
 const fitClass=plan.fit==='fill'?'cover':'contain';

 // Live caption approximation (the MP4 uses the exact server renderer).
 const caption=useMemo(()=>{
  if(!plan.subtitles.enabled||!clip||!clip.captions)return null;
  const words=wordsFor(clip);if(!words)return null;
  const local=clip.start+(now-(starts[index]||0));
  const per=plan.subtitles.template==='single'?1:plan.subtitles.words;
  const inside=words.filter(w=>w.start>=clip.start-.03&&w.end<=clip.end+.03);
  const groups:Word[][]=[];let cur:Word[]=[];
  for(const w of inside){if(cur.length&&(cur.length>=per||w.start-cur[cur.length-1].end>.6)){groups.push(cur);cur=[]}cur.push(w);if(/[.!?…]$/.test(w.word)){groups.push(cur);cur=[]}}
  if(cur.length)groups.push(cur);
  const g=groups.findIndex(group=>local>=group[0].start&&local<=group[group.length-1].end);
  if(g<0)return null;
  return {words:groups[g],active:groups[g].findIndex(w=>local>=w.start&&local<w.end),group:g};
 },[now,plan.subtitles,clip,index]);
 const s=plan.subtitles;const scale=(plan.format==='9:16'?frameWidth:frameWidth*9/16)/1080;
 const font=FONT[s.template]||FONT.bold;

 if(result)return <div className="montage-player-wrap"><div className="montage-frame result" style={{aspectRatio:aspect}}><video key={result} src={result} controls autoPlay playsInline/></div><p className="preview-note">Готовый MP4 — ровно то, что будет опубликовано.</p></div>;
 return <div className="montage-player-wrap">
  <div ref={frame} className={'montage-frame '+(plan.fit==='blur'?'with-backdrop':'')} style={{aspectRatio:aspect}} onClick={toggle}>
   {plan.fit==='blur'&&info?.thumbnail_url&&<img className="montage-blur" src={info.thumbnail_url} alt=""/>}
   {clip&&info?.media_url?<video ref={video} key={clip.id+info.media_url} src={info.media_url} preload="auto" playsInline style={{objectFit:fitClass}} onLoadedMetadata={onLoaded} onTimeUpdate={()=>{if(!playing)return;onTick()}}/>:<div className="montage-frame-empty"><Film size={34} strokeWidth={1}/><span>{plan.clips.length?'Клип недоступен':'Добавьте клипы — здесь появится просмотр'}</span></div>}
   {caption&&<div className={'montage-caption t-'+s.template} style={{top:`${s.position*100}%`,fontFamily:font.family,fontWeight:font.weight,fontSize:Math.max(8,s.size*scale),color:s.color,textTransform:s.uppercase?'uppercase':'none',WebkitTextStroke:s.outline?`${Math.max(.5,s.outline*scale)}px #000`:undefined,['--accent' as any]:s.accent,paintOrder:'stroke fill'}}>
    {caption.words.map((w,n)=><span key={n} className={n===caption.active?'active':''} style={s.template==='single'?{color:caption.group%2?s.accent:s.color}:undefined}>{w.word}</span>)}
   </div>}
   {!playing&&clip&&<span className="montage-play-badge"><Play size={22} fill="currentColor"/></span>}
  </div>
  <div className="montage-controls">
   <Button size="icon" aria-label={playing?'Пауза':'Смотреть'} onClick={toggle} disabled={!clip}>{playing?<Pause size={16}/>:<Play size={16}/>}</Button>
   <input type="range" aria-label="Позиция" min={0} max={Math.max(total,.1)} step={.05} value={Math.min(now,total)} onChange={e=>seek(+e.target.value)}/>
   <span className="montage-time">{time(now)} / {time(total)}</span>
  </div>
  <p className="preview-note">Быстрый просмотр в браузере: стыки и субтитры приблизительны. Точный результат — в готовом MP4.</p>
  {plan.audio.map(a=>media[a.id]?.media_url&&<audio key={a.id} ref={el=>{audios.current[a.id]=el}} src={media[a.id].media_url!} preload="auto"/>)}
 </div>;
});

function RenderStatus({project,job,showResult,setShowResult,onReveal,onQueue}:{project:Project;job?:Job;showResult:boolean;setShowResult:(v:boolean)=>void;onReveal:()=>void;onQueue:()=>void}){
 if(job&&['Queued','Running','Paused'].includes(job.status))return <div className="montage-result"><div className="spread"><strong><Loader2 size={14} className="spin"/> {job.status==='Queued'?'В очереди':job.status==='Paused'?'На паузе':job.stage==='Rendering'?'Склеиваю видео':job.stage==='Quality check'?'Проверяю файл':job.stage}</strong><button className="text-link" onClick={onQueue}>Очередь</button></div><div className="progress"><i style={{width:Math.max(4,job.progress)+'%'}}/></div></div>;
 const failed=project.last_render?.status==='Failed';
 if(failed&&!project.video_url)return <div className="montage-result error"><AlertCircle size={15}/><span>{project.last_render?.error||'Видео не создано'}</span></div>;
 if(!project.video_url)return null;
 return <div className="montage-result">
  <div className="spread"><strong><CheckCircle2 size={15}/> Видео готово</strong>{project.stale&&<small>После создания были изменения — создайте заново</small>}</div>
  <div className="button-row">
   <Button size="sm" onClick={()=>setShowResult(!showResult)}>{showResult?<><Scissors size={13}/>Вернуться к монтажу</>:<><Play size={13}/>Смотреть MP4</>}</Button>
   <a className="button primary small" href={project.video_url+'?download=true'} download><Download size={14}/>Скачать MP4</a>
   <Button size="sm" variant="ghost" onClick={onReveal}><FolderOpen size={14}/>{REVEAL_LABEL}</Button>
  </div>
  {failed&&<p className="inline-error">Последняя попытка: {project.last_render?.error}</p>}
 </div>;
}

/* ------------------------------------------------------------ uploads */

function useUpload(toast:(t:string,e?:boolean)=>void){
 const [confirmed,setConfirmed]=useState(read(RIGHTS)==='1'),[uploading,setUploading]=useState(false);
 const confirm=(v:boolean)=>{setConfirmed(v);write(RIGHTS,v?'1':null)};
 const upload=async(files:File[])=>{
  if(!files.length)return [];
  setUploading(true);
  try{
   const form=new FormData();files.forEach(f=>form.append('files',f));form.append('confirmed',confirmed?'true':'false');
   const result:any[]=await api('/montage/media',{method:'POST',body:form});
   result.filter(r=>r.error).forEach(r=>toast(`${r.name}: ${r.error}`,true));
   return result.filter(r=>!r.error);
  }catch(e:any){toast(e.message,true);return []}finally{setUploading(false)}
 };
 return {confirmed,confirm,uploading,upload};
}

function RightsCheck({confirmed,onChange}:{confirmed:boolean;onChange:(v:boolean)=>void}){
 if(confirmed)return null;
 return <label className="check-row montage-rights"><input type="checkbox" checked={confirmed} onChange={e=>onChange(e.target.checked)}/>Подтверждаю, что у меня есть права на загружаемые видео и звук</label>;
}

/* ------------------------------------------------------------ clips */

function ClipsPanel({plan,media,selected,onSelect,onAdd,onChange,onMove,onRemove,onPicker,toast,playhead,starts}:{plan:Plan;media:Record<string,MediaInfo>;selected:ClipItem|null;onSelect:(id:string)=>void;onAdd:(items:any[])=>void;onChange:(id:string,p:Partial<ClipItem>)=>void;onMove:(id:string,d:number)=>void;onRemove:(id:string)=>void;onPicker:()=>void;toast:(t:string,e?:boolean)=>void;playhead:number;starts:number[]}){
 const input=useRef<HTMLInputElement>(null);
 const {confirmed,confirm,uploading,upload}=useUpload(toast);
 const pick=async(files:File[])=>{const done=await upload(files);onAdd(done.map(m=>({kind:'upload',id:m.id,start:0,end:+m.duration.toFixed(3),info:{title:m.name,duration:m.duration,has_audio:m.has_audio,media_url:m.media_url,thumbnail_url:m.thumbnail_url},captions:true})))};
 return <>
  <h2>Клипы</h2>
  <p className="muted">Добавьте ролики — они склеятся по порядку сверху вниз. Порядок можно менять стрелками или перетаскиванием на ленте внизу.</p>
  <RightsCheck confirmed={confirmed} onChange={confirm}/>
  <div className="montage-add">
   <button className="montage-add-button" disabled={!confirmed||uploading} onClick={()=>input.current?.click()}>{uploading?<Loader2 size={20} className="spin"/>:<Upload size={20}/>}<strong>{uploading?'Загружаю…':'С компьютера'}</strong><small>MP4, MOV, MKV, WebM</small></button>
   <button className="montage-add-button" onClick={onPicker}><Library size={20}/><strong>Из библиотеки</strong><small>Найденные моменты и готовые клипы</small></button>
   <input ref={input} type="file" multiple accept=".mp4,.mov,.mkv,.webm" hidden onChange={e=>{pick(Array.from(e.target.files||[]));e.target.value=''}}/>
  </div>
  <div className="montage-clip-list">{plan.clips.map((c,n)=>{const info=media[c.id];const open=selected?.id===c.id;return <div key={c.id} className={'montage-clip'+(open?' open':'')}>
   <div className="montage-clip-row" onClick={()=>onSelect(c.id)}>
    <span className="montage-index">{n+1}</span>
    <div className="montage-thumb">{info?.thumbnail_url?<img src={info.thumbnail_url} alt=""/>:<Film size={16}/>}</div>
    <div className="montage-clip-name"><strong>{info?.title||'Клип'}</strong><small>{info?.error?<span className="inline-error">{info.error}</span>:<>{seconds(c.end-c.start)}{c.muted?' · без звука':''}{c.media_kind==='render'?' · готовый MP4':c.media_kind==='source'?' · из библиотеки':''}</>}</small></div>
    <div className="montage-clip-actions" onClick={e=>e.stopPropagation()}>
     <Button size="icon" variant="ghost" aria-label="Выше" disabled={n===0} onClick={()=>onMove(c.id,-1)}><ArrowUp size={14}/></Button>
     <Button size="icon" variant="ghost" aria-label="Ниже" disabled={n===plan.clips.length-1} onClick={()=>onMove(c.id,1)}><ArrowDown size={14}/></Button>
     <Button size="icon" variant="ghost" aria-label="Удалить клип" onClick={()=>onRemove(c.id)}><Trash2 size={14}/></Button>
    </div>
   </div>
   {open&&info&&!info.error&&<ClipEditor clip={c} info={info} onChange={p=>onChange(c.id,p)} cursor={playhead>=starts[n]&&playhead<=starts[n]+c.end-c.start?c.start+playhead-starts[n]:null}/>}
  </div>})}</div>
  {!plan.clips.length&&<div className="empty-row">Клипов пока нет. Начните с 3–7 коротких роликов по 10–15 секунд.</div>}
 </>;
}

function ClipEditor({clip,info,onChange,cursor}:{clip:ClipItem;info:MediaInfo;onChange:(p:Partial<ClipItem>)=>void;cursor:number|null}){
 const max=info.duration||clip.end;
 const setStart=(v:number)=>onChange({start:+clamp(v,0,clip.end-.2).toFixed(2)});
 const setEnd=(v:number)=>onChange({end:+clamp(v,clip.start+.2,max).toFixed(2)});
 return <div className="montage-clip-editor">
  <div className="trim-head"><strong>Обрезка</strong><span>Длина {seconds(clip.end-clip.start)} из {seconds(max)}</span></div>
  <div className="trim-bar" aria-hidden="true"><i style={{left:`${clip.start/max*100}%`,width:`${(clip.end-clip.start)/max*100}%`}}/>{cursor!=null&&<b style={{left:`${cursor/max*100}%`}}/>}</div>
  <label className="range-label">Начало<input type="range" min={0} max={max} step={.05} value={clip.start} onChange={e=>setStart(+e.target.value)}/><input className="mini-number" type="number" step={.1} min={0} max={clip.end-.2} value={clip.start} onChange={e=>setStart(+e.target.value)}/></label>
  <label className="range-label">Конец<input type="range" min={0} max={max} step={.05} value={clip.end} onChange={e=>setEnd(+e.target.value)}/><input className="mini-number" type="number" step={.1} min={clip.start+.2} max={max} value={clip.end} onChange={e=>setEnd(+e.target.value)}/></label>
  <div className="button-row">
   <Button size="sm" disabled={cursor==null} onClick={()=>cursor!=null&&setStart(cursor)}>Начать с текущего кадра</Button>
   <Button size="sm" disabled={cursor==null} onClick={()=>cursor!=null&&setEnd(cursor)}>Закончить на текущем кадре</Button>
  </div>
  <div className="trim-head"><strong>Звук клипа</strong><span>{clip.muted?'выключен':Math.round(clip.volume*100)+'%'}</span></div>
  <div className="volume-row">
   <Button size="icon" variant="ghost" aria-label={clip.muted?'Включить звук':'Выключить звук'} onClick={()=>onChange({muted:!clip.muted})}>{clip.muted?<VolumeX size={16}/>:<Volume2 size={16}/>}</Button>
   <input type="range" aria-label="Громкость клипа" min={0} max={2} step={.05} value={clip.volume} disabled={clip.muted} onChange={e=>onChange({volume:+e.target.value})}/>
  </div>
  {info.has_audio===false&&<p className="muted">В этом клипе нет звуковой дорожки.</p>}
  <Toggle label="Субтитры для этого клипа" description={clip.media_kind==='render'?'Готовый MP4 обычно уже содержит субтитры — включайте, только если их нет.':undefined} checked={clip.captions} onChange={v=>onChange({captions:v})}/>
 </div>;
}

function LibraryPicker({clips,sources,onClose,onAdd}:{clips:Clip[];sources:Source[];onClose:()=>void;onAdd:(items:any[])=>void}){
 const dialog=useRef<HTMLDialogElement>(null);
 useEffect(()=>{dialog.current?.showModal();return()=>dialog.current?.close()},[]);
 const [query,setQuery]=useState(''),[added,setAdded]=useState<string[]>([]);
 const local=new Map(sources.filter(s=>s.media_url).map(s=>[s.id,s]));
 const shown=clips.filter(c=>c.title.toLowerCase().includes(query.toLowerCase())&&(local.has(c.source_id)||c.media_url));
 const add=(c:Clip,kind:'source'|'render')=>{
  const source=local.get(c.source_id);
  if(kind==='source'&&source)onAdd([{kind,id:source.id,start:+c.start.toFixed(2),end:+c.end.toFixed(2),captions:true,info:{title:c.title,duration:source.duration,has_audio:true,media_url:source.media_url,thumbnail_url:c.poster_url}}]);
  else{const d=c.qc?.duration||c.end-c.start;onAdd([{kind:'render',id:c.id,start:0,end:+d.toFixed(2),captions:false,info:{title:c.title,duration:d,has_audio:true,media_url:c.media_url,thumbnail_url:c.poster_url}}])}
  setAdded(a=>[...a,c.id+kind]);
 };
 return <dialog ref={dialog} className="wide" onCancel={e=>{e.preventDefault();onClose()}} onClick={e=>{if(e.target===dialog.current)onClose()}}>
  <div className="modal-title"><h2>Клипы из библиотеки</h2><Button size="icon" variant="ghost" aria-label="Закрыть" onClick={onClose}><X size={20}/></Button></div>
  <div className="modal-body">
   <p className="muted"><b>Фрагмент</b> — чистое видео без субтитров, границы потом можно расширить. <b>Готовый MP4</b> — клип ровно как в библиотеке, с его кадрированием и субтитрами.</p>
   <input placeholder="Поиск по названию…" value={query} onChange={e=>setQuery(e.target.value)}/>
   <div className="picker-list">{shown.length?shown.map(c=><div className="picker-row" key={c.id}>
    <div className="montage-thumb">{c.poster_url?<img src={c.poster_url} alt=""/>:<Film size={16}/>}</div>
    <div className="montage-clip-name"><strong>{c.title}</strong><small>{seconds(c.end-c.start)}{c.media_url?' · есть готовый MP4':''}</small></div>
    <div className="button-row">
     {local.has(c.source_id)&&<Button size="sm" onClick={()=>add(c,'source')}>{added.includes(c.id+'source')?<Check size={13}/>:<Plus size={13}/>}Фрагмент</Button>}
     {c.media_url&&<Button size="sm" onClick={()=>add(c,'render')}>{added.includes(c.id+'render')?<Check size={13}/>:<Plus size={13}/>}Готовый MP4</Button>}
    </div>
   </div>):<div className="empty-row">Нет клипов с локальным видео. Скачайте исходник и выполните анализ, либо загрузите ролики с компьютера.</div>}</div>
   <div className="modal-actions"><Button variant="default" onClick={onClose}>Готово</Button></div>
  </div>
 </dialog>;
}

/* ------------------------------------------------------------ audio */

function AudioPanel({music,plan,media,setMedia,total,playhead,selected,onSelect,onAdd,onChange,onRemove,onNormalize,toast}:{music:React.ReactNode;plan:Plan;media:Record<string,MediaInfo>;setMedia:React.Dispatch<React.SetStateAction<Record<string,MediaInfo>>>;total:number;playhead:number;selected:string|null;onSelect:(id:string|null)=>void;onAdd:(a:AudioItem)=>void;onChange:(id:string,p:Partial<AudioItem>)=>void;onRemove:(id:string)=>void;onNormalize:(v:boolean)=>void;toast:(t:string,e?:boolean)=>void}){
 const input=useRef<HTMLInputElement>(null);
 const {confirmed,confirm,uploading,upload}=useUpload(toast);
 const pick=async(files:File[])=>{
  const done=await upload(files);
  for(const m of done){
   const at=+clamp(playhead,0,Math.max(0,total-.5)).toFixed(2);
   const item:AudioItem={id:uid(),kind:'file',media_id:m.id,at,offset:0,duration:+Math.max(.5,Math.min(m.duration,(total||m.duration)-at)).toFixed(2),volume:.8,fade_in:0,fade_out:1};
   setMedia(prev=>({...prev,[item.id]:{title:m.name,duration:m.duration,media_url:m.media_url}}));
   onAdd(item);
  }
 };
 return <>
  {music}
  <h3 className="montage-subhead">Свой аудиофайл</h3>
  <p className="muted">Музыка или озвучка с компьютера. Дорожка ставится в позицию курсора — её можно сдвинуть, обрезать и сделать тише.</p>
  <RightsCheck confirmed={confirmed} onChange={confirm}/>
  <div className="montage-add single">
   <button className="montage-add-button" disabled={!confirmed||uploading||!plan.clips.length} onClick={()=>input.current?.click()}>{uploading?<Loader2 size={20} className="spin"/>:<Music size={20}/>}<strong>{uploading?'Загружаю…':'Добавить аудиофайл'}</strong><small>{plan.clips.length?`MP3, WAV, M4A · начнётся с ${seconds(playhead)}`:'Сначала добавьте клипы'}</small></button>
   <input ref={input} type="file" multiple accept=".mp3,.wav,.m4a,.aac,.ogg,.flac" hidden onChange={e=>{pick(Array.from(e.target.files||[]));e.target.value=''}}/>
  </div>
  <div className="montage-clip-list">{plan.audio.map(a=>{const info=media[a.id];const open=selected===a.id;const fileLength=info?.duration||a.offset+a.duration;return <div key={a.id} className={'montage-clip'+(open?' open':'')}>
   <div className="montage-clip-row" onClick={()=>onSelect(open?null:a.id)}>
    <div className={'montage-thumb audio'+(a.kind==='music'?' ai':'')}>{a.kind==='music'?<Sparkles size={16}/>:<Music size={16}/>}</div>
    <div className="montage-clip-name"><strong>{a.kind==='music'?`AI-музыка · ${a.label||''}`:info?.title||'Аудио'}</strong><small>{info?.error?<span className="inline-error">{info.error}</span>:`с ${seconds(a.at)} · ${seconds(a.duration)} · ${Math.round(a.volume*100)}%`}</small></div>
    <div className="montage-clip-actions" onClick={e=>e.stopPropagation()}><Button size="icon" variant="ghost" aria-label="Удалить дорожку" onClick={()=>onRemove(a.id)}><Trash2 size={14}/></Button></div>
   </div>
   {open&&<div className="montage-clip-editor">
    <label className="range-label">Начинается на<input type="range" min={0} max={Math.max(total,.1)} step={.05} value={a.at} onChange={e=>onChange(a.id,{at:+e.target.value})}/><input className="mini-number" type="number" step={.1} min={0} value={a.at} onChange={e=>onChange(a.id,{at:Math.max(0,+e.target.value)})}/></label>
    <div className="button-row"><Button size="sm" onClick={()=>onChange(a.id,{at:+playhead.toFixed(2)})}>Поставить на курсор ({seconds(playhead)})</Button></div>
    <label className="range-label">Длина<input type="range" min={.5} max={Math.max(.5,fileLength-a.offset)} step={.05} value={a.duration} onChange={e=>onChange(a.id,{duration:+e.target.value})}/><input className="mini-number" type="number" step={.1} min={.5} value={a.duration} onChange={e=>onChange(a.id,{duration:Math.max(.5,+e.target.value)})}/></label>
    <label className="range-label">С какого места файла<input type="range" min={0} max={Math.max(0,fileLength-.5)} step={.05} value={a.offset} onChange={e=>onChange(a.id,{offset:+e.target.value,duration:Math.min(a.duration,fileLength-+e.target.value)})}/><input className="mini-number" type="number" step={.1} min={0} value={a.offset} onChange={e=>onChange(a.id,{offset:Math.max(0,+e.target.value)})}/></label>
    <label className="range-label">Громкость<input type="range" min={0} max={2} step={.05} value={a.volume} onChange={e=>onChange(a.id,{volume:+e.target.value})}/><span className="mini-value">{Math.round(a.volume*100)}%</span></label>
    <div className="form-grid">
     <Field label="Плавное появление, с"><input type="number" min={0} max={10} step={.5} value={a.fade_in} onChange={e=>onChange(a.id,{fade_in:clamp(+e.target.value,0,10)})}/></Field>
     <Field label="Плавное затухание, с"><input type="number" min={0} max={10} step={.5} value={a.fade_out} onChange={e=>onChange(a.id,{fade_out:clamp(+e.target.value,0,10)})}/></Field>
    </div>
   </div>}
  </div>})}</div>
  {!plan.audio.length&&<div className="empty-row">Дополнительного звука нет — в видео будет звук самих клипов.</div>}
  <Toggle label="Выровнять громкость для соцсетей" description="Итоговый звук приводится к −14 LUFS, как рекомендуют YouTube, Instagram и TikTok." checked={plan.normalize} onChange={onNormalize}/>
 </>;
}

/* ------------------------------------------------------------ subtitles */

function SubtitlesPanel({plan,media,templates,style,needWords,wordsFor,recognizing,wordsJob,busy,onRecognize,onLanguage,onEdit}:{plan:Plan;media:Record<string,MediaInfo>;templates:Template[];style:(p:Partial<Style>)=>void;needWords:ClipItem[];wordsFor:(c:ClipItem)=>Word[]|null;recognizing:boolean;wordsJob?:Job;busy:boolean;onRecognize:()=>void;onLanguage:(v:string)=>void;onEdit:(id:string,w:Word[]|null)=>void}){
 const s=plan.subtitles;
 const preview=(t:Template)=>`/api/montage/caption-preview?crop=true&format=9:16&style=${encodeURIComponent(JSON.stringify({template:t.id,...t.defaults,enabled:true}))}`;
 const custom=`/api/montage/caption-preview?crop=true&format=${encodeURIComponent(plan.format)}&style=${encodeURIComponent(JSON.stringify(s))}`;
 const captioned=plan.clips.filter(c=>c.captions);
 return <>
  <h2>Субтитры</h2>
  <Toggle label="Добавить субтитры в видео" description="Текст распознаётся из речи прямо на этом компьютере (Whisper), без отправки в интернет." checked={s.enabled} onChange={v=>style({enabled:v})}/>
  {s.enabled&&<>
   <div className="template-grid">{templates.map(t=><button key={t.id} className={'template-card'+(s.template===t.id?' chosen':'')} onClick={()=>style({...t.defaults,template:t.id})}>
    <span className="template-sample"><img src={preview(t)} alt="" loading="lazy"/></span><strong>{t.label}</strong><small>{t.hint}</small>{s.template===t.id&&<Check size={15}/>}
   </button>)}</div>
   <h3 className="montage-subhead">Настроить стиль</h3>
   <div className="template-result"><img src={custom} alt="Так будут выглядеть субтитры"/></div>
   <div className="form-grid">
    <Field label="Цвет текста"><input type="color" value={s.color} onChange={e=>style({color:e.target.value.toUpperCase()})}/></Field>
    {s.template!=='clean'&&<Field label={ACCENT_LABEL[s.template]||'Цвет акцента'}><input type="color" value={s.accent} onChange={e=>style({accent:e.target.value.toUpperCase()})}/></Field>}
   </div>
   <label className="range-label">Размер<input type="range" min={30} max={160} step={2} value={s.size} onChange={e=>style({size:+e.target.value})}/><span className="mini-value">{s.size}</span></label>
   <label className="range-label">Положение<input type="range" min={.1} max={.9} step={.01} value={s.position} onChange={e=>style({position:+e.target.value})}/><span className="mini-value">{s.position<.35?'вверху':s.position>.65?'внизу':'по центру'}</span></label>
   <label className="range-label">Обводка<input type="range" min={0} max={14} step={1} value={s.outline} onChange={e=>style({outline:+e.target.value})}/><span className="mini-value">{s.outline||'нет'}</span></label>
   {s.template!=='single'&&<label className="range-label">Слов на экране<input type="range" min={1} max={6} step={1} value={s.words} onChange={e=>style({words:+e.target.value})}/><span className="mini-value">{s.words}</span></label>}
   <Toggle label="ЗАГЛАВНЫЕ БУКВЫ" checked={s.uppercase} onChange={v=>style({uppercase:v})}/>

   <h3 className="montage-subhead">Текст субтитров</h3>
   <div className="form-grid"><Field label="Язык речи"><select value={plan.language} onChange={e=>onLanguage(e.target.value)}><option value="auto">Определить автоматически</option><option value="ru">Русский</option><option value="en">English</option></select></Field></div>
   {recognizing?<div className="montage-result"><strong><Loader2 size={14} className="spin"/> {wordsJob?.stage||'Распознаю речь…'}</strong><div className="progress"><i style={{width:Math.max(4,wordsJob?.progress||0)+'%'}}/></div></div>
    :needWords.length?<div className="notice-box"><span>Текст ещё не распознан для {needWords.length} {needWords.length===1?'клипа':'клипов'}. Распознайте сейчас, чтобы проверить и исправить слова, — или это произойдёт автоматически при создании видео.</span></div>:null}
   {!recognizing&&needWords.length>0&&<Button disabled={busy} onClick={onRecognize}><Subtitles size={15}/>Распознать речь</Button>}
   <div className="caption-clips">{captioned.map((c,n)=>{const words=wordsFor(c);const inside=(words||[]).filter(w=>w.start>=c.start-.03&&w.end<=c.end+.03);const edited=!!plan.caption_edits[c.id];return <details key={c.id} className="caption-word-editor">
    <summary>{plan.clips.indexOf(c)+1}. {media[c.id]?.title||'Клип'} <small>{words==null?'не распознан':inside.length?`${inside.length} слов${edited?' · исправлено':''}`:'речи нет'}</small></summary>
    {words!=null&&inside.length>0&&<><div className="word-edit-list">{inside.map((w,i)=><label key={i}><time>{seconds(w.start-c.start)}</time><input maxLength={120} value={w.word} onChange={e=>{const next=inside.map((x,k)=>k===i?{...x,word:e.target.value}:x).filter(x=>x.word.trim());onEdit(c.id,next.map(x=>({word:x.word,start:x.start,end:x.end})))}}/></label>)}</div>
     {edited&&<Button size="sm" onClick={()=>onEdit(c.id,null)}>Вернуть распознанный текст</Button>}</>}
   </details>})}</div>
  </>}
 </>;
}

/* ------------------------------------------------------------ format */

function FormatPanel({plan,onChange}:{plan:Plan;onChange:(p:Partial<Plan>)=>void}){
 return <>
  <h2>Формат видео</h2>
  <div className="format-cards">
   <button className={plan.format==='9:16'?'chosen':''} onClick={()=>onChange({format:'9:16'})}><Smartphone size={26} strokeWidth={1.4}/><strong>Вертикальное 9:16</strong><small>1080×1920 · Reels, Shorts, TikTok</small>{plan.format==='9:16'&&<Check size={15}/>}</button>
   <button className={plan.format==='16:9'?'chosen':''} onClick={()=>onChange({format:'16:9'})}><Monitor size={26} strokeWidth={1.4}/><strong>Горизонтальное Full HD</strong><small>1920×1080 · YouTube, презентации</small>{plan.format==='16:9'&&<Check size={15}/>}</button>
  </div>
  <h3 className="montage-subhead">Если форма клипа другая</h3>
  <div className="crop-options">{[['blur','Размытый фон','Клип целиком, по краям — его размытая копия. Подходит почти всегда.'],['fill','Заполнить кадр','Клип увеличивается и обрезается по краям, без полос.'],['fit','Целиком с полями','Клип целиком, по краям чёрные полосы.']].map(([id,label,desc])=><button key={id} className={plan.fit===id?'chosen':''} onClick={()=>onChange({fit:id as Plan['fit']})}><span className="radio-dot"/><div><strong>{label}</strong><small>{desc}</small></div>{plan.fit===id&&<Check size={16}/>}</button>)}</div>
  <div className="form-grid">
   <Field label="Плавность"><select value={plan.fps} onChange={e=>onChange({fps:+e.target.value as 30|60})}><option value={30}>30 кадров/с — стандарт</option><option value={60}>60 кадров/с — очень плавно</option></select></Field>
   <Field label="Качество"><select value={plan.quality} onChange={e=>onChange({quality:+e.target.value})}><option value={18}>Высокое (файл больше)</option><option value={20}>Стандартное</option><option value={23}>Компактное (файл меньше)</option></select></Field>
  </div>
 </>;
}

/* ------------------------------------------------------------ timeline */

function Timeline({plan,media,total,starts,playhead,selected,selectedAudio,onSeek,onSelectClip,onSelectAudio,onReorder}:{plan:Plan;media:Record<string,MediaInfo>;total:number;starts:number[];playhead:number;selected:string|null;selectedAudio:string|null;onSeek:(t:number)=>void;onSelectClip:(id:string)=>void;onSelectAudio:(id:string)=>void;onReorder:(from:number,to:number)=>void}){
 const lane=useRef<HTMLDivElement>(null);
 const [drag,setDrag]=useState<number|null>(null),[over,setOver]=useState<number|null>(null);
 if(!plan.clips.length)return null;
 const span=Math.max(total,plan.audio.reduce((n,a)=>Math.max(n,a.at+a.duration),0),.1);
 const pct=(t:number)=>`${t/span*100}%`;
 const seekAt=(e:React.MouseEvent)=>{const box=lane.current?.getBoundingClientRect();if(!box)return;onSeek(clamp((e.clientX-box.left)/box.width,0,1)*span)};
 const ticks=Array.from({length:Math.floor(span/5)+1},(_,i)=>i*5);
 return <div className="montage-timeline">
  <div className="timeline-labels-col"><span/><span><Film size={13}/>Видео</span><span><Music size={13}/>Звук</span></div>
  <div className="timeline-body" ref={lane}>
   <div className="timeline-ruler" onClick={seekAt}>{ticks.map(t=><span key={t} style={{left:pct(t)}}>{time(t)}</span>)}</div>
   <div className="timeline-track">{plan.clips.map((c,n)=>{const info=media[c.id];return <button key={c.id} draggable className={'track-block video'+(selected===c.id?' selected':'')+(over===n&&drag!==null&&drag!==n?' drop':'')} style={{left:pct(starts[n]),width:pct(c.end-c.start)}}
     onClick={e=>{onSelectClip(c.id);seekAt(e)}} onDragStart={()=>setDrag(n)} onDragOver={e=>{e.preventDefault();setOver(n)}} onDragEnd={()=>{setDrag(null);setOver(null)}} onDrop={e=>{e.preventDefault();if(drag!==null&&drag!==n)onReorder(drag,n);setDrag(null);setOver(null)}}
     title={`${info?.title||'Клип'} · ${seconds(c.end-c.start)}`}>
     {info?.thumbnail_url&&<img src={info.thumbnail_url} alt=""/>}<span>{n+1}. {info?.title||'Клип'}</span>
    </button>})}</div>
   <div className="timeline-track audio" onClick={e=>{if(e.target===e.currentTarget)seekAt(e)}}>{plan.audio.map(a=><button key={a.id} className={'track-block sound'+(a.kind==='music'?' ai':'')+(selectedAudio===a.id?' selected':'')} style={{left:pct(a.at),width:pct(Math.min(a.duration,span-a.at))}} onClick={()=>onSelectAudio(a.id)} title={media[a.id]?.title}>{a.kind==='music'?<Sparkles size={12}/>:<AudioLines size={12}/>}<span>{a.kind==='music'?`AI-музыка · ${a.label||''}`:media[a.id]?.title||'Аудио'}</span></button>)}
    {!plan.audio.length&&<span className="track-hint">Музыка и звуки появятся здесь</span>}</div>
   <i className="timeline-playhead" style={{left:pct(Math.min(playhead,span))}}/>
  </div>
 </div>;
}

/* ------------------------------------------------------------ AI music */

type MusicOptions={styles:{id:string;label:string}[];tempos:{id:string;label:string}[];key_connected:boolean;requests_left:number;seconds_left:number;model:string;terms_url:string};
const STYLE_ICON:Record<string,string>={kids:'🧸',action:'💥',epic:'🏔️',fun:'🎉',chill:'☕',tension:'🕵️',romantic:'💞',sport:'🏃',hiphop:'🎧',inspire:'🌅',comedy:'🤡',horror:'👻',custom:'✍️'};

function MusicGenerator({total,job,variants,current,busy,onGenerate,onUse}:{total:number;job?:Job;variants:Variant[];current?:AudioItem;busy:boolean;onGenerate:(b:{style:string;tempo:string;notes:string;consent:true})=>Promise<boolean>;onUse:(v:Variant)=>void}){
 const [options,setOptions]=useState<MusicOptions|null>(null),[style,setStyle]=useState(''),[tempo,setTempo]=useState('auto'),[notes,setNotes]=useState(''),[consent,setConsent]=useState(false);
 const running=!!job&&['Queued','Running','Paused'].includes(job.status);
 const refresh=()=>api('/montage/music-options').then(setOptions).catch(()=>{});
 useEffect(()=>{refresh()},[running]);
 const custom=style==='custom';
 const ready=!!options?.key_connected&&!!style&&(!custom||notes.trim().length>=5)&&consent&&total>=3&&!running&&!busy;
 const generate=async()=>{if(!ready)return;if(await onGenerate({style,tempo,notes,consent:true}))setConsent(false)};
 const currentVariant=current&&variants.find(v=>v.id===current.media_id);
 const shortBy=current?total-current.duration:0;
 return <section className="ai-music">
  <div className="ai-music-head"><Sparkles size={18}/><div><h2>AI-музыка под весь монтаж</h2><small>ElevenLabs · {options?.model||'Eleven Music'}</small></div></div>
  <p className="muted">Выберите жанр — ElevenLabs сочинит инструментальную дорожку ровно на длину монтажа: <b>{time(total)}</b>. Она ляжет фоном под звук клипов.</p>
  {options&&!options.key_connected&&<div className="notice-box"><AlertCircle size={15}/><span>Ключ ElevenLabs не найден. Добавьте его в <a className="inline-link" href="/?settings=voice#settings">Настройки → Озвучка</a>.</span></div>}
  <div className="style-grid">{(options?.styles||[]).map(s=><button key={s.id} className={'style-chip'+(style===s.id?' chosen':'')} onClick={()=>setStyle(s.id)} disabled={running}><span aria-hidden="true">{STYLE_ICON[s.id]||'🎵'}</span>{s.label}</button>)}</div>
  <div className="tempo-row"><span>Темп</span><div className="segmented">{(options?.tempos||[]).map(t=><button key={t.id} className={tempo===t.id?'chosen':''} onClick={()=>setTempo(t.id)} disabled={running}>{t.label}</button>)}</div></div>
  <Field label={custom?'Опишите музыку':'Пожелания (необязательно)'} hint="Например: «как в мультфильмах Pixar, с колокольчиками» или «тяжёлые барабаны, без электрогитар». Можно по-русски.">
   <textarea rows={2} maxLength={400} value={notes} disabled={running} placeholder={custom?'Какую музыку вы хотите услышать?':'Инструменты, настроение, на что похоже…'} onChange={e=>setNotes(e.target.value)}/>
  </Field>
  {running?<div className="montage-result"><strong><Loader2 size={14} className="spin"/> {job!.status==='Queued'?'В очереди…':job!.status==='Paused'?'На паузе':'ElevenLabs сочиняет музыку…'}</strong><small>Обычно 20–90 секунд. Можно продолжать монтаж — дорожка появится сама.</small><div className="progress"><i style={{width:Math.max(6,job!.progress)+'%'}}/></div></div>
   :<>
    <label className="check-row"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>Разрешаю отправить описание в ElevenLabs и потратить кредиты тарифа (1 запрос, {Math.ceil(total)} с музыки).</label>
    <Button variant="default" disabled={!ready} onClick={generate}><Sparkles size={15}/>{current?'Сгенерировать новый вариант':'Сгенерировать музыку'}</Button>
    <p className="muted ai-music-meta">{total<3?'Добавьте клипы: музыке нужно от 3 секунд. ':''}{!style?'Сначала выберите жанр. ':''}{options?`Остаток лимита: ${options.requests_left} запросов, ${Math.floor(options.seconds_left/60)} мин музыки. `:''}{current?'Новый вариант заменит текущую AI-музыку, прошлые останутся ниже.':''}</p>
   </>}
  {current&&shortBy>.5&&<div className="notice-box"><AlertCircle size={15}/><span>Монтаж стал длиннее музыки на {seconds(shortBy)} — сгенерируйте новый вариант, чтобы музыка шла до конца.</span></div>}
  {variants.length>0&&<details className="ai-variants" open={variants.length>1}>
   <summary>Варианты музыки · {variants.length}</summary>
   {variants.map(v=><div className="ai-variant" key={v.job_id}>
    <div className="montage-clip-name"><strong>{v.label}</strong><small>{seconds(v.duration)} · {new Date(v.created_at*1000).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'})}</small></div>
    <audio controls preload="none" src={v.media_url}/>
    {currentVariant?.job_id===v.job_id?<span className="badge positive"><Check size={11}/>В монтаже</span>:<Button size="sm" onClick={()=>onUse(v)}>Использовать</Button>}
   </div>)}
  </details>}
  <p className="muted small-text">Создаётся самостоятельная композиция по описанию. Использование — по <a className="inline-link" href={options?.terms_url||'https://elevenlabs.io/music-terms'} target="_blank" rel="noreferrer">условиям вашего тарифа Eleven Music</a>.</p>
 </section>;
}
