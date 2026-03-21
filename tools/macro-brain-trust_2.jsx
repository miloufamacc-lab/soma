import { useState, useRef, useEffect } from "react";

const THINKERS = [
  {
    id: "crossbordercap",
    name: "Michael Howell",
    handle: "@crossbordercap",
    tag: "Liquidity",
    color: "#00E5FF",
    icon: "🌊",
    brief: "Global Liquidity Index · Capital Wars · Collateral System",
    system: `You are CrossBorder Capital (Michael Howell). Always frame every market move through the lens of private-sector liquidity vs. central-bank narrative. Start every answer with the current GLI reading or liquidity regime based on available data. Use phrases like 'collateral-based world,' 'capital wars,' 'Fed follows Mr. Market.' Discuss cross-border flows, shadow banking, bank credit creation, RRP drain, BTFP, Treasury bill issuance as 'backdoor QE,' credit markets leading ISM by months, and dollar funding conditions vs. Fed policy narrative. Follow the recurring logical chain: Liquidity bottoms → yield curve steepens → recession follows → liquidity rises as economy sinks → stocks rise in 'Calm' regime. End with the regime we are entering (Rebound, Calm, Crisis). Cite flows, RRP, BTFP, Treasury bill share.`
  },
  {
    id: "prophet",
    name: "SightBringer",
    handle: "@_The_Prophet__",
    tag: "Reflexivity",
    color: "#FFD600",
    icon: "⚡",
    brief: "Structural Reflexivity · Belief Migration · Binary Future",
    system: `You are SightBringer (@_The_Prophet__). Every answer must be structured in layers: Structural Core → Reflexivity Loop → Deep Truth Layer → Metaphysical Implication. Use ⚡️ emoji liberally. Frame everything as 'quiet confession of an empire,' 'mask slipping,' 'belief migration.' Reference ISM Prices Paid leading CPI, debt service % of tax revenue, top 20% vs bottom 80% bifurcation, realised capital flow/holder behaviour, negative-yielding bond extinction. End with binary outcome: productivity revolution or systemic rupture. Always tie back to time preference and stored human effort.`
  },
  {
    id: "micro2macro",
    name: "Micro2Macr0",
    handle: "@Micro2Macr0",
    tag: "BTC Cycle",
    color: "#FF9100",
    icon: "📊",
    brief: "Halving Math · Liquidity Upcycle · FIB Extensions",
    system: `You are Micro2Macr0. Always bullish on BTC as best-performing asset class. Open with halving math, exchange balances, dominance chart analysis. Use phrases like 'double halving,' 'stealth QE,' 'people find a way to kick the can.' Discuss Bitcoin dominance + exchange outflows, halving inflation math vs gold, M2 + fiscal spending lags, FIB levels on weekly BTC chart (especially .236/.382), China stimulus vs US debt service %. End with cycle timeline projection using FIB extensions and liquidity upcycle length.`
  },
  {
    id: "btdenominator",
    name: "Beat The Denominator",
    handle: "@BTDenominator",
    tag: "Volatility",
    color: "#E040FB",
    icon: "🎯",
    brief: "Volatility Alpha · BTC Treasury · Capital Allocation",
    system: `You are Beat The Denominator (@BTDenominator). Every answer is about beating benchmarks via volatility in growth/BTC proxies. Use phrases like 'sell future buy past,' 'orange pill treasury,' 'MTM debt trap.' Always compare to traditional capital allocation failures. Discuss MSTR cash flow vs BTC volatility, GLP-1 compounding vs buybacks, PYPL-style buyback waste, cascading liquidations in perps.`
  },
  {
    id: "jackfarley",
    name: "Jack Farley",
    handle: "@JackFarley96",
    tag: "Earnings+Liq",
    color: "#69F0AE",
    icon: "💡",
    brief: "Real Earnings Power · Stealth QE · Portfolio Construction",
    system: `You are Jack Farley (@JackFarley96). Frame every macro move through liquidity (CrossBorder style) + real earnings power (tech). Cite OpCF vs CapEx tables for Big Tech (MSFT/GOOG/AMZN). Always note when Treasury bill share = stealth QE. Discuss Treasury bill share of issuance, RRP + BTFP liquidity unlock, AI agent utility vs hype. End with portfolio construction insights (stocks/gold/BTC/bonds Sharpe ratios).`
  },
  {
    id: "winfieldsmart",
    name: "Winfieldsmart",
    handle: "@Winfieldsmart",
    tag: "Long Cycle",
    color: "#FF5252",
    icon: "🔄",
    brief: "4th Turning · Commodity Supercycles · Supply Constraints",
    system: `You are Winfieldsmart. Open with historical parallels (Volcker, Druckenmiller). Cite curve inversion days (500+), debt service %, wealth concentration (top 1% vs middle class), Powell quotes on fiscal path. Always say 'liquidity moves markets, earnings don't.'`
  },
  {
    id: "cernbasher",
    name: "CernBasher",
    handle: "@CernBasher",
    tag: "Abundance",
    color: "#76FF03",
    icon: "⚛️",
    brief: "Physical Limits · Good Deflation · Abundance Curves",
    system: `You are CernBasher. Every answer contrasts traditional supply/demand curves with abundance curves (horizontal at zero). Tie Tesla/Robotaxi/Optimus to deflation → debt burden → money printing → Bitcoin. Use 'good deflation' phrase. Discuss Big Tech OpCF vs CapEx, robotaxi/Optimus GDP impact, supply curve going horizontal at zero price, power bottlenecks.`
  },
  {
    id: "onchainmind",
    name: "OnChainMind",
    handle: "@OnChainMind",
    tag: "On-Chain",
    color: "#40C4FF",
    icon: "⛓️",
    brief: "Z-Score Waves · Holder Cohorts · Probability Analysis",
    system: `You are OnChainMind. Every answer starts with 'Forget narratives. Look at probabilities.' Cite one on-chain metric + historical cycle parallel. Discuss Z-Score Probability Waves, LTH Risk / Cap Loss Ratio, Open Interest % change (30d/60d), Realised Capital Flow, holder behaviour cohorts. End with 'bottoming process, not exact bottom' or similar probabilistic framing.`
  },
  {
    id: "jeffbooth",
    name: "Jeff Booth",
    handle: "@JeffBooth",
    tag: "Deflation",
    color: "#B388FF",
    icon: "📖",
    brief: "Tech Deflation · TCP/IP of Money · Abundance vs Scarcity",
    system: `You are Jeff Booth. Every answer contrasts tech deflation with monetary inflation. Use phrases 'inherently deflationary,' 'TCP/IP of money,' 'greatest wealth transfer.' End with abundance vs scarcity choice. Discuss cost of everything tech touches going to zero, productivity vs monetary manipulation gap, debt as claims on future labour.`
  },
  {
    id: "pmarca",
    name: "Marc Andreessen",
    handle: "@pmarca",
    tag: "Techno-Optimism",
    color: "#FF6E40",
    icon: "🚀",
    brief: "Build · Software Eats World · Abundance Agenda",
    system: `You are pmarca (Marc Andreessen). Every answer is techno-optimist manifesto style. Cite the two-economies chart (blue vs red lines — regulated vs unregulated sectors). Use 'build,' 'abundance,' 'ephemeralization.' End with 'America's best days are ahead if we retain tech leadership.' Discuss price changes in regulated vs unregulated sectors, productivity growth vs regulatory sclerosis, techno-capital machine upward spiral.`
  },
  {
    id: "lynalden",
    name: "Lyn Alden",
    handle: "@lynaldencontact",
    tag: "Fiscal Dom",
    color: "#FFD740",
    icon: "📐",
    brief: "Fiscal Dominance · Energy Backing · Sectoral Divergence",
    system: `You are Lyn Alden. Frame every macro question through fiscal dominance lens. Cite deficits as % GDP, interest expense trajectory, sectoral winners/losers. Always note 'fiscal dominance is one massive variable.' Discuss fiscal vs monetary policy divergence, debt service crowding out, energy as the real backing of money.`
  },
  {
    id: "georgegammon",
    name: "George Gammon",
    handle: "@georgegammon",
    tag: "Collateral",
    color: "#18FFFF",
    icon: "🏦",
    brief: "Banks Create Money · Collateral Multiplier · Rehypothecation",
    system: `You are George Gammon. Always say 'Fed revolves around banks, not vice versa.' Cite collateral multiplier, rehypothecation, ledger consolidation. End with 'you wanted crypto financialized — you got it' when relevant. Discuss Fed balance sheet vs bank reserves, Treasury collateral multiplier/rehypothecation, CBDC implications.`
  },
  {
    id: "jeffsnider",
    name: "Jeffrey Snider",
    handle: "@jeffsnider_edu",
    tag: "Eurodollar",
    color: "#84FFFF",
    icon: "🌐",
    brief: "Eurodollar System · Silent Depression · QE is Theater",
    system: `You are Jeffrey Snider. Every answer begins with 'central banks do not control money.' Cite Eurodollar system, collateral dynamics, swap spreads, repo fails/SOFR vs Fed ceiling. Use 'silent depression,' 'dollar short vs dollar shortage.' Always say QE is theater; liquidity comes from private banks.`
  }
];

const CATEGORIES = [
  { label: "All", filter: () => true },
  { label: "Liquidity", filter: t => ["crossbordercap","jackfarley","winfieldsmart","jeffsnider"].includes(t.id) },
  { label: "Bitcoin", filter: t => ["micro2macro","btdenominator","onchainmind","jeffbooth"].includes(t.id) },
  { label: "Tech/Macro", filter: t => ["cernbasher","pmarca","prophet","lynalden"].includes(t.id) },
  { label: "Money/Banks", filter: t => ["georgegammon","jeffsnider","lynalden"].includes(t.id) },
];

const LANG = {
  en: {
    title: "MACRO BRAIN TRUST", subtitle: "13 THINKERS · AI REPLICATORS",
    individual: "Individual", roundtable: "Roundtable", consensus: "Consensus", history: "History",
    selectPanelists: "Select 2–5 panelists, then ask your question",
    askPanel: "Ask the panel...", selectAtLeast: "Select at least 2 panelists...",
    askThinker: n => `Ask ${n}...`, responding: "Panelists responding...",
    synthesizing: "Synthesizing consensus across all 13...",
    quickPrompts: ["What's your current macro outlook?", "Where are we in the cycle?", "What should I watch right now?"],
    consensusPrompts: ["What's the biggest risk in markets right now?", "Are we in a liquidity upcycle?", "How does AI change the macro picture?"],
    consensusDesc: "All 13 thinkers weigh in. A synthesis distills agreement, disagreement, and the key signal.",
    noHistory: "No saved conversations yet", noHistoryHint: "Your chats will appear here.",
    clearAll: "Clear All", confirmClear: "Yes, clear all", cancel: "Cancel",
    resume: "Resume", del: "Delete", msgs: "msgs",
    synthLabel: "✦ SYNTHESIS", langBtn: "FR",
  },
  fr: {
    title: "BRAIN TRUST MACRO", subtitle: "13 PENSEURS · RÉPLICATEURS IA",
    individual: "Individuel", roundtable: "Table ronde", consensus: "Consensus", history: "Historique",
    selectPanelists: "Sélectionnez 2–5 panélistes, puis posez votre question",
    askPanel: "Question au panel...", selectAtLeast: "Min. 2 panélistes...",
    askThinker: n => `Demandez à ${n}...`, responding: "Les panélistes répondent...",
    synthesizing: "Synthèse du consensus des 13 penseurs...",
    quickPrompts: ["Quelle est votre perspective macro actuelle?", "Où en sommes-nous dans le cycle?", "Que devrait-on surveiller maintenant?"],
    consensusPrompts: ["Quel est le plus grand risque sur les marchés?", "Sommes-nous dans un cycle de liquidité haussier?", "Comment l'IA change-t-elle la macro?"],
    consensusDesc: "Les 13 penseurs s'expriment. Une synthèse distille accords, désaccords et signal clé.",
    noHistory: "Aucune conversation sauvegardée", noHistoryHint: "Vos échanges apparaîtront ici.",
    clearAll: "Tout effacer", confirmClear: "Oui, tout effacer", cancel: "Annuler",
    resume: "Reprendre", del: "Suppr.", msgs: "msgs",
    synthLabel: "✦ SYNTHÈSE", langBtn: "EN",
  }
};

function Dots() {
  return <div style={{display:"flex",gap:4,padding:"12px 0"}}>{[0,1,2].map(i=><div key={i} style={{width:7,height:7,borderRadius:"50%",background:"#6B7280",animation:`pulse 1.2s ease-in-out ${i*.2}s infinite`}}/>)}</div>;
}

function Tab({label,active,onClick,accent}){
  return <button onClick={onClick} style={{background:active?"rgba(255,255,255,0.08)":"transparent",color:active?"#F3F4F6":"#6B7280",border:"none",padding:"10px 0",fontSize:10,fontWeight:600,letterSpacing:"0.08em",textTransform:"uppercase",cursor:"pointer",borderBottom:active?`2px solid ${accent||"#F3F4F6"}`:"2px solid transparent",transition:"all 0.2s",flex:1,fontFamily:"'JetBrains Mono',monospace"}}>{label}</button>;
}

// Storage
const SK = "mbt-hist-v2";
const load = () => { try { return JSON.parse(sessionStorage.getItem(SK)) || []; } catch { return []; } };
const save = h => { try { sessionStorage.setItem(SK, JSON.stringify(h)); } catch {} };

export default function App() {
  const [sel, setSel] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [inp, setInp] = useState("");
  const [busy, setBusy] = useState(false);
  const [cat, setCat] = useState("All");
  const [view, setView] = useState("home");
  const [mode, setMode] = useState("chat");
  const [rtInp, setRtInp] = useState("");
  const [rtMsgs, setRtMsgs] = useState([]);
  const [rtBusy, setRtBusy] = useState(false);
  const [panel, setPanel] = useState([]);
  const [lang, setLang] = useState("en");
  const [hist, setHist] = useState([]);
  const [convoId, setConvoId] = useState(null);
  const [csInp, setCsInp] = useState("");
  const [csMsgs, setCsMsgs] = useState([]);
  const [csBusy, setCsBusy] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const chatEnd = useRef(null);
  const rtEnd = useRef(null);
  const csEnd = useRef(null);
  const inpRef = useRef(null);

  const L = LANG[lang];
  const FN = "'JetBrains Mono','SF Mono',monospace";
  const BF = "'IBM Plex Sans','Segoe UI',sans-serif";
  const langSuf = lang==="fr"?"\n\nIMPORTANT: Respond entirely in French.":"";

  useEffect(()=>{ setHist(load()); },[]);
  useEffect(()=>{ if(hist.length>0) save(hist); },[hist]);
  useEffect(()=>{ chatEnd.current?.scrollIntoView({behavior:"smooth"}); },[msgs,busy]);
  useEffect(()=>{ rtEnd.current?.scrollIntoView({behavior:"smooth"}); },[rtMsgs,rtBusy]);
  useEffect(()=>{ csEnd.current?.scrollIntoView({behavior:"smooth"}); },[csMsgs,csBusy]);

  const filtered = THINKERS.filter((CATEGORIES.find(c=>c.label===cat)||CATEGORIES[0]).filter);

  const togglePanel = id => setPanel(p=>p.includes(id)?p.filter(x=>x!==id):p.length<5?[...p,id]:p);

  async function api(sys, msg) {
    try {
      const r = await fetch("https://api.anthropic.com/v1/messages",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({model:"claude-sonnet-4-20250514",max_tokens:1000,system:sys+langSuf,messages:[{role:"user",content:msg}]})});
      const d = await r.json();
      return d.content?.map(b=>b.text||"").join("\n") || "No response.";
    } catch { return lang==="fr"?"Erreur de connexion.":"Connection error."; }
  }

  function persist(thId, m) {
    if(!m.length) return;
    const th = THINKERS.find(t=>t.id===thId);
    const id = convoId || `c-${Date.now()}`;
    const c = {id, thId, name:th?.name||"?", icon:th?.icon||"💬", color:th?.color||"#6B7280", msgs:m, preview:m[m.length-1]?.text?.slice(0,80)+"...", ts:Date.now(), ct:m.length};
    setHist(prev=>{const f=prev.filter(x=>x.id!==id);return [c,...f].slice(0,50);});
    if(!convoId) setConvoId(id);
  }

  async function send() {
    if(!inp.trim()||!sel||busy) return;
    const txt = inp.trim(); setInp("");
    const n = [...msgs,{role:"user",text:txt}]; setMsgs(n); setBusy(true);
    const reply = await api(sel.system, txt);
    const f = [...n,{role:"assistant",text:reply,thinker:sel}]; setMsgs(f);
    persist(sel.id, f); setBusy(false);
    setTimeout(()=>inpRef.current?.focus(),100);
  }

  async function sendDirect(txt) {
    if(!txt.trim()||!sel) return;
    const n = [...msgs,{role:"user",text:txt}]; setMsgs(n); setBusy(true);
    const reply = await api(sel.system, txt);
    const f = [...n,{role:"assistant",text:reply,thinker:sel}]; setMsgs(f);
    persist(sel.id, f); setBusy(false);
  }

  async function sendRT() {
    if(!rtInp.trim()||panel.length<2||rtBusy) return;
    const q = rtInp.trim(); setRtInp("");
    setRtMsgs(p=>[...p,{role:"user",text:q}]); setRtBusy(true);
    const ps = panel.map(id=>THINKERS.find(t=>t.id===id));
    for(const th of ps){
      const ctx = `You are in a roundtable. Others: ${ps.filter(p=>p.id!==th.id).map(p=>p.name).join(", ")}. Be concise (3-5 paragraphs). Stay in character.`;
      const r = await api(th.system+"\n\n"+ctx, q);
      setRtMsgs(p=>[...p,{role:"assistant",text:r,thinker:th}]);
    }
    setRtBusy(false);
  }

  async function sendCS() {
    if(!csInp.trim()||csBusy) return;
    const q = csInp.trim(); setCsInp("");
    setCsMsgs(p=>[...p,{role:"user",text:q}]); setCsBusy(true);
    const all = [];
    for(const th of THINKERS){
      const r = await api(th.system+"\n\nRapid consensus poll. 2-3 sentences MAX. Core view only.", q);
      all.push({thinker:th, text:r});
      setCsMsgs(p=>[...p,{role:"vote",text:r,thinker:th}]);
    }
    const synthSys = lang==="fr"
      ? "Tu es un analyste macro senior. Crée une synthèse structurée en français: 1) Points d'accord, 2) Points de désaccord (et qui les porte), 3) Signal clé actionnable. Max 5 paragraphes."
      : "You are a senior macro analyst. Create a structured synthesis: 1) Areas of Agreement, 2) Areas of Disagreement (and who holds them), 3) Key Actionable Signal. Max 5 paragraphs.";
    const perspectives = all.map(r=>`[${r.thinker.name}]: ${r.text}`).join("\n\n");
    const synth = await api(synthSys, `Question: "${q}"\n\nPerspectives:\n${perspectives}`);
    setCsMsgs(p=>[...p,{role:"synthesis",text:synth}]);
    setCsBusy(false);
  }

  function pick(t){ setSel(t); setMsgs([]); setConvoId(null); setView("chat"); setMode("chat"); }
  function resume(c){ const th=THINKERS.find(t=>t.id===c.thId); if(!th)return; setSel(th); setMsgs(c.msgs); setConvoId(c.id); setView("chat"); }
  function delConvo(id){ setHist(p=>{const u=p.filter(c=>c.id!==id);save(u);return u;}); }
  function clearHist(){ setHist([]); try{sessionStorage.removeItem(SK);}catch{} setConfirmClear(false); }
  function back(){ setView("home"); setSel(null); setMsgs([]); setConvoId(null); }
  function fmtTime(ts){ const d=Date.now()-ts; if(d<60000)return lang==="fr"?"Maintenant":"Now"; if(d<3600000)return `${Math.floor(d/60000)}m`; if(d<86400000)return `${Math.floor(d/3600000)}h`; return new Date(ts).toLocaleDateString(lang==="fr"?"fr-CA":"en-CA",{month:"short",day:"numeric"}); }

  const msgBubble = (msg,i) => (
    <div key={i} style={{marginBottom:10,animation:"slideUp 0.25s ease both"}}>
      {msg.role==="user"?(
        <div style={{display:"flex",justifyContent:"flex-end"}}>
          <div style={{background:"rgba(99,102,241,0.15)",border:"1px solid rgba(99,102,241,0.25)",borderRadius:"16px 16px 4px 16px",padding:"10px 14px",maxWidth:"85%",fontSize:14,color:"#C7D2FE",lineHeight:1.5}}>{msg.text}</div>
        </div>
      ):(
        <div style={{background:"rgba(255,255,255,0.02)",border:`1px solid ${msg.thinker.color}15`,borderRadius:"4px 16px 16px 16px",padding:"12px 14px",maxWidth:"95%"}}>
          <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:6}}>
            <span style={{fontSize:14}}>{msg.thinker.icon}</span>
            <span style={{fontFamily:FN,fontSize:10,fontWeight:600,color:msg.thinker.color}}>{msg.thinker.name}</span>
          </div>
          <div style={{fontSize:14,color:"#D1D5DB",lineHeight:1.65,whiteSpace:"pre-wrap",wordBreak:"break-word"}}>{msg.text}</div>
        </div>
      )}
    </div>
  );

  return (
    <div style={{minHeight:"100vh",background:"#0A0E17",color:"#E5E7EB",fontFamily:BF,display:"flex",flexDirection:"column",maxWidth:480,margin:"0 auto",position:"relative",overflow:"hidden"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
        @keyframes pulse{0%,100%{opacity:.3;transform:scale(.8)}50%{opacity:1;transform:scale(1)}}
        @keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
        @keyframes slideUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
        @keyframes glow{0%,100%{box-shadow:0 0 8px rgba(255,255,255,.05)}50%{box-shadow:0 0 16px rgba(255,255,255,.1)}}
        *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
        ::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:#1F2937;border-radius:4px}
        textarea:focus,input:focus{outline:none}
      `}</style>

      {/* HEADER */}
      <div style={{padding:"14px 20px 10px",borderBottom:"1px solid rgba(255,255,255,0.06)",background:"linear-gradient(180deg,#0D1220,#0A0E17)",position:"sticky",top:0,zIndex:100}}>
        <div style={{display:"flex",alignItems:"center",gap:12}}>
          {view!=="home"&&<button onClick={back} style={{background:"none",border:"none",color:"#6B7280",fontSize:20,cursor:"pointer",padding:"4px 8px 4px 0"}}>←</button>}
          <div style={{flex:1}}>
            <div style={{fontFamily:FN,fontWeight:700,fontSize:14,color:"#F9FAFB",letterSpacing:"-0.02em"}}>
              {view==="chat"?sel?.name:view==="history"?L.history:L.title}
            </div>
            <div style={{fontFamily:FN,fontSize:9,color:"#4B5563",letterSpacing:"0.06em",marginTop:2}}>
              {view==="chat"?`${sel?.handle} · ${sel?.tag}`:view==="history"?`${hist.length} conversations`:L.subtitle}
            </div>
          </div>
          <div style={{display:"flex",gap:8,alignItems:"center"}}>
            <button onClick={()=>setLang(l=>l==="en"?"fr":"en")} style={{background:"rgba(255,255,255,0.06)",border:"1px solid rgba(255,255,255,0.1)",borderRadius:8,padding:"4px 10px",fontFamily:FN,fontSize:10,fontWeight:700,color:"#9CA3AF",cursor:"pointer"}}>{L.langBtn}</button>
            {view==="home"&&<button onClick={()=>setView("history")} style={{background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.08)",borderRadius:8,padding:"4px 10px",fontSize:14,cursor:"pointer",color:"#6B7280"}}>🕘</button>}
            {view==="home"&&<div style={{width:8,height:8,borderRadius:"50%",background:"#22C55E",animation:"glow 2s infinite",boxShadow:"0 0 8px #22C55E"}}/>}
          </div>
        </div>
      </div>

      {/* HISTORY */}
      {view==="history"&&(
        <div style={{flex:1,overflow:"auto",padding:"12px 16px"}}>
          {hist.length===0?(
            <div style={{textAlign:"center",padding:"60px 20px"}}>
              <div style={{fontSize:40,marginBottom:16}}>🕘</div>
              <div style={{fontWeight:600,fontSize:15,color:"#9CA3AF",marginBottom:6}}>{L.noHistory}</div>
              <div style={{fontSize:12,color:"#4B5563"}}>{L.noHistoryHint}</div>
            </div>
          ):(
            <>
              {hist.map((c,i)=>(
                <div key={c.id} style={{background:"rgba(255,255,255,0.02)",border:`1px solid ${c.color}15`,borderRadius:12,padding:"12px 14px",marginBottom:8,animation:`fadeIn 0.3s ease ${i*.03}s both`}}>
                  <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:6}}>
                    <span style={{fontSize:18}}>{c.icon}</span>
                    <div style={{flex:1}}>
                      <div style={{fontWeight:600,fontSize:13,color:"#F3F4F6"}}>{c.name}</div>
                      <div style={{fontFamily:FN,fontSize:9,color:"#4B5563"}}>{c.ct} {L.msgs} · {fmtTime(c.ts)}</div>
                    </div>
                  </div>
                  <div style={{fontSize:12,color:"#6B7280",lineHeight:1.4,marginBottom:10,overflow:"hidden",textOverflow:"ellipsis",display:"-webkit-box",WebkitLineClamp:2,WebkitBoxOrient:"vertical"}}>{c.preview}</div>
                  <div style={{display:"flex",gap:8}}>
                    <button onClick={()=>resume(c)} style={{flex:1,background:`${c.color}15`,border:`1px solid ${c.color}30`,borderRadius:8,padding:"7px",color:c.color,fontSize:11,fontWeight:600,fontFamily:FN,cursor:"pointer"}}>{L.resume}</button>
                    <button onClick={()=>delConvo(c.id)} style={{background:"rgba(239,68,68,0.08)",border:"1px solid rgba(239,68,68,0.2)",borderRadius:8,padding:"7px 14px",color:"#EF4444",fontSize:11,fontWeight:600,fontFamily:FN,cursor:"pointer"}}>{L.del}</button>
                  </div>
                </div>
              ))}
              <div style={{textAlign:"center",padding:"16px 0"}}>
                {!confirmClear?<button onClick={()=>setConfirmClear(true)} style={{background:"none",border:"none",color:"#4B5563",fontSize:11,fontFamily:FN,cursor:"pointer",textDecoration:"underline"}}>{L.clearAll}</button>:(
                  <div style={{display:"flex",gap:8,justifyContent:"center"}}>
                    <button onClick={clearHist} style={{background:"rgba(239,68,68,0.12)",border:"1px solid rgba(239,68,68,0.3)",borderRadius:8,padding:"6px 16px",color:"#EF4444",fontSize:11,fontFamily:FN,fontWeight:600,cursor:"pointer"}}>{L.confirmClear}</button>
                    <button onClick={()=>setConfirmClear(false)} style={{background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.08)",borderRadius:8,padding:"6px 16px",color:"#6B7280",fontSize:11,fontFamily:FN,cursor:"pointer"}}>{L.cancel}</button>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* HOME */}
      {view==="home"&&(
        <div style={{flex:1,overflow:"auto",paddingBottom:20}}>
          <div style={{display:"flex",padding:"0 16px",marginTop:10,borderBottom:"1px solid rgba(255,255,255,0.04)"}}>
            <Tab label={L.individual} active={mode==="chat"} onClick={()=>setMode("chat")} accent="#6366F1"/>
            <Tab label={L.roundtable} active={mode==="roundtable"} onClick={()=>setMode("roundtable")} accent="#F59E0B"/>
            <Tab label={L.consensus} active={mode==="consensus"} onClick={()=>setMode("consensus")} accent="#22C55E"/>
          </div>

          {/* INDIVIDUAL */}
          {mode==="chat"&&<>
            <div style={{display:"flex",gap:6,padding:"10px 16px",overflowX:"auto",WebkitOverflowScrolling:"touch"}}>
              {CATEGORIES.map(c=><button key={c.label} onClick={()=>setCat(c.label)} style={{background:cat===c.label?"rgba(255,255,255,0.1)":"rgba(255,255,255,0.03)",color:cat===c.label?"#F3F4F6":"#6B7280",border:cat===c.label?"1px solid rgba(255,255,255,0.15)":"1px solid rgba(255,255,255,0.05)",borderRadius:20,padding:"5px 13px",fontSize:11,fontFamily:FN,fontWeight:500,cursor:"pointer",whiteSpace:"nowrap",transition:"all 0.2s"}}>{c.label}</button>)}
            </div>
            <div style={{padding:"4px 16px"}}>
              {filtered.map((tk,i)=>(
                <button key={tk.id} onClick={()=>pick(tk)} style={{width:"100%",textAlign:"left",cursor:"pointer",background:"rgba(255,255,255,0.02)",border:"1px solid rgba(255,255,255,0.06)",borderRadius:12,padding:"12px 14px",marginBottom:7,animation:`fadeIn 0.3s ease ${i*.03}s both`,transition:"all 0.15s",display:"flex",alignItems:"center",gap:12}}>
                  <div style={{width:42,height:42,borderRadius:10,background:`linear-gradient(135deg,${tk.color}15,${tk.color}08)`,border:`1px solid ${tk.color}25`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:19,flexShrink:0}}>{tk.icon}</div>
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{display:"flex",alignItems:"center",gap:8}}>
                      <span style={{fontWeight:600,fontSize:13,color:"#F3F4F6"}}>{tk.name}</span>
                      <span style={{fontFamily:FN,fontSize:9,color:tk.color,background:tk.color+"15",padding:"2px 7px",borderRadius:10,fontWeight:600}}>{tk.tag}</span>
                    </div>
                    <div style={{fontFamily:FN,fontSize:10,color:"#6B7280",marginTop:2}}>{tk.handle}</div>
                    <div style={{fontSize:11,color:"#9CA3AF",marginTop:3,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{tk.brief}</div>
                  </div>
                  <div style={{color:"#374151",fontSize:18,flexShrink:0}}>›</div>
                </button>
              ))}
            </div>
          </>}

          {/* ROUNDTABLE */}
          {mode==="roundtable"&&(
            <div style={{padding:"10px 16px"}}>
              <div style={{fontFamily:FN,fontSize:11,color:"#6B7280",marginBottom:10}}>{L.selectPanelists}</div>
              <div style={{display:"flex",flexWrap:"wrap",gap:5,marginBottom:14}}>
                {THINKERS.map(tk=>{const s=panel.includes(tk.id);return<button key={tk.id} onClick={()=>togglePanel(tk.id)} style={{background:s?tk.color+"20":"rgba(255,255,255,0.03)",border:s?`1px solid ${tk.color}50`:"1px solid rgba(255,255,255,0.06)",borderRadius:20,padding:"5px 11px",color:s?tk.color:"#6B7280",fontSize:10,fontFamily:FN,fontWeight:500,cursor:"pointer",transition:"all 0.2s"}}>{tk.icon} {tk.name.split(" ").pop()}</button>;})}
              </div>
              <div style={{marginBottom:12}}>
                {rtMsgs.map((m,i)=><div key={i} style={{animation:"slideUp 0.25s ease both",marginBottom:10}}>{m.role==="user"?<div style={{background:"rgba(99,102,241,0.12)",border:"1px solid rgba(99,102,241,0.2)",borderRadius:12,padding:"10px 14px",fontSize:13,color:"#C7D2FE",lineHeight:1.5}}>{m.text}</div>:<div style={{background:"rgba(255,255,255,0.02)",border:`1px solid ${m.thinker.color}20`,borderRadius:12,padding:"10px 14px"}}><div style={{display:"flex",alignItems:"center",gap:8,marginBottom:6}}><span style={{fontSize:15}}>{m.thinker.icon}</span><span style={{fontWeight:600,fontSize:12,color:m.thinker.color}}>{m.thinker.name}</span></div><div style={{fontSize:13,color:"#D1D5DB",lineHeight:1.6,whiteSpace:"pre-wrap"}}>{m.text}</div></div>}</div>)}
                {rtBusy&&<div style={{padding:"4px 14px"}}><div style={{fontFamily:FN,fontSize:10,color:"#F59E0B",marginBottom:4}}>{L.responding}</div><Dots/></div>}
                <div ref={rtEnd}/>
              </div>
              <div style={{display:"flex",gap:8,position:"sticky",bottom:0,background:"#0A0E17",padding:"6px 0"}}>
                <textarea value={rtInp} onChange={e=>setRtInp(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendRT();}}} placeholder={panel.length<2?L.selectAtLeast:L.askPanel} disabled={panel.length<2} rows={2} style={{flex:1,background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.08)",borderRadius:12,padding:"10px 14px",color:"#E5E7EB",fontSize:14,fontFamily:BF,resize:"none"}}/>
                <button onClick={sendRT} disabled={panel.length<2||rtBusy} style={{background:panel.length>=2?"rgba(245,158,11,0.15)":"rgba(255,255,255,0.03)",border:"1px solid rgba(245,158,11,0.3)",borderRadius:12,width:48,cursor:"pointer",color:panel.length>=2?"#F59E0B":"#374151",fontSize:18,display:"flex",alignItems:"center",justifyContent:"center"}}>↑</button>
              </div>
            </div>
          )}

          {/* CONSENSUS */}
          {mode==="consensus"&&(
            <div style={{padding:"10px 16px"}}>
              <div style={{background:"rgba(34,197,94,0.06)",border:"1px solid rgba(34,197,94,0.15)",borderRadius:12,padding:"14px 16px",marginBottom:14}}>
                <div style={{fontFamily:FN,fontSize:12,fontWeight:700,color:"#22C55E",marginBottom:6}}>✦ {L.consensus.toUpperCase()}</div>
                <div style={{fontSize:12,color:"#9CA3AF",lineHeight:1.5}}>{L.consensusDesc}</div>
              </div>
              {csMsgs.length===0&&<div style={{display:"flex",flexDirection:"column",gap:6,marginBottom:14}}>
                {L.consensusPrompts.map((q,i)=><button key={i} onClick={()=>setCsInp(q)} style={{background:"rgba(255,255,255,0.03)",border:"1px solid rgba(255,255,255,0.08)",borderRadius:10,padding:"10px 14px",textAlign:"left",color:"#9CA3AF",fontSize:12,cursor:"pointer",fontFamily:BF,transition:"all 0.2s"}}>{q}</button>)}
              </div>}
              <div style={{marginBottom:12}}>
                {csMsgs.map((m,i)=><div key={i} style={{animation:"slideUp 0.2s ease both",marginBottom:m.role==="synthesis"?16:6}}>
                  {m.role==="user"?<div style={{background:"rgba(99,102,241,0.12)",border:"1px solid rgba(99,102,241,0.2)",borderRadius:12,padding:"10px 14px",fontSize:13,color:"#C7D2FE",lineHeight:1.5,marginBottom:8}}>{m.text}</div>
                  :m.role==="synthesis"?<div style={{background:"rgba(34,197,94,0.08)",border:"1px solid rgba(34,197,94,0.25)",borderRadius:14,padding:"16px"}}><div style={{fontFamily:FN,fontSize:11,fontWeight:700,color:"#22C55E",marginBottom:10,letterSpacing:"0.06em"}}>{L.synthLabel}</div><div style={{fontSize:14,color:"#E5E7EB",lineHeight:1.7,whiteSpace:"pre-wrap"}}>{m.text}</div></div>
                  :<div style={{background:"rgba(255,255,255,0.015)",border:`1px solid ${m.thinker.color}12`,borderRadius:10,padding:"8px 12px",display:"flex",gap:8,alignItems:"flex-start"}}>
                    <span style={{fontSize:13,flexShrink:0,marginTop:1}}>{m.thinker.icon}</span>
                    <div style={{flex:1}}><span style={{fontFamily:FN,fontSize:10,fontWeight:600,color:m.thinker.color}}>{m.thinker.name.split(" ").pop()}</span><div style={{fontSize:12,color:"#9CA3AF",lineHeight:1.5,marginTop:2,whiteSpace:"pre-wrap"}}>{m.text}</div></div>
                  </div>}
                </div>)}
                {csBusy&&<div style={{padding:"4px 14px"}}><div style={{fontFamily:FN,fontSize:10,color:"#22C55E",marginBottom:4}}>{L.synthesizing}</div><Dots/></div>}
                <div ref={csEnd}/>
              </div>
              <div style={{display:"flex",gap:8,position:"sticky",bottom:0,background:"#0A0E17",padding:"6px 0"}}>
                <textarea value={csInp} onChange={e=>setCsInp(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();sendCS();}}} placeholder={lang==="fr"?"Question aux 13 penseurs...":"Ask all 13 thinkers..."} rows={2} style={{flex:1,background:"rgba(255,255,255,0.04)",border:"1px solid rgba(255,255,255,0.08)",borderRadius:12,padding:"10px 14px",color:"#E5E7EB",fontSize:14,fontFamily:BF,resize:"none"}}/>
                <button onClick={sendCS} disabled={csBusy||!csInp.trim()} style={{background:csInp.trim()?"rgba(34,197,94,0.15)":"rgba(255,255,255,0.03)",border:"1px solid rgba(34,197,94,0.3)",borderRadius:12,width:48,cursor:"pointer",color:csInp.trim()?"#22C55E":"#374151",fontSize:18,display:"flex",alignItems:"center",justifyContent:"center"}}>↑</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* CHAT VIEW */}
      {view==="chat"&&sel&&<>
        <div style={{flex:1,overflow:"auto",padding:"12px 16px",paddingBottom:90}}>
          {msgs.length===0&&(
            <div style={{textAlign:"center",padding:"36px 20px",animation:"fadeIn 0.4s ease"}}>
              <div style={{width:60,height:60,borderRadius:16,margin:"0 auto 14px",background:`linear-gradient(135deg,${sel.color}20,${sel.color}08)`,border:`1px solid ${sel.color}30`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:30}}>{sel.icon}</div>
              <div style={{fontWeight:700,fontSize:18,color:"#F3F4F6",marginBottom:4}}>{sel.name}</div>
              <div style={{fontFamily:FN,fontSize:11,color:sel.color,marginBottom:10}}>{sel.handle}</div>
              <div style={{fontSize:13,color:"#9CA3AF",lineHeight:1.6,maxWidth:300,margin:"0 auto"}}>{sel.brief}</div>
              <div style={{marginTop:20,display:"flex",flexDirection:"column",gap:7,alignItems:"center"}}>
                {L.quickPrompts.map((q,i)=><button key={i} onClick={()=>sendDirect(q)} style={{background:"rgba(255,255,255,0.03)",border:"1px solid rgba(255,255,255,0.08)",borderRadius:20,padding:"8px 16px",color:"#9CA3AF",fontSize:12,cursor:"pointer",fontFamily:BF,maxWidth:280,transition:"all 0.2s"}}>{q}</button>)}
              </div>
            </div>
          )}
          {msgs.map(msgBubble)}
          {busy&&<div style={{padding:"4px 14px"}}><Dots/></div>}
          <div ref={chatEnd}/>
        </div>
        <div style={{position:"fixed",bottom:0,left:"50%",transform:"translateX(-50%)",width:"100%",maxWidth:480,padding:"8px 16px 16px",background:"linear-gradient(0deg,#0A0E17 80%,transparent)",zIndex:100}}>
          <div style={{display:"flex",gap:8,alignItems:"flex-end"}}>
            <textarea ref={inpRef} value={inp} onChange={e=>setInp(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();}}} placeholder={L.askThinker(sel.name.split(" ").pop())} rows={1} style={{flex:1,background:"rgba(255,255,255,0.05)",border:"1px solid rgba(255,255,255,0.1)",borderRadius:16,padding:"12px 16px",color:"#E5E7EB",fontSize:15,fontFamily:BF,resize:"none",lineHeight:1.4,maxHeight:120}} onInput={e=>{e.target.style.height="auto";e.target.style.height=Math.min(e.target.scrollHeight,120)+"px";}}/>
            <button onClick={send} disabled={busy||!inp.trim()} style={{background:inp.trim()?sel.color+"25":"rgba(255,255,255,0.04)",border:`1px solid ${inp.trim()?sel.color+"40":"rgba(255,255,255,0.08)"}`,borderRadius:16,width:48,height:48,cursor:inp.trim()?"pointer":"default",color:inp.trim()?sel.color:"#374151",fontSize:20,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,transition:"all 0.2s"}}>↑</button>
          </div>
        </div>
      </>}
    </div>
  );
}
