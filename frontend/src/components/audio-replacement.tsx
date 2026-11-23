import {tr} from '../i18n';
import type {ReactNode} from 'react';
const Field=({label,children}:{label:string;children:ReactNode})=><label className="field"><span>{label}</span>{children}</label>;
export const defaultAudio=()=>({mode:'original',music_prompt:'Dark cinematic electronic instrumental, tense atmosphere, steady mid-tempo pulse, restrained bass and percussion, no vocals.',music_volume:.3,voice_volume:1,consent:false});
export function AudioReplacementControls({value,onChange,config,count=1,seconds=0,allowKeep=false}:{value:any;onChange:(v:any)=>void;config?:any;count?:number;seconds?:number;allowKeep?:boolean}){
 const audio={...defaultAudio(),...value};
 const set=(k:string,v:any)=>onChange({...audio,[k]:v});
 const usage=config?.integration_usage;
 return <section className="audio-replacement-controls">
  <h3>{tr("Звуковая дорожка")}</h3>
  <Field label={tr("Режим звука")}><select value={audio.mode} onChange={e=>onChange({...audio,mode:e.target.value,consent:false})}>{allowKeep&&<option value="keep">{tr("Использовать настройки звука каждого клипа")}</option>}<option value="original">{tr("Оставить исходный звук")}</option><option value="music">{tr("Новая AI-музыка · убрать речь и исходный звук")}</option><option value="music_voice">{tr("Новая AI-музыка + переозвучить те же слова")}</option></select></Field>
  {!['original','keep'].includes(audio.mode)&&<>
   <p className="muted">{tr("Исходная аудиодорожка полностью исключается из MP4, включая музыку, голоса и эффекты.")} {audio.mode==='music_voice'?tr("Распознанные слова озвучит выбранный голос ElevenLabs; интонации и синхронизация губ не сохраняются."):tr("Вместо неё будет только новая инструментальная музыка.")}</p>
   {audio.mode==='music_voice'&&<p className="muted">{tr("Проверьте распознанные слова перед большой пачкой: ошибки транскрипции попадут в новую речь. Исправления слов из Clip Studio учитываются.")}</p>}
   <Field label={tr("Характер новой музыки")}><select value="" onChange={e=>{if(e.target.value)set('music_prompt',e.target.value)}}><option value="">{tr("Выбрать настроение…")}</option><option value="Dark cinematic electronic instrumental, tense atmosphere, steady mid-tempo pulse, restrained bass and percussion, no vocals.">{tr("Напряжённая · cinematic electronic")}</option><option value="Upbeat energetic instrumental, punchy drums, bright synths, steady driving rhythm, optimistic mood, no vocals.">{tr("Энергичная · upbeat electronic")}</option><option value="Quiet atmospheric instrumental, spacious ambient pads, subtle percussion, restrained cinematic texture, no vocals.">{tr("Спокойная · ambient")}</option></select></Field>
   <Field label={tr("Настроение, темп и инструменты")}><textarea rows={3} maxLength={700} value={audio.music_prompt} onChange={e=>set('music_prompt',e.target.value)}/></Field>
   <div className="form-grid"><Field label={tr("Громкость музыки, %")}><input type="number" min={0} max={100} value={Math.round(audio.music_volume*100)} onChange={e=>set('music_volume',+e.target.value/100)}/></Field>{audio.mode==='music_voice'&&<Field label={tr("Громкость голоса, %")}><input type="number" min={0} max={200} value={Math.round(audio.voice_volume*100)} onChange={e=>set('voice_volume',+e.target.value/100)}/></Field>}</div>
   <p className="muted">{tr("До")} {count} {tr("новых композиций")}{seconds>0?tr(" · около {0} мин музыки",[Math.ceil(seconds/60)]):''}{audio.mode==='music_voice'?tr(" и до {0} переозвучек",[count]):''}{tr(". Eleven Music и голос расходуют кредиты ElevenLabs отдельно от OpenAI. Повторы используют готовые дорожки из кэша.")}</p>
   {usage&&<p className="muted">{tr("Остаток лимитов: музыка —")} {Math.max(0,(config.values.music_request_limit||0)-(usage.music?.requests||0))} {tr("запросов,")} {Math.max(0,Math.floor(((config.values.music_seconds_limit||0)-(usage.music?.seconds||0))/60))} {tr("мин; голос —")} {Math.max(0,(config.values.elevenlabs_request_limit||0)-(usage.elevenlabs?.requests||0))} {tr("запросов. Лимиты меняются в «Настройки → Озвучка».")}</p>}
   <p className="muted">{tr("Генерируется самостоятельная композиция в заданном настроении. Условия использования зависят от")} <a href="https://elevenlabs.io/music-terms" target="_blank" rel="noreferrer" className="text-link">{tr("тарифа Eleven Music")}</a>{tr(". Это не копия оригинальной песни и не гарантия отсутствия претензий к видео.")}</p>
   <label className="check-row"><input type="checkbox" checked={audio.consent} onChange={e=>set('consent',e.target.checked)}/>{tr("Разрешаю генерацию новой музыки и, при выборе, отправку исходного текста речи в ElevenLabs. Запросы расходуют мой тариф.")}</label>
  </>}
 </section>;
}
