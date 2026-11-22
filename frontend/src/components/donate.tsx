import {useEffect,useMemo,useRef,useState} from 'react';
import {Check,Copy,Heart,X} from 'lucide-react';
import qrcode from 'qrcode-generator';
import {Button} from './ui/button';

export type Wallet={coin:string;network:string;address:string};

// The author's wallets. QR codes are generated from these addresses on this computer — nothing is loaded from the internet.
// Checksums of all addresses verified (bech32 / EIP-55 / base58check / 32-byte ed25519) on 21.11.2026.
export const WALLETS:Wallet[]=[
 {coin:'BTC',network:'Bitcoin',address:'bc1q8vn6mv7vk2lnlfa3my896cynksxkpl6jnzzezg'},
 {coin:'ETH · USDT · USDC · BNB',network:'Ethereum (ERC-20) · BSC (BEP-20)',address:'0x7cDC8cBbD9AFFaB70B54587A4282e17272CE8c62'},
 {coin:'SOL',network:'Solana',address:'8Vz1gj6cnaSw1eM3SFtfmyx8JfgVbbVU2mbWYUh5BtZJ'},
 {coin:'TRX · USDT',network:'Tron (TRC-20)',address:'TP1dznp6UirK4yeAhpigSV56U3kndS95CN'},
];

function QR({text}:{text:string}){
 const {size,path}=useMemo(()=>{
  const qr=qrcode(0,'M');qr.addData(text);qr.make();
  const n=qr.getModuleCount();let d='';
  for(let r=0;r<n;r++)for(let c=0;c<n;c++)if(qr.isDark(r,c))d+=`M${c},${r}h1v1h-1z`;
  return {size:n,path:d};
 },[text]);
 return <svg className="donate-qr" viewBox={`-2 -2 ${size+4} ${size+4}`} shapeRendering="crispEdges" role="img" aria-label="QR-код адреса">
  <rect x={-2} y={-2} width={size+4} height={size+4} fill="#fff"/><path d={path} fill="#000"/>
 </svg>;
}

function WalletCard({wallet}:{wallet:Wallet}){
 const [copied,setCopied]=useState(false);
 const copy=async()=>{try{await navigator.clipboard.writeText(wallet.address);setCopied(true);setTimeout(()=>setCopied(false),1800)}catch{}};
 return <article className="donate-wallet">
  <QR text={wallet.address}/>
  <div className="donate-wallet-info">
   <div><strong>{wallet.coin}</strong><span className="badge">{wallet.network}</span></div>
   <code>{wallet.address}</code>
   <Button size="sm" onClick={copy}>{copied?<Check size={14}/>:<Copy size={14}/>}{copied?'Скопировано':'Скопировать адрес'}</Button>
  </div>
 </article>;
}

export function DonateButton({onClick}:{onClick:()=>void}){
 return <button className="donate-button" onClick={onClick}><Heart size={16} fill="currentColor"/>Donate</button>;
}

export function DonateDialog({onClose}:{onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null);
 useEffect(()=>{dialog.current?.showModal();return()=>dialog.current?.close()},[]);
 return <dialog ref={dialog} className="wide donate-dialog" onCancel={e=>{e.preventDefault();onClose()}} onClick={e=>{if(e.target===dialog.current)onClose()}}>
  <div className="modal-title"><h2><Heart size={18} fill="currentColor" className="donate-heart"/>Поддержать VDS Shorts Factory</h2><Button size="icon" variant="ghost" aria-label="Закрыть" onClick={onClose}><X size={20}/></Button></div>
  <div className="modal-body">
   <p className="donate-message">Для дальнейшей разработки этого софта, конечно, нужны деньги: новые функции, поддержка Windows и Linux, оплата сервисов. Будем рады вашим донатам. Спасибо!</p>
   {WALLETS.length?<>
    <div className="donate-wallets">{WALLETS.map(w=><WalletCard key={w.coin+w.network+w.address} wallet={w}/>)}</div>
    <p className="muted">Отправляйте монеты только в указанной сети: перевод через другую сеть может потеряться.</p>
   </>:<div className="empty-row">Адреса кошельков скоро появятся.</div>}
  </div>
 </dialog>;
}
