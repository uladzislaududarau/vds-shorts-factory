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
  try{if(!(await save()))return;const result=await fn();setNote(result.note||'Готово');return result}
  catch(e){setError(e instanceof Error?e.message:String(e));return null}
  finally{setBusy('')}
 };
 return {busy,error,note,action};
}
function Result({busy,error,note}:{busy:string;error:string;note:string}){
 return <>{busy&&<p role="status" className="integration-note"><Loader2 size={14} className="spin"/> Выполняю запрос…</p>}{error&&<p role="alert" className="inline-error">{error}</p>}{note&&<p role="status" className="integration-note">{note}</p>}</>;
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
  <div className="settings-row integration-settings"><div><h2>Анализ видео</h2><p>OpenAI оценивает транскрипцию и выборочные кадры. Gemini получает транскрипцию и аудиовизуальные превью. Локальный режим работает без API.</p><p>Для нового английского сценария откройте вкладку «AI-проба».</p></div>
   <div className="panel settings-form">
    <Field label="Провайдер"><select value={values.provider} onChange={e=>{change('provider',e.target.value);setModels([])}}><option value="local">Local · Whisper + эвристика</option><option value="openai">OpenAI · транскрипция + кадры</option><option value="gemini">Google Gemini · мультимодальный анализ</option></select></Field>
    <label className="toggle-row"><div><span>Разрешить облачную обработку</span><small>При запуске анализа дополнительно подтвердите отправку материала выбранному провайдеру.</small></div><input type="checkbox" role="switch" checked={values.cloud_enabled} onChange={e=>change('cloud_enabled',e.target.checked)}/></label>
    {cloud&&<>
     <Field label={provider+' API key'} hint={connected?'Ключ сохранён на этом компьютере; его значение не возвращается в браузер.':'Вставьте ключ провайдера и сохраните настройки.'}><input type="password" autoComplete="new-password" value={keys[keyField]||''} onChange={e=>setKey(keyField,e.target.value)} placeholder={connected?'Ключ сохранён · введите для замены':'Вставьте API key'}/></Field>
     <div className="button-row"><Button disabled={!!busy} onClick={async()=>{const r=await action('connection',()=>post(openai?'/settings/test-openai':'/settings/test-connection'));if(r)setModels(r.models)}}>Test connection</Button><Button variant="ghost" disabled={!!busy||!connected} onClick={()=>{if(confirm(`Удалить сохранённый ключ ${provider}?`))action('delete',()=>api('/settings',{method:'PUT',body:JSON.stringify({values:{},[keyField]:''})}))}}>Удалить ключ</Button></div>
     <Field label={'Модель '+provider} hint="Выберите модель с поддержкой изображений и structured outputs. Список моделей не подтверждает эти возможности или наличие средств."><input list="provider-models" value={values[modelField]} onChange={e=>change(modelField,e.target.value)} placeholder="Выберите после Test connection"/><datalist id="provider-models">{models.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</datalist></Field>
     <a className="text-link" href={openai?'https://platform.openai.com/api-keys':'https://aistudio.google.com/apikey'} target="_blank" rel="noreferrer">Открыть API-ключи {provider}<ExternalLink size={13}/></a>
    </>}
    <Result busy={busy} error={error} note={note}/>
    <Field label="Модель Whisper" hint="Распознавание речи выполняется локально."><select value={values.whisper_model} onChange={e=>change('whisper_model',e.target.value)}>{['mlx-community/whisper-tiny','mlx-community/whisper-base','mlx-community/whisper-small'].map(m=><option key={m}>{m}</option>)}</select></Field>
   </div>
  </div>
  {cloud&&<div className="settings-row integration-settings"><div><h2>Расходы {provider}</h2><p>Укажите актуальные тарифы выбранной модели. Бюджет оценочный и накопительный, не суточный. При неизвестных ценах и активном бюджете генерация блокируется.</p>{usage&&<p>{usage.requests} попыток генерации · оценка {usage.estimated_cost==null?'—':'$'+usage.estimated_cost.toFixed(4)}</p>}<a className="text-link" href={openai?'https://developers.openai.com/api/docs/pricing':'https://ai.google.dev/gemini-api/docs/pricing'} target="_blank" rel="noreferrer">Тарифы {provider}<ExternalLink size={13}/></a></div>
   <div className="panel settings-form"><div className="form-grid">
    <Field label="Бюджет USD · 0 = выключен"><input type="number" min={0} step="0.1" value={values[budget]} onChange={e=>change(budget,+e.target.value)}/></Field>
    <Field label="Лимит запросов"><input type="number" min={1} step={1} value={values[limit]} onChange={e=>change(limit,+e.target.value)}/></Field>
    <Field label="Вход / 1 млн токенов, USD"><input type="number" min={0} step="0.01" value={values[input]??''} placeholder="Не указан" onChange={e=>change(input,e.target.value===''?null:+e.target.value)}/></Field>
    <Field label="Выход / 1 млн токенов, USD"><input type="number" min={0} step="0.01" value={values[output]??''} placeholder="Не указан" onChange={e=>change(output,e.target.value===''?null:+e.target.value)}/></Field>
   </div><Field label="Максимум выходных токенов" hint="Включает reasoning-токены модели. Слишком маленький лимит может оборвать ответ."><input type="number" min={1024} max={openai?16000:32000} step={1024} value={values[openai?'openai_max_output_tokens':'max_output_tokens']} onChange={e=>change(openai?'openai_max_output_tokens':'max_output_tokens',+e.target.value)}/></Field><p className="muted">Фактические расходы смотрите у провайдера. Повторные платные запросы OpenAI автоматически не выполняются.</p></div>
  </div>}
 </>;
}

export function VoiceSettings({config,values,change,keys,setKey,save}:Props){
 const {busy,error,note,action}=useAction(save),[models,setModels]=useState<any[]>([]),[voiceName,setVoiceName]=useState('');
 const [text,setText]=useState('Every detail tells a story. Let’s take a closer look.'),[consent,setConsent]=useState(false),[audio,setAudio]=useState<any>(null);
 return <>
  <div className="settings-row integration-settings"><div><h2>ElevenLabs</h2><p>Новая английская озвучка для сценариев. Укажите API-ключ, Voice ID и модель. Используйте голос с подходящими правами.</p><p>Test connection проверяет доступ к голосу и моделям, без генерации речи.</p><a className="text-link" href="https://elevenlabs.io/app/api/api-keys" target="_blank" rel="noreferrer">API-ключи ElevenLabs<ExternalLink size={13}/></a></div>
   <div className="panel settings-form">
    <Field label="ElevenLabs API key" hint={config.elevenlabs_key_connected?'Ключ сохранён на этом компьютере.':'Ключу нужны права на чтение голоса/моделей и Text to Speech.'}><input type="password" autoComplete="new-password" value={keys.elevenlabs_api_key||''} onChange={e=>setKey('elevenlabs_api_key',e.target.value)} placeholder={config.elevenlabs_key_connected?'Ключ сохранён · введите для замены':'Вставьте ElevenLabs API key'}/></Field>
    <Field label="Voice ID" hint="Скопируйте идентификатор выбранного голоса в ElevenLabs → Voices."><input value={values.elevenlabs_voice_id} onChange={e=>{change('elevenlabs_voice_id',e.target.value);setVoiceName('');setAudio(null)}} placeholder="Voice ID вашего голоса"/></Field>
    <Field label="Модель озвучки"><input list="voice-models" value={values.elevenlabs_model} onChange={e=>{change('elevenlabs_model',e.target.value);setAudio(null)}}/><datalist id="voice-models">{models.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</datalist></Field>
    <Field label="Лимит генераций ElevenLabs" hint={`Накопительно использовано попыток: ${config.integration_usage?.elevenlabs?.requests||0}. Одна проба — до 1200 символов; денежные расходы смотрите в ElevenLabs.`}><input type="number" min={1} max={1000} step={1} value={values.elevenlabs_request_limit} onChange={e=>change('elevenlabs_request_limit',+e.target.value)}/></Field>
    <div className="button-row"><Button disabled={!!busy} onClick={async()=>{const r=await action('connection',()=>post('/settings/test-elevenlabs'));if(r){setModels(r.models);setVoiceName(r.voice_verified?r.voice.name:'')}}}>Test connection</Button><Button variant="ghost" disabled={!!busy||!config.elevenlabs_key_connected} onClick={()=>{if(confirm('Удалить сохранённый ключ ElevenLabs?'))action('delete',()=>api('/settings',{method:'PUT',body:JSON.stringify({values:{},elevenlabs_api_key:''})}))}}>Удалить ключ</Button></div>
    {voiceName&&<p className="integration-note">Доступен голос: {voiceName}</p>}<Result busy={busy==='connection'||busy==='delete'?busy:''} error={error} note={note}/>
   </div>
  </div>
  <div className="settings-row integration-settings"><div><h2>Проба голоса</h2><p>Создайте короткую озвучку и прослушайте результат. Генерация расходует лимит ElevenLabs. Повтор того же текста с тем же голосом и моделью использует кэш.</p></div>
   <div className="panel settings-form"><Field label="Текст для озвучки" hint={`${text.length} / 1200 символов`}><textarea maxLength={1200} rows={4} value={text} onChange={e=>{setText(e.target.value);setAudio(null);setConsent(false)}}/></Field>
    <label className="check-row"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>Разрешаю отправить этот текст в ElevenLabs и выполнить платную генерацию по моему тарифу.</label>
    <Button disabled={!!busy||!consent||!text.trim()} onClick={async()=>{const r=await action('voice',()=>post('/integrations/voice-preview',{consent:true,text}));if(r)setAudio(r)}}>{busy==='voice'?<Loader2 size={14} className="spin"/>:null}Создать пробу голоса</Button>
    {audio&&<div className="voice-result"><audio controls src={audio.url}/><p>{audio.duration.toFixed(1)} с · {audio.cached?'Из кэша':'Новая озвучка'}</p><a href={audio.url} download="voice-preview.mp3" className="text-link">Скачать MP3</a></div>}
   </div>
  </div>
  <div className="settings-row integration-settings"><div><h2>Eleven Music · замена музыки</h2><p>Используется прямо в Generate Reel для одного или выбранной пачки клипов. На каждый клип создаётся самостоятельная инструментальная композиция по настроению и темпу.</p><p>Нужен доступ Music Generation в ключе ElevenLabs и подходящий платный тариф. TTS и музыка — разные возможности одного сервиса.</p><a className="text-link" href="https://elevenlabs.io/music-terms" target="_blank" rel="noreferrer">Условия Eleven Music<ExternalLink size={13}/></a></div>
   <div className="panel settings-form"><Field label="Модель музыки"><select value={values.music_model} onChange={e=>change('music_model',e.target.value)}>{['music_v2_5','music_v2','music_v1'].map(model=><option key={model}>{model}</option>)}</select></Field>
    <Field label="Лимит запросов музыки" hint={`Уже попыток: ${config.integration_usage?.music?.requests||0}. Один клип — до одного нового запроса музыки.`}><input type="number" min={1} max={1000} step={1} value={values.music_request_limit} onChange={e=>change('music_request_limit',+e.target.value)}/></Field>
    <Field label="Лимит заказанной музыки, секунд" hint={`Уже заказано: ${Math.ceil(config.integration_usage?.music?.seconds||0)} с. Например, 50 роликов по 30 секунд — около 1500 секунд музыки. Это накопительный лимит, не денежный бюджет.`}><input type="number" min={3} max={100000} step={1} value={values.music_seconds_limit} onChange={e=>change('music_seconds_limit',+e.target.value)}/></Field>
    <p className="muted">Для 50 переозвучек также увеличьте лимит генераций голоса выше с учётом уже использованных запросов. Предварительная проверка остановит пачку, если лимитов недостаточно.</p>
   </div>
  </div>
 </>;
}

export function AuthorPilotSettings({config,save}:{config:any;save:Props['save']}){
 const {busy,error,note,action}=useAction(save),[clips,setClips]=useState<Clip[]>([]),[clipId,setClipId]=useState('');
 const [consent,setConsent]=useState(false),[draft,setDraft]=useState<any>(null),[text,setText]=useState(''),[audio,setAudio]=useState<any>(null),[loadError,setLoadError]=useState('');
 useEffect(()=>{Promise.all([api<Clip[]>('/clips'),api('/integrations/author-pilot')]).then(([items,last])=>{const available=items.filter(c=>c.end-c.start<=90);setClips(available);const pilot=last.pilot;if(pilot&&available.some(c=>c.id===pilot.clip_id)){setClipId(pilot.clip_id);setDraft(pilot);setText(pilot.script);setAudio(pilot.voice||null)}else setClipId(available[0]?.id||'')}).catch(e=>setLoadError(e.message))},[]);
 return <div className="settings-row integration-settings"><div><h2>Авторский сценарий · проба</h2><p>Выберите один клип до 90 секунд. OpenAI получит шесть кадров и доступную транскрипцию, затем предложит самостоятельный английский сценарий.</p><p>Это черновик для проверки фактов. Исходный клип сохраняется; новый MP4 и публикация здесь не создаются.</p><p>После проверки текста можно получить озвучку ElevenLabs. Обе генерации используют заданные лимиты.</p></div>
  <div className="panel settings-form">
   <Field label="Фрагмент из библиотеки"><select value={clipId} onChange={e=>{setClipId(e.target.value);setDraft(null);setText('');setAudio(null);setConsent(false)}}>{clips.map(c=><option key={c.id} value={c.id}>{c.title} · {(c.end-c.start).toFixed(0)} с</option>)}</select></Field>
   {loadError&&<p role="alert" className="inline-error">{loadError}</p>}{!clips.length&&!loadError&&<p className="muted">Добавьте в библиотеку клип до 90 секунд из скачанного исходника.</p>}
   {!config.openai_key_connected&&<p className="muted">Сначала сохраните ключ и модель OpenAI на вкладке «AI и модели».</p>}
   <label className="check-row"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/>Разрешаю отправить кадры и транскрипцию в OpenAI, а текст при озвучке — в ElevenLabs. Запросы оплачиваются по моим тарифам.</label>
   <Button disabled={!!busy||!consent||!clipId} onClick={async()=>{const r=await action('script',()=>post('/integrations/author-pilot',{consent:true,clip_id:clipId}));if(r){setDraft(r);setText(r.script);setAudio(null)}}}>{busy==='script'?<Loader2 size={14} className="spin"/>:null}Создать сценарий OpenAI</Button>
   <Result busy={busy} error={error} note={note}/>
   {draft&&<div className="pilot-result"><h3>{draft.title}</h3><span className="badge">Нужна проверка</span><div className="pilot-observations">{draft.observations.map((o:any,i:number)=><div key={i}><strong>{o.timestamp.toFixed(2)} с</strong><p>{o.visible_detail}</p>{o.interpretation&&<p className="muted">Интерпретация: {o.interpretation}</p>}</div>)}</div>{draft.warnings.map((w:string,i:number)=><p className="muted" key={i}>{w}</p>)}
    <Field label="Английский сценарий" hint={`${text.length} / 1200 символов. Проверьте факты и произношение названий.`}><textarea rows={8} maxLength={1200} value={text} onChange={e=>{setText(e.target.value);setAudio(null)}}/></Field>
    <Button disabled={!!busy||!consent||!text.trim()||!config.elevenlabs_key_connected} onClick={async()=>{const r=await action('voice',()=>post('/integrations/voice-preview',{consent:true,text}));if(r)setAudio(r)}}>Озвучить сценарий ElevenLabs</Button>
    {!config.elevenlabs_key_connected&&<p className="muted">Ключ и Voice ID добавляются на вкладке «Озвучка».</p>}
    {audio&&<div className="voice-result"><audio controls src={audio.url}/><a href={audio.url} download="commentary-preview.mp3" className="text-link">Скачать озвучку MP3</a></div>}
   </div>}
  </div>
 </div>;
}
