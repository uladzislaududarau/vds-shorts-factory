import type {ReactNode} from 'react';
const Field=({label,children}:{label:string;children:ReactNode})=><label className="field"><span>{label}</span>{children}</label>;
export const defaultAudio=()=>({mode:'original',music_prompt:'Dark cinematic electronic instrumental, tense atmosphere, steady mid-tempo pulse, restrained bass and percussion, no vocals.',music_volume:.3,voice_volume:1,consent:false});
export function AudioReplacementControls({value,onChange,config,count=1,seconds=0,allowKeep=false}:{value:any;onChange:(v:any)=>void;config?:any;count?:number;seconds?:number;allowKeep?:boolean}){
 const audio={...defaultAudio(),...value};
 const set=(k:string,v:any)=>onChange({...audio,[k]:v});
 const usage=config?.integration_usage;
 return <section className="audio-replacement-controls">
  <h3>Звуковая дорожка</h3>
  <Field label="Режим звука"><select value={audio.mode} onChange={e=>onChange({...audio,mode:e.target.value,consent:false})}>{allowKeep&&<option value="keep">Использовать настройки звука каждого клипа</option>}<option value="original">Оставить исходный звук</option><option value="music">Новая AI-музыка · убрать речь и исходный звук</option><option value="music_voice">Новая AI-музыка + переозвучить те же слова</option></select></Field>
  {!['original','keep'].includes(audio.mode)&&<>
   <p className="muted">Исходная аудиодорожка полностью исключается из MP4, включая музыку, голоса и эффекты. {audio.mode==='music_voice'?'Распознанные слова озвучит выбранный голос ElevenLabs; интонации и синхронизация губ не сохраняются.':'Вместо неё будет только новая инструментальная музыка.'}</p>
   {audio.mode==='music_voice'&&<p className="muted">Проверьте распознанные слова перед большой пачкой: ошибки транскрипции попадут в новую речь. Исправления слов из Clip Studio учитываются.</p>}
   <Field label="Характер новой музыки"><select value="" onChange={e=>{if(e.target.value)set('music_prompt',e.target.value)}}><option value="">Выбрать настроение…</option><option value="Dark cinematic electronic instrumental, tense atmosphere, steady mid-tempo pulse, restrained bass and percussion, no vocals.">Напряжённая · cinematic electronic</option><option value="Upbeat energetic instrumental, punchy drums, bright synths, steady driving rhythm, optimistic mood, no vocals.">Энергичная · upbeat electronic</option><option value="Quiet atmospheric instrumental, spacious ambient pads, subtle percussion, restrained cinematic texture, no vocals.">Спокойная · ambient</option></select></Field>
   <Field label="Настроение, темп и инструменты"><textarea rows={3} maxLength={700} value={audio.music_prompt} onChange={e=>set('music_prompt',e.target.value)}/></Field>
   <div className="form-grid"><Field label="Громкость музыки, %"><input type="number" min={0} max={100} value={Math.round(audio.music_volume*100)} onChange={e=>set('music_volume',+e.target.value/100)}/></Field>{audio.mode==='music_voice'&&<Field label="Громкость голоса, %"><input type="number" min={0} max={200} value={Math.round(audio.voice_volume*100)} onChange={e=>set('voice_volume',+e.target.value/100)}/></Field>}</div>
   <p className="muted">До {count} новых композиций{seconds>0?` · около ${Math.ceil(seconds/60)} мин музыки`:''}{audio.mode==='music_voice'?` и до ${count} переозвучек`:''}. Eleven Music и голос расходуют кредиты ElevenLabs отдельно от OpenAI. Повторы используют готовые дорожки из кэша.</p>
   {usage&&<p className="muted">Остаток лимитов: музыка — {Math.max(0,(config.values.music_request_limit||0)-(usage.music?.requests||0))} запросов, {Math.max(0,Math.floor(((config.values.music_seconds_limit||0)-(usage.music?.seconds||0))/60))} мин; голос — {Math.max(0,(config.values.elevenlabs_request_limit||0)-(usage.elevenlabs?.requests||0))} запросов. Лимиты меняются в «Настройки → Озвучка».</p>}
   <p className="muted">Генерируется самостоятельная композиция в заданном настроении. Условия использования зависят от <a href="https://elevenlabs.io/music-terms" target="_blank" rel="noreferrer" className="text-link">тарифа Eleven Music</a>. Это не копия оригинальной песни и не гарантия отсутствия претензий к видео.</p>
   <label className="check-row"><input type="checkbox" checked={audio.consent} onChange={e=>set('consent',e.target.checked)}/>Разрешаю генерацию новой музыки и, при выборе, отправку исходного текста речи в ElevenLabs. Запросы расходуют мой тариф.</label>
  </>}
 </section>;
}
