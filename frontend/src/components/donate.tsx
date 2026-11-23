import {tr} from '../i18n';
import {useEffect,useMemo,useRef,useState,type ReactNode} from 'react';
import {Check,ChevronDown,Copy,Sparkles,X} from 'lucide-react';
import qrcode from 'qrcode-generator';
import {Button} from './ui/button';

// The author's wallets. QR codes are generated from these addresses on this computer — nothing is loaded from the internet.
// Checksums of all addresses verified (bech32 / EIP-55 / base58check / 32-byte ed25519) on 21.11.2026.
const BTC='bc1q8vn6mv7vk2lnlfa3my896cynksxkpl6jnzzezg';
const EVM='0x7cDC8cBbD9AFFaB70B54587A4282e17272CE8c62';   // one address for Ethereum and BNB Smart Chain
const SOL='8Vz1gj6cnaSw1eM3SFtfmyx8JfgVbbVU2mbWYUh5BtZJ';
const TRON='TP1dznp6UirK4yeAhpigSV56U3kndS95CN';

export type Network={label:string;address:string};
export type Coin={ticker:string;name:string;networks:Network[]};

export const COINS:Coin[]=[
 {ticker:'BTC',name:'Bitcoin',networks:[{label:'Bitcoin',address:BTC}]},
 {ticker:'ETH',name:'Ethereum',networks:[{label:'Ethereum (ERC-20)',address:EVM}]},
 {ticker:'USDT',name:'Tether',networks:[{label:'Tron (TRC-20)',address:TRON},{label:'Ethereum (ERC-20)',address:EVM},{label:'BSC (BEP-20)',address:EVM}]},
 {ticker:'USDC',name:'USD Coin',networks:[{label:'Ethereum (ERC-20)',address:EVM},{label:'BSC (BEP-20)',address:EVM}]},
 {ticker:'BNB',name:'BNB',networks:[{label:'BNB Smart Chain (BEP-20)',address:EVM}]},
 {ticker:'SOL',name:'Solana',networks:[{label:'Solana',address:SOL}]},
 {ticker:'TRX',name:'Tron',networks:[{label:'Tron (TRC-20)',address:TRON}]},
];

// Simplified coin marks, drawn inline so the dialog works offline.
const MARKS:Record<string,ReactNode>={
 BTC:<><circle cx="16" cy="16" r="16" fill="#F7931A"/><text x="16" y="22.2" textAnchor="middle" fontSize="18" fontWeight="800" fill="#fff" fontFamily="Inter,Arial,sans-serif" transform="rotate(12 16 16)">₿</text></>,
 ETH:<><circle cx="16" cy="16" r="16" fill="#627EEA"/><path d="M16 5v8.1l6.9 3.1z" fill="#fff" fillOpacity=".6"/><path d="M16 5 9.1 16.2l6.9-3.1z" fill="#fff"/><path d="M16 21.5V27l6.9-9.6z" fill="#fff" fillOpacity=".6"/><path d="M16 27v-5.5l-6.9-4.1z" fill="#fff"/><path d="m16 20.3 6.9-4.1-6.9-3.1z" fill="#fff" fillOpacity=".2"/><path d="m9.1 16.2 6.9 4.1v-7.2z" fill="#fff" fillOpacity=".6"/></>,
 USDT:<><circle cx="16" cy="16" r="16" fill="#26A17B"/><path d="M17.9 17.2v0c-.1 0-.7.1-1.9.1-1 0-1.7 0-1.9-.1-3.7-.2-6.4-.8-6.4-1.6s2.7-1.4 6.4-1.6v2.5c.2 0 .9.1 1.9.1 1.2 0 1.8-.1 1.9-.1v-2.5c3.7.2 6.4.8 6.4 1.6s-2.7 1.4-6.4 1.6m0-3.4v-2.3h5.2V8H8.9v3.5h5.2v2.3c-4.2.2-7.4 1-7.4 2s3.2 1.8 7.4 2v7.3h3.8v-7.3c4.2-.2 7.4-1 7.4-2s-3.2-1.8-7.4-2" fill="#fff"/></>,
 USDC:<><circle cx="16" cy="16" r="16" fill="#2775CA"/><path d="M12.6 25.2A9.6 9.6 0 0 1 12.6 6.8M19.4 6.8a9.6 9.6 0 0 1 0 18.4" stroke="#fff" strokeWidth="1.8" fill="none" strokeLinecap="round"/><text x="16" y="21.2" textAnchor="middle" fontSize="14.5" fontWeight="800" fill="#fff" fontFamily="Inter,Arial,sans-serif">$</text></>,
 BNB:<><circle cx="16" cy="16" r="16" fill="#F3BA2F"/><path d="M12.1 14.1 16 10.2l3.9 3.9 2.3-2.3L16 5.6l-6.2 6.2zM5.6 16l2.3-2.3 2.3 2.3-2.3 2.3zm6.5 1.9L16 21.8l3.9-3.9 2.3 2.3L16 26.4l-6.2-6.2zm9.7-1.9 2.3-2.3 2.3 2.3-2.3 2.3zM18.4 16 16 13.6 14.2 15.4l-.2.2-.4.4L16 18.4z" fill="#fff"/></>,
 SOL:<><circle cx="16" cy="16" r="16" fill="#111"/><defs><linearGradient id="sol-g" x1="8" y1="24" x2="24" y2="8" gradientUnits="userSpaceOnUse"><stop stopColor="#9945FF"/><stop offset="1" stopColor="#14F195"/></linearGradient></defs><path d="M10.4 20.4a.6.6 0 0 1 .4-.2h13.4c.3 0 .4.3.2.5l-2.8 2.8a.6.6 0 0 1-.4.2H7.8c-.3 0-.4-.3-.2-.5zm0-11.6a.6.6 0 0 1 .4-.2h13.4c.3 0 .4.3.2.5l-2.8 2.8a.6.6 0 0 1-.4.2H7.8c-.3 0-.4-.3-.2-.5zm11.2 5.8a.6.6 0 0 0-.4-.2H7.8c-.3 0-.4.3-.2.5l2.8 2.8c.1.1.3.2.4.2h13.4c.3 0 .4-.3.2-.5z" fill="url(#sol-g)"/></>,
 TRX:<><circle cx="16" cy="16" r="16" fill="#EB0029"/><path d="M21.9 9.6 7.8 7l7.4 18.7 10.3-12.6zm-.3 1.4 2.2 2.1-5.9 1.1zm-5 2.9-6.2-5.2 10.2 1.9zm-.4.9-1 8.4-5.5-13.9zm.9.4 6.5-1.2-7.5 9.1z" fill="#fff"/></>,
};

function CoinMark({ticker,size=28}:{ticker:string;size?:number}){
 return <svg className="coin-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">{MARKS[ticker]}</svg>;
}

function QR({text}:{text:string}){
 const {size,path}=useMemo(()=>{
  const qr=qrcode(0,'M');qr.addData(text);qr.make();
  const n=qr.getModuleCount();let d='';
  for(let r=0;r<n;r++)for(let c=0;c<n;c++)if(qr.isDark(r,c))d+=`M${c},${r}h1v1h-1z`;
  return {size:n,path:d};
 },[text]);
 return <svg className="donate-qr" viewBox={`-2 -2 ${size+4} ${size+4}`} shapeRendering="crispEdges" role="img" aria-label={tr("QR-код адреса")}>
  <rect x={-2} y={-2} width={size+4} height={size+4} fill="#fff"/><path d={path} fill="#000"/>
 </svg>;
}

function useModal(onClose:()=>void){
 const ref=useRef<HTMLDialogElement>(null);
 useEffect(()=>{const d=ref.current;d?.showModal();return()=>d?.close()},[]);
 // stopPropagation: the coin popup is nested in the donate dialog — Esc or a backdrop click closes only the top one.
 return {ref,onCancel:(e:React.SyntheticEvent)=>{e.preventDefault();e.stopPropagation();onClose()},onClick:(e:React.MouseEvent)=>{e.stopPropagation();if(e.target===ref.current)onClose()}};
}

function CoinDialog({coin,onClose}:{coin:Coin;onClose:()=>void}){
 const modal=useModal(onClose);
 const [index,setIndex]=useState(0);
 const [copied,setCopied]=useState(false);
 const network=coin.networks[index];
 const copy=async()=>{try{await navigator.clipboard.writeText(network.address);setCopied(true);setTimeout(()=>setCopied(false),1800)}catch{}};
 return <dialog {...modal} className="coin-dialog">
  <div className="coin-head">
   <CoinMark ticker={coin.ticker} size={44}/>
   <div><h2>{tr("Отправить")} {coin.ticker}</h2><span>{coin.name}</span></div>
   <Button size="icon" variant="ghost" aria-label={tr("Закрыть")} onClick={onClose}><X size={20}/></Button>
  </div>
  {coin.networks.length>1&&<div className="segmented coin-networks" role="tablist" aria-label={tr("Сеть")}>
   {coin.networks.map((n,i)=><button key={n.label} role="tab" aria-selected={i===index} className={i===index?'chosen':''} onClick={()=>{setIndex(i);setCopied(false)}}>{n.label}</button>)}
  </div>}
  <div className="coin-qr-frame"><QR text={network.address}/></div>
  <div className="coin-address">
   <span>{tr("Адрес ·")} {network.label}</span>
   <code>{network.address}</code>
  </div>
  <Button variant="default" className={'coin-copy'+(copied?' done':'')} onClick={copy}>{copied?<Check size={16}/>:<Copy size={16}/>}{copied?tr("Адрес скопирован"):tr("Скопировать адрес")}</Button>
  <p className="coin-warning">{tr("Отправляйте")} {coin.ticker} {tr("только через сеть")} <b>{network.label}</b> {tr("— перевод через другую сеть может потеряться.")}</p>
 </dialog>;
}

export function DonateButton({onClick}:{onClick:()=>void}){
 return <button className="donate-button" onClick={onClick} title={tr("Поддержать проект донатом")}><Sparkles size={17} className="karma-spark"/><span>{tr("Карма +1")}</span></button>;
}

export function DonateDialog({onClose}:{onClose:()=>void}){
 const modal=useModal(onClose);
 const [open,setOpen]=useState(false);
 const [coin,setCoin]=useState<Coin|null>(null);
 return <dialog {...modal} className="donate-dialog">
  <div className="modal-title"><h2><Sparkles size={20} className="donate-heart"/>{tr("Удача любит круговорот")}</h2><Button size="icon" variant="ghost" aria-label={tr("Закрыть")} onClick={onClose}><X size={20}/></Button></div>
  <div className="modal-body">
   <div className="donate-message">
    <p>{tr("Ваш ролик набрал миллион? Передайте немного удачи дальше — тем, кто свой ещё ждёт.")}</p>
    <p>{tr("Говорят, удача возвращается к тем, кто делится ею первым.")}</p>
    <p>{tr("Программа бесплатная. Каждый донат — это новые функции для всех, кто ею пользуется.")}</p>
   </div>
   <button className={'donate-toggle'+(open?' open':'')} aria-expanded={open} onClick={()=>setOpen(!open)}>
    <Sparkles size={17}/><span>{tr("Поддержать проект")}</span><ChevronDown size={18} className="donate-chevron"/>
   </button>
   <div className={'coin-drawer'+(open?' open':'')} aria-hidden={!open}>
    <div className="coin-grid">
     {COINS.map((c,i)=><button key={c.ticker} className="coin-tile" style={{'--i':i} as React.CSSProperties} tabIndex={open?0:-1} onClick={()=>setCoin(c)}>
      <CoinMark ticker={c.ticker}/><span><b>{c.ticker}</b><small>{c.name}</small></span>
     </button>)}
    </div>
   </div>
   <p className="donate-thanks">{tr("Спасибо, и пусть ваши шортс и рилсы набирают миллионы!")}</p>
  </div>
  {coin&&<CoinDialog coin={coin} onClose={()=>setCoin(null)}/>}
 </dialog>;
}
