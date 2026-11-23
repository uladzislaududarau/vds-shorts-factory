import {tr} from '../i18n';
import {useEffect,useState,type ReactNode} from 'react';
import {ExternalLink,Loader2} from 'lucide-react';
import {Button} from './ui/button';
import {api,post,type Clip} from '../lib';

const Field=({label,hint,children}:{label:string;hint?:string;children:ReactNode})=><label className="field"><span>{label}</span>{children}{hint&&<small>{hint}</small>}</label>;
type Props={config:any;values:any;change:(key:string,value:any)=>void;keys:Record<string,string>;setKey:(key:string,value:string)=>void;save:()=>Promise<any>};

function useAction(save:Props['save']){
 const [busy,setBusy]=useState(''),[error,setError]=useState(''),[note,setNote]=useState('');
 const action=async(name:string,fn:()=>Promise<any>)=>{
  setBusy(name);setError('');setNote('');
  try{if(!(await save()))return;const result=await fn();setNote(result.note||tr("Готово"));return result}
  catch(e){setError(e instanceof Error?e.message:String(e));return null}
  finally{setBusy('')}
 };
 return {busy,error,note,action};
}
function Result({busy,error,note}:{busy:string;error:string;note:string}){
 return <>{busy&&<p role="status" className="integration-note"><Loader2 size={14} className="spin"/> {tr("Выполняю запрос…")}</p>}{error&&<p role="alert" className="inline-error">{error}</p>}{note&&<p role="status" className="integration-note">{note}</p>}</>;
}

export function AISettings({config,values,change,keys,setKey,save}:Props){
 const {busy,error,note,action}=useAction(save),[models,setModels]=useState<any[]>([]);
 const openai=values.provider==='openai',cloud=values.provider!=='local';
 const provider=openai?'OpenAI':'Gemini',keyField=openai?'openai_api_key':'api_key';
 const modelField=openai?'openai_model':'model';
 const connected=openai?config.openai_key_connected:config.key_connected;
 const budget=openai?'openai_budget_usd':'budget_usd',limit=openai?'openai_request_limit':'cloud_request_limit';
 const input=openai?'openai_input_price_per_million':'input_price_per_million',output=openai?'openai_output_price_per_million':'output_price_per_million';
 const usage=openai?config.integration_usage?.openai:null;
 return <>
  <div className="settings-row integration-settings"><div><h2>{tr("Анализ видео")}</h2><p>{tr("OpenAI оценивает транскрипцию и выборочные кадры. Gemini получает транскрипцию и аудиовизуальные превью. Локальный режим работает без API.")}</p><p>{tr("Для нового английского сценария откройте вкладку «AI-проба».")}</p></div>
   <div className="panel settings-form">
    <Field label={tr("Провайдер")}><select value={values.provider} onChange={e=>{change('provider',e.target.value);setModels([])}}><option value="local">{tr("Local · Whisper + эвристика")}</option><option value="openai">{tr("OpenAI · транскрипция + кадры")}</option><option value="gemini">{tr("Google Gemini · мультимодальный анализ")}</option></select></Field>
    <label className="toggle-row"><div><span>{tr("Разрешить облачную обработку")}</span><small>{tr("При запуске анализа дополнительно подтвердите отправку материала выбранному провайдеру.")}</small></div><input type="checkbox" role="switch" checked={values.cloud_enabled} onChange={e=>change('cloud_enabled',e.target.checked)}/></label>
    {cloud&&<>
     <Field label={provider+' API key'} hint={connected?tr("Ключ сохранён на этом компьютере; его значение не возвращается в браузер."):tr("Вставьте ключ провайдера и сохраните настройки.")}><input type="password" autoComplete="new-password" value={keys[keyField]||''} onChange={e=>setKey(keyField,e.target.value)} placeholder={connected?tr("Ключ сохранён · введите для замены"):tr("Вставьте API key")}/></Field>
     <div className="button-row"><Button disabled={!!busy} onClick={async()=>{const r=await action('connection',()=>post(openai?'/settings/test-openai':'/settings/test-connection'));if(r)setModels(r.models)}}>Test connection</Button><Button variant="ghost" disabled={!!busy||!connected} onClick={()=>{if(confirm(tr("Удалить сохранённый ключ {0}?",[provider])))action('delete',()=>api('/settings',{method:'PUT',body:JSON.stringify({values:{},[keyField]:''})}))}}>{tr("Удалить ключ")}</Button></div>
     <Field label={tr("Модель ")+provider} hint={tr("Выберите модель с поддержкой изображений и structured outputs. Список моделей не подтверждает эти возможности или наличие средств.")}><input list="provider-models" value={values[modelField]} onChange={e=>change(modelField,e.target.value)} placeholder={tr("Выберите после Test connection")}/><datalist id="provider-models">{models.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</datalist></Field>
     <a className="text-link" href={openai?'https://platform.openai.com/api-keys':'https://aistudio.google.com/apikey'} target="_blank" rel="noreferrer">{tr("Открыть API-ключи")} {provider}<ExternalLink size={13}/></a>
    </>}
    <Result busy={busy} error={error} note={note}/>
    <Field label={tr("Модель Whisper")} hint={tr("Распознавание речи выполняется локально.")}><select value={values.whisper_model} onChange={e=>change('whisper_model',e.target.value)}>{['mlx-community/whisper-tiny','mlx-community/whisper-base','mlx-community/whisper-small'].map(m=><option key={m}>{m}</option>)}</select></Field>
   </div>
  </div>
  {cloud&&<div className="settings-row integration-settings"><div><h2>{tr("Расходы")} {provider}</h2><p>{tr("Укажите актуальные тарифы выбранной модели. Бюджет оценочный и накопительный, не суточный. При неизвестных ценах и активном бюджете генерация блокируется.")}</p>{usage&&<p>{usage.requests} {tr("попыток генерации · оценка")} {usage.estimated_cost==null?'—':'$'+usage.estimated_cost.toFixed(4)}</p>}<a className="text-link" href={openai?'https://developers.openai.com/api/docs/pricing':'https://ai.google.dev/gemini-api/docs/pricing'} target="_blank" rel="noreferrer">{tr("Тарифы")} {provider}<ExternalLink size={13}/></a></div>
   <div className="panel settings-form"><div className="form-grid">
    <Field label={tr("Бюджет USD · 0 = выключен")}><input type="number" min={0} step="0.1" value={values[budget]} onChange={e=>change(budget,+e.target.value)}/></Field>
    <Field label={tr("Лимит запросов")}><input type="number" min={1} step={1} value={values[limit]} onChange={e=>change(limit,+e.target.value)}/></Field>
    <Field label={tr("Вход / 1 млн токенов, USD")}><input type="number" min={0} step="0.01" value={values[input]??''} placeholder={tr("Не указан")} onChange={e=>change(input,e.target.value===''?null:+e.target.value)}/></Field>
    <Field label={tr("Выход / 1 млн токенов, USD")}><input type="number" min={0} step="0.01" value={values[output]??''} placeholder={tr("Не указан")} onChange={e=>change(output,e.target.value===''?null:+e.target.value)}/></Field>
   </div><Field label={tr("Максимум выходных токенов")} hint={tr("Включает reasoning-токены модели. Слишком маленький лимит может оборвать ответ.")}><input type="number" min={1024} max={openai?16000:32000} step={1024} value={values[openai?'openai_max_output_tokens':'max_output_tokens']} onChange={e=>change(openai?'openai_max_output_tokens':'max_output_tokens',+e.target.value)}/></Field><p className="muted">{tr("Фактические расходы смотрите у провайдера. Повторные платные запросы OpenAI автоматически не выполняются.")}</p></div>
  </div>}
 </>;
}

export function VoiceSettings({config,values,change,keys,setKey,save}:Props){
 const {busy,error,note,action}=useAction(save),[models,setModels]=useState<any[]>([]),[voiceName,setVoiceName]=useState('');
 const [text,setText]=useState('Every detail tells a story. Let’s take a closer look.'),[consent,setConsent]=useState(false),[audio,setAudio]=useState<any>(null);
 return <>
  <div className="settings-row integration-settings"><div><h2>ElevenLabs</h2><p>{tr("Новая английская озвучка для сценариев. Укажите API-ключ, Voice ID и модель. Используйте голос с подходящими правами.")}</p><p>{tr("Test connection проверяет доступ к голосу и моделям, без генерации речи.")}</p><a className="text-link" href="https://elevenlabs.io/app/api/api-keys" target="_blank" rel="noreferrer">{tr("API-ключи ElevenLabs")}<ExternalLink size={13}/></a></div>
   <div className="panel settings-form">
    <Field label="ElevenLabs API key" hint={config.elevenlabs_key_connected?tr("Ключ сохранён на этом компьютере."):tr("Ключу нужны права на чтение голоса/моделей и Text to Speech.")}><input type="password" autoComplete="new-password" value={keys.elevenlabs_api_key||''} onChange={e=>setKey('elevenlabs_api_key',e.target.value)} placeholder={config.elevenlabs_key_connected?tr("Ключ сохранён · введите для замены"):tr("Вставьте ElevenLabs API key")}/></Field>
    <Field label="Voice ID" hint={tr("Скопируйте идентификатор выбранного голоса в ElevenLabs → Voices.")}><input value={values.elevenlabs_voice_id} onChange={e=>{change('elevenlabs_voice_id',e.target.value);setVoiceName('');setAudio(null)}} placeholder={tr("Voice ID вашего голоса")}/></Field>
    <Field label={tr("Модель озвучки")}><input list="voice-models" value={values.elevenlabs_model} onChange={e=>{change('elevenlabs_model',e.target.value);setAudio(null)}}/><datalist id="voice-models">{models.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</datalist></Field>
    <Field label={tr("Лимит генераций ElevenLabs")} hint={tr("Накопительно использовано попыток: {0}. Одна проба — до 1200 символов; денежные расходы смотрите в ElevenLabs.",[config.integration_usage?.elevenlabs?.requests||0])}><input type="number" min={1} max={1000} step={1} value={values.elevenlabs_request_limit} onChange={e=>change('elevenlabs_request_limit',+e.target.value)}/></Field>
    <div className="button-row"><Button disabled={!!busy} onClick={async()=>{const r=await action('connection',()=>post('/settings/test-elevenlabs'));if(r){setModels(r.models);setVoiceName(r.voice_verified?r.voice.name:'')}}}>Test connection</Button><Button variant="ghost" disabled={!!busy||!config.elevenlabs_key_connected} onClick={()=>{if(confirm(tr("Удалить сохранённый ключ ElevenLabs?")))action('delete',()=>api('/settings',{method:'PUT',body:JSON.stringify({values:{},elevenlabs_api_key:''})}))}}>{tr("Удалить ключ")}</Button></div>
    {voiceName&&<p className="integration-note">{tr("Доступен голос:")} {voiceName}</p>}<Result busy={busy==='connection'||busy==='delete'?busy:''} error={error} note={note}/>
   </div>
  </div>
  <div className="settings-row integration-settings"><div><h2>{tr("Проба голоса")}</h2><p>{tr("Создайте короткую озвучку и прослушайте результат. Генерация расходует лимит ElevenLabs. Повтор того же текста с тем же голосом и моделью использует кэш.")}</p></div>
   <div className="panel settings-form"><Field label={tr("Текст для озвучки")} hint={tr("{0} / 1200 символов",[text.length])}><textarea maxLength={1200} rows={4} value={text} onChange={e=>{setText(e.target.value);setAudio(null);setConsent(false)}}/></Field>
    <label className="check-row"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>{tr("Разрешаю отправить этот текст в ElevenLabs и выполнить платную генерацию по моему тарифу.")}</label>
    <Button disabled={!!busy||!consent||!text.trim()} onClick={async()=>{const r=await action('voice',()=>post('/integrations/voice-preview',{consent:true,text}));if(r)setAudio(r)}}>{busy==='voice'?<Loader2 size={14} className="spin"/>:null}{tr("Создать пробу голоса")}</Button>
    {audio&&<div className="voice-result"><audio controls src={audio.url}/><p>{audio.duration.toFixed(1)} {tr("с ·")} {audio.cached?tr("Из кэша"):tr("Новая озвучка")}</p><a href={audio.url} download="voice-preview.mp3" className="text-link">{tr("Скачать MP3")}</a></div>}
   </div>
  </div>
  <div className="settings-row integration-settings"><div><h2>{tr("Eleven Music · замена музыки")}</h2><p>{tr("Используется прямо в Generate Reel для одного или выбранной пачки клипов. На каждый клип создаётся самостоятельная инструментальная композиция по настроению и темпу.")}</p><p>{tr("Нужен доступ Music Generation в ключе ElevenLabs и подходящий платный тариф. TTS и музыка — разные возможности одного сервиса.")}</p><a className="text-link" href="https://elevenlabs.io/music-terms" target="_blank" rel="noreferrer">{tr("Условия Eleven Music")}<ExternalLink size={13}/></a></div>
   <div className="panel settings-form"><Field label={tr("Модель музыки")}><select value={values.music_model} onChange={e=>change('music_model',e.target.value)}>{['music_v2_5','music_v2','music_v1'].map(model=><option key={model}>{model}</option>)}</select></Field>
    <Field label={tr("Лимит запросов музыки")} hint={tr("Уже попыток: {0}. Один клип — до одного нового запроса музыки.",[config.integration_usage?.music?.requests||0])}><input type="number" min={1} max={1000} step={1} value={values.music_request_limit} onChange={e=>change('music_request_limit',+e.target.value)}/></Field>
    <Field label={tr("Лимит заказанной музыки, секунд")} hint={tr("Уже заказано: {0} с. Например, 50 роликов по 30 секунд — около 1500 секунд музыки. Это накопительный лимит, не денежный бюджет.",[Math.ceil(config.integration_usage?.music?.seconds||0)])}><input type="number" min={3} max={100000} step={1} value={values.music_seconds_limit} onChange={e=>change('music_seconds_limit',+e.target.value)}/></Field>
    <p className="muted">{tr("Для 50 переозвучек также увеличьте лимит генераций голоса выше с учётом уже использованных запросов. Предварительная проверка остановит пачку, если лимитов недостаточно.")}</p>
   </div>
  </div>
 </>;
}

export function AuthorPilotSettings({config,save}:{config:any;save:Props['save']}){
 const {busy,error,note,action}=useAction(save),[clips,setClips]=useState<Clip[]>([]),[clipId,setClipId]=useState('');
 const [consent,setConsent]=useState(false),[draft,setDraft]=useState<any>(null),[text,setText]=useState(''),[audio,setAudio]=useState<any>(null),[loadError,setLoadError]=useState('');
 useEffect(()=>{Promise.all([api<Clip[]>('/clips'),api('/integrations/author-pilot')]).then(([items,last])=>{const available=items.filter(c=>c.end-c.start<=90);setClips(available);const pilot=last.pilot;if(pilot&&available.some(c=>c.id===pilot.clip_id)){setClipId(pilot.clip_id);setDraft(pilot);setText(pilot.script);setAudio(pilot.voice||null)}else setClipId(available[0]?.id||'')}).catch(e=>setLoadError(e.message))},[]);
 return <div className="settings-row integration-settings"><div><h2>{tr("Авторский сценарий · проба")}</h2><p>{tr("Выберите один клип до 90 секунд. OpenAI получит шесть кадров и доступную транскрипцию, затем предложит самостоятельный английский сценарий.")}</p><p>{tr("Это черновик для проверки фактов. Исходный клип сохраняется; новый MP4 и публикация здесь не создаются.")}</p><p>{tr("После проверки текста можно получить озвучку ElevenLabs. Обе генерации используют заданные лимиты.")}</p></div>
  <div className="panel settings-form">
   <Field label={tr("Фрагмент из библиотеки")}><select value={clipId} onChange={e=>{setClipId(e.target.value);setDraft(null);setText('');setAudio(null);setConsent(false)}}>{clips.map(c=><option key={c.id} value={c.id}>{c.title} · {(c.end-c.start).toFixed(0)} {tr("с")}</option>)}</select></Field>
   {loadError&&<p role="alert" className="inline-error">{loadError}</p>}{!clips.length&&!loadError&&<p className="muted">{tr("Добавьте в библиотеку клип до 90 секунд из скачанного исходника.")}</p>}
   {!config.openai_key_connected&&<p className="muted">{tr("Сначала сохраните ключ и модель OpenAI на вкладке «AI и модели».")}</p>}
   <label className="check-row"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>{tr("Разрешаю отправить кадры и транскрипцию в OpenAI, а текст при озвучке — в ElevenLabs. Запросы оплачиваются по моим тарифам.")}</label>
   <Button disabled={!!busy||!consent||!clipId} onClick={async()=>{const r=await action('script',()=>post('/integrations/author-pilot',{consent:true,clip_id:clipId}));if(r){setDraft(r);setText(r.script);setAudio(null)}}}>{busy==='script'?<Loader2 size={14} className="spin"/>:null}{tr("Создать сценарий OpenAI")}</Button>
   <Result busy={busy} error={error} note={note}/>
   {draft&&<div className="pilot-result"><h3>{draft.title}</h3><span className="badge">{tr("Нужна проверка")}</span><div className="pilot-observations">{draft.observations.map((o:any,i:number)=><div key={i}><strong>{o.timestamp.toFixed(2)} {tr("с")}</strong><p>{o.visible_detail}</p>{o.interpretation&&<p className="muted">{tr("Интерпретация:")} {o.interpretation}</p>}</div>)}</div>{draft.warnings.map((w:string,i:number)=><p className="muted" key={i}>{w}</p>)}
    <Field label={tr("Английский сценарий")} hint={tr("{0} / 1200 символов. Проверьте факты и произношение названий.",[text.length])}><textarea rows={8} maxLength={1200} value={text} onChange={e=>{setText(e.target.value);setAudio(null)}}/></Field>
    <Button disabled={!!busy||!consent||!text.trim()||!config.elevenlabs_key_connected} onClick={async()=>{const r=await action('voice',()=>post('/integrations/voice-preview',{consent:true,text}));if(r)setAudio(r)}}>{tr("Озвучить сценарий ElevenLabs")}</Button>
    {!config.elevenlabs_key_connected&&<p className="muted">{tr("Ключ и Voice ID добавляются на вкладке «Озвучка».")}</p>}
    {audio&&<div className="voice-result"><audio controls src={audio.url}/><a href={audio.url} download="commentary-preview.mp3" className="text-link">{tr("Скачать озвучку MP3")}</a></div>}
   </div>}
  </div>
 </div>;
}
