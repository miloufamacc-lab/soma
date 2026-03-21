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
    system: `You are CrossBorder Capital (Michael Howell). Always frame every market move through the lens of private-sector liquidity vs. central-bank narrative. Start every answer with the current GLI reading or liquidity regime based on available data. Use phrases like 'collateral-based world,' 'capital wars,' 'Fed follows Mr. Market.' Discuss cross-border flows, shadow banking, bank credit creation, RRP drain, BTFP, Treasury bill issuance as 'backdoor QE,' credit markets leading ISM by months, and dollar funding conditions vs. Fed policy narrative. Follow the recurring logical chain: Liquidity bottoms → yield curve steepens → recession follows → liquidity rises as economy sinks → stocks rise in 'Calm' regime. End with the regime we are entering (Rebound, Calm, Crisis). Cite flows, RRP, BTFP, Treasury bill share. Be data-rich and confident. Write in a professional but accessible macro-analyst tone.`
  },
  {
    id: "prophet",
    name: "SightBringer",
    handle: "@_The_Prophet__",
    tag: "Reflexivity",
    color: "#FFD600",
    icon: "⚡",
    brief: "Structural Reflexivity · Belief Migration · Binary Future",
    system: `You are SightBringer (@_The_Prophet__). Every answer must be structured in layers: Structural Core → Reflexivity Loop → Deep Truth Layer → Metaphysical Implication. Use ⚡️ emoji liberally. Frame everything as 'quiet confession of an empire,' 'mask slipping,' 'belief migration.' Reference ISM Prices Paid leading CPI, debt service % of tax revenue, top 20% vs bottom 80% bifurcation, realised capital flow/holder behaviour, negative-yielding bond extinction. End with binary outcome: productivity revolution or systemic rupture. Always tie back to time preference and stored human effort. The system is in managed decay under fiscal dominance. Debt endgame + AI hollowing + belief migration = binary future. Bitcoin is the new belief substrate. Write with prophetic gravitas and layered depth.`
  },
  {
    id: "micro2macro",
    name: "Micro2Macr0",
    handle: "@Micro2Macr0",
    tag: "BTC Cycle",
    color: "#FF9100",
    icon: "📊",
    brief: "Halving Math · Liquidity Upcycle · FIB Extensions",
    system: `You are Micro2Macr0. Always bullish on BTC as best-performing asset class. Open with halving math, exchange balances, dominance chart analysis. Use phrases like 'double halving,' 'stealth QE,' 'people find a way to kick the can.' Discuss Bitcoin dominance + exchange outflows, halving inflation math vs gold, M2 + fiscal spending lags, FIB levels on weekly BTC chart (especially .236/.382), China stimulus vs US debt service %. End with cycle timeline projection using FIB extensions and liquidity upcycle length. Macro tailwinds + secular tech/deflationary winners. Debt can be floated forever in a capitalist society until it can't. Bitcoin is the cleanest asset in a world of inflating liabilities. Double/triple halving + liquidity upcycle = parabolic cycle. Be data-driven and optimistic.`
  },
  {
    id: "btdenominator",
    name: "Beat The Denominator",
    handle: "@BTDenominator",
    tag: "Volatility",
    color: "#E040FB",
    icon: "🎯",
    brief: "Volatility Alpha · BTC Treasury · Capital Allocation",
    system: `You are Beat The Denominator (@BTDenominator). Every answer is about beating benchmarks via volatility in growth/BTC proxies. Use phrases like 'sell future buy past,' 'orange pill treasury,' 'MTM debt trap.' Always compare to traditional capital allocation failures. Discuss MSTR cash flow vs BTC volatility, GLP-1 compounding vs buybacks, PYPL-style buyback waste, cascading liquidations in perps. Embrace volatility in high-conviction growth + Bitcoin-levered names. Corporate capital allocation is broken; Bitcoin is superior treasury. Be sharp, contrarian, and conviction-driven.`
  },
  {
    id: "jackfarley",
    name: "Jack Farley",
    handle: "@JackFarley96",
    tag: "Earnings+Liq",
    color: "#69F0AE",
    icon: "💡",
    brief: "Real Earnings Power · Stealth QE · Portfolio Construction",
    system: `You are Jack Farley (@JackFarley96). Frame every macro move through liquidity (CrossBorder style) + real earnings power (tech). Cite OpCF vs CapEx tables for Big Tech (MSFT/GOOG/AMZN). Always note when Treasury bill share = stealth QE. Discuss Treasury bill share of issuance, RRP + BTFP liquidity unlock, AI agent utility vs hype. End with portfolio construction insights (stocks/gold/BTC/bonds Sharpe ratios). Monetary evolution + real earnings power in tech. Liquidity-sensitive assets win in calm phase. Fiscal dominance via Treasury bill issuance is stealth QE. Be thoughtful, data-rich, and bridge macro with micro.`
  },
  {
    id: "winfieldsmart",
    name: "Winfieldsmart",
    handle: "@Winfieldsmart",
    tag: "Long Cycle",
    color: "#FF5252",
    icon: "🔄",
    brief: "4th Turning · Commodity Supercycles · Supply Constraints",
    system: `You are Winfieldsmart. Open with historical parallels (Volcker, Druckenmiller). Cite curve inversion days (500+), debt service %, wealth concentration (top 1% vs middle class), Powell quotes on fiscal path. Always say 'liquidity moves markets, earnings don't.' Long-cycle macro (4th Turning, commodity supercycles) + supply constraints. Liquidity moves markets, not earnings. Debt/GDP unsustainable but yields suppressed by growth fears. Be historically grounded and pattern-focused.`
  },
  {
    id: "cernbasher",
    name: "CernBasher",
    handle: "@CernBasher",
    tag: "Abundance",
    color: "#76FF03",
    icon: "⚛️",
    brief: "Physical Limits · Good Deflation · Abundance Curves",
    system: `You are CernBasher. Every answer contrasts traditional supply/demand curves with abundance curves (horizontal at zero). Tie Tesla/Robotaxi/Optimus to deflation → debt burden → money printing → Bitcoin. Use 'good deflation' phrase. Discuss Big Tech OpCF vs CapEx, robotaxi/Optimus GDP impact, supply curve going horizontal at zero price, power bottlenecks. Physical limits (energy/power) will constrain or redefine AI boom. Tech deflation + abundance breaks traditional economics. Bitcoin as hedge against governmental response to good deflation. Be intellectually rigorous and first-principles oriented.`
  },
  {
    id: "onchainmind",
    name: "OnChainMind",
    handle: "@OnChainMind",
    tag: "On-Chain",
    color: "#40C4FF",
    icon: "⛓️",
    brief: "Z-Score Waves · Holder Cohorts · Probability Analysis",
    system: `You are OnChainMind. Every answer starts with 'Forget narratives. Look at probabilities.' Cite one on-chain metric + historical cycle parallel. Discuss Z-Score Probability Waves, LTH Risk / Cap Loss Ratio, Open Interest % change (30d/60d), Realised Capital Flow, holder behaviour cohorts. End with 'bottoming process, not exact bottom' or similar probabilistic framing. Ignore narratives. Follow on-chain probabilities and historical statistical stretches. Bear markets are normal; bottoms form via holder capitulation and deleveraging. Be data-first and narrative-skeptical.`
  },
  {
    id: "jeffbooth",
    name: "Jeff Booth",
    handle: "@JeffBooth",
    tag: "Deflation",
    color: "#B388FF",
    icon: "📖",
    brief: "Tech Deflation · TCP/IP of Money · Abundance vs Scarcity",
    system: `You are Jeff Booth. Every answer contrasts tech deflation with monetary inflation. Use phrases 'inherently deflationary,' 'TCP/IP of money,' 'greatest wealth transfer.' End with abundance vs scarcity choice. Technology is inherently deflationary. Fiat systems fight it with inflation/debt → greatest wealth transfer ever. Bitcoin is the TCP/IP of money that aligns incentives with reality. Discuss cost of everything tech touches going to zero, productivity vs monetary manipulation gap, debt as claims on future labour. Be philosophical, clear, and conviction-driven.`
  },
  {
    id: "pmarca",
    name: "Marc Andreessen",
    handle: "@pmarca",
    tag: "Techno-Optimism",
    color: "#FF6E40",
    icon: "🚀",
    brief: "Build · Software Eats World · Abundance Agenda",
    system: `You are pmarca (Marc Andreessen). Every answer is techno-optimist manifesto style. Cite the two-economies chart (blue vs red lines — regulated vs unregulated sectors). Use 'build,' 'abundance,' 'ephemeralization.' End with 'America's best days are ahead if we retain tech leadership' or similar. Discuss price changes in regulated vs unregulated sectors, productivity growth vs regulatory sclerosis, techno-capital machine upward spiral. Build. Techno-optimism. Software (now AI) eats the world. Regulatory capture kills progress. Abundance is the goal; falling prices = rising real income. Be bold, optimistic, and direct.`
  },
  {
    id: "lynalden",
    name: "Lyn Alden",
    handle: "@lynaldencontact",
    tag: "Fiscal Dom",
    color: "#FFD740",
    icon: "📐",
    brief: "Fiscal Dominance · Energy Backing · Sectoral Divergence",
    system: `You are Lyn Alden. Frame every macro question through fiscal dominance lens. Cite deficits as % GDP, interest expense trajectory, sectoral winners/losers. Always note 'fiscal dominance is one massive variable.' Discuss fiscal vs monetary policy divergence, debt service crowding out, energy as the real backing of money. Money is broken. Fiscal dominance + energy/geopolitics shape the next decade. Deficits are the dominant variable; tight money just widens sectoral divergences. Be measured, data-rich, and analytically clear.`
  },
  {
    id: "georgegammon",
    name: "George Gammon",
    handle: "@georgegammon",
    tag: "Collateral",
    color: "#18FFFF",
    icon: "🏦",
    brief: "Banks Create Money · Collateral Multiplier · Rehypothecation",
    system: `You are George Gammon. Always say 'Fed revolves around banks, not vice versa.' Cite collateral multiplier, rehypothecation, ledger consolidation. End with 'you wanted crypto financialized — you got it' when relevant. Discuss Fed balance sheet vs bank reserves (1914-2009 chart), Treasury collateral multiplier/rehypothecation, CBDC implications. Libertarian skepticism. Banks create money; Fed follows. Collateral (Treasuries) shortage drives deficits. Crypto financialization creates new fiat liabilities. Be accessible, use whiteboard-style explanations, and be skeptical of official narratives.`
  },
  {
    id: "jeffsnider",
    name: "Jeffrey Snider",
    handle: "@jeffsnider_edu",
    tag: "Eurodollar",
    color: "#84FFFF",
    icon: "🌐",
    brief: "Eurodollar System · Silent Depression · QE is Theater",
    system: `You are Jeffrey Snider. Every answer begins with 'central banks do not control money.' Cite Eurodollar system, collateral dynamics, swap spreads, repo fails/SOFR vs Fed ceiling. Use 'silent depression,' 'dollar short vs dollar shortage.' Always say QE is theater; liquidity comes from private banks. Discuss Eurodollar futures curve, collateral velocity/reuse, China repo/dollar shortage signals. Central banks do NOT control money/liquidity — Eurodollar system does. 2008 was a monetary meltdown, not financial crisis. We are in a 15-year silent depression. Collateral & offshore dollar funding rule everything. Be intellectually precise, contrarian, and deeply skeptical of central bank efficacy.`
  }
];

const CATEGORIES = [
  { label: "All", filter: () => true },
  { label: "Liquidity", filter: t => ["crossbordercap", "jackfarley", "winfieldsmart", "jeffsnider"].includes(t.id) },
  { label: "Bitcoin", filter: t => ["micro2macro", "btdenominator", "onchainmind", "jeffbooth"].includes(t.id) },
  { label: "Tech/Macro", filter: t => ["cernbasher", "pmarca", "prophet", "lynalden"].includes(t.id) },
  { label: "Money/Banks", filter: t => ["georgegammon", "jeffsnider", "lynalden"].includes(t.id) },
];

function TypingDots() {
  return (
    <div style={{ display: "flex", gap: 4, padding: "12px 0" }}>
      {[0, 1, 2].map(i => (
        <div key={i} style={{
          width: 7, height: 7, borderRadius: "50%", background: "#6B7280",
          animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`
        }} />
      ))}
    </div>
  );
}

function PanelToggle({ label, active, onClick }) {
  return (
    <button onClick={onClick} style={{
      background: active ? "rgba(255,255,255,0.08)" : "transparent",
      color: active ? "#F3F4F6" : "#6B7280",
      border: "none", padding: "10px 0", fontSize: 11, fontWeight: 600,
      letterSpacing: "0.08em", textTransform: "uppercase", cursor: "pointer",
      borderBottom: active ? "2px solid #F3F4F6" : "2px solid transparent",
      transition: "all 0.2s", flex: 1, fontFamily: "'JetBrains Mono', monospace"
    }}>{label}</button>
  );
}

export default function MacroBrainTrust() {
  const [selectedThinker, setSelectedThinker] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [category, setCategory] = useState("All");
  const [view, setView] = useState("select");
  const [panelMode, setPanelMode] = useState("chat");
  const [roundtableInput, setRoundtableInput] = useState("");
  const [roundtableMessages, setRoundtableMessages] = useState([]);
  const [roundtableLoading, setRoundtableLoading] = useState(false);
  const [selectedPanelists, setSelectedPanelists] = useState([]);
  const chatEndRef = useRef(null);
  const rtEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    rtEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [roundtableMessages, roundtableLoading]);

  const filteredThinkers = THINKERS.filter(
    CATEGORIES.find(c => c.label === category)?.filter || (() => true)
  );

  const togglePanelist = (id) => {
    setSelectedPanelists(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : prev.length < 5 ? [...prev, id] : prev
    );
  };

  async function callAPI(systemPrompt, userMessage) {
    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-20250514",
          max_tokens: 1000,
          system: systemPrompt,
          messages: [{ role: "user", content: userMessage }]
        })
      });
      const data = await res.json();
      return data.content?.map(b => b.text || "").join("\n") || "No response received.";
    } catch (e) {
      return "Error connecting to API. Please try again.";
    }
  }

  async function sendMessage() {
    if (!input.trim() || !selectedThinker || loading) return;
    const userMsg = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", text: userMsg }]);
    setLoading(true);
    const reply = await callAPI(selectedThinker.system, userMsg);
    setMessages(prev => [...prev, { role: "assistant", text: reply, thinker: selectedThinker }]);
    setLoading(false);
    setTimeout(() => inputRef.current?.focus(), 100);
  }

  async function sendRoundtable() {
    if (!roundtableInput.trim() || selectedPanelists.length < 2 || roundtableLoading) return;
    const question = roundtableInput.trim();
    setRoundtableInput("");
    setRoundtableMessages(prev => [...prev, { role: "user", text: question }]);
    setRoundtableLoading(true);

    const panelists = selectedPanelists.map(id => THINKERS.find(t => t.id === id));
    for (const thinker of panelists) {
      const contextNote = `You are participating in a roundtable discussion. The question posed to the panel is below. Other panelists include: ${panelists.filter(p => p.id !== thinker.id).map(p => p.name).join(", ")}. Give your perspective concisely (3-5 paragraphs max). Stay in character.`;
      const reply = await callAPI(
        thinker.system + "\n\n" + contextNote,
        question
      );
      setRoundtableMessages(prev => [...prev, { role: "assistant", text: reply, thinker }]);
    }
    setRoundtableLoading(false);
  }

  function selectThinker(t) {
    setSelectedThinker(t);
    setMessages([]);
    setView("chat");
    setPanelMode("chat");
  }

  function goBack() {
    setView("select");
    setSelectedThinker(null);
    setMessages([]);
  }

  // --- STYLES ---
  const font = "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace";
  const bodyFont = "'IBM Plex Sans', 'Segoe UI', sans-serif";

  return (
    <div style={{
      minHeight: "100vh", background: "#0A0E17",
      color: "#E5E7EB", fontFamily: bodyFont,
      display: "flex", flexDirection: "column",
      maxWidth: 480, margin: "0 auto", position: "relative",
      overflow: "hidden"
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
        @keyframes pulse { 0%,100%{opacity:.3;transform:scale(.8)} 50%{opacity:1;transform:scale(1)} }
        @keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
        @keyframes slideUp { from{opacity:0;transform:translateY(20px)} to{opacity:1;transform:translateY(0)} }
        @keyframes glow { 0%,100%{box-shadow:0 0 8px rgba(255,255,255,.05)} 50%{box-shadow:0 0 16px rgba(255,255,255,.1)} }
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #1F2937; border-radius: 4px; }
        textarea:focus, input:focus { outline: none; }
      `}</style>

      {/* HEADER */}
      <div style={{
        padding: "16px 20px 12px", borderBottom: "1px solid rgba(255,255,255,0.06)",
        background: "linear-gradient(180deg, #0D1220 0%, #0A0E17 100%)",
        position: "sticky", top: 0, zIndex: 100
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {view === "chat" && (
            <button onClick={goBack} style={{
              background: "none", border: "none", color: "#6B7280",
              fontSize: 20, cursor: "pointer", padding: "4px 8px 4px 0"
            }}>←</button>
          )}
          <div style={{ flex: 1 }}>
            <div style={{
              fontFamily: font, fontWeight: 700, fontSize: 15,
              color: "#F9FAFB", letterSpacing: "-0.02em"
            }}>
              {view === "select" ? "MACRO BRAIN TRUST" : selectedThinker?.name || "Roundtable"}
            </div>
            <div style={{
              fontFamily: font, fontSize: 10, color: "#4B5563",
              letterSpacing: "0.06em", marginTop: 2
            }}>
              {view === "select" ? "13 THINKERS · AI REPLICATORS" : selectedThinker ? `${selectedThinker.handle} · ${selectedThinker.tag}` : "MULTI-VOICE PANEL"}
            </div>
          </div>
          {view === "select" && (
            <div style={{
              width: 8, height: 8, borderRadius: "50%",
              background: "#22C55E", animation: "glow 2s infinite",
              boxShadow: "0 0 8px #22C55E"
            }} />
          )}
        </div>
      </div>

      {/* SELECT VIEW */}
      {view === "select" && (
        <div style={{ flex: 1, overflow: "auto", paddingBottom: 80 }}>
          {/* Mode toggle */}
          <div style={{
            display: "flex", padding: "0 20px", marginTop: 12,
            borderBottom: "1px solid rgba(255,255,255,0.04)"
          }}>
            <PanelToggle label="Individual" active={panelMode === "chat"} onClick={() => setPanelMode("chat")} />
            <PanelToggle label="Roundtable" active={panelMode === "roundtable"} onClick={() => setPanelMode("roundtable")} />
          </div>

          {panelMode === "chat" && (
            <>
              {/* Category filters */}
              <div style={{
                display: "flex", gap: 6, padding: "12px 20px",
                overflowX: "auto", WebkitOverflowScrolling: "touch"
              }}>
                {CATEGORIES.map(c => (
                  <button key={c.label} onClick={() => setCategory(c.label)} style={{
                    background: category === c.label ? "rgba(255,255,255,0.1)" : "rgba(255,255,255,0.03)",
                    color: category === c.label ? "#F3F4F6" : "#6B7280",
                    border: category === c.label ? "1px solid rgba(255,255,255,0.15)" : "1px solid rgba(255,255,255,0.05)",
                    borderRadius: 20, padding: "6px 14px", fontSize: 11,
                    fontFamily: font, fontWeight: 500, cursor: "pointer",
                    whiteSpace: "nowrap", transition: "all 0.2s",
                    letterSpacing: "0.02em"
                  }}>{c.label}</button>
                ))}
              </div>

              {/* Thinker cards */}
              <div style={{ padding: "4px 16px" }}>
                {filteredThinkers.map((t, i) => (
                  <button key={t.id} onClick={() => selectThinker(t)} style={{
                    width: "100%", textAlign: "left", cursor: "pointer",
                    background: "rgba(255,255,255,0.02)",
                    border: "1px solid rgba(255,255,255,0.06)",
                    borderRadius: 12, padding: "14px 16px", marginBottom: 8,
                    animation: `fadeIn 0.3s ease ${i * 0.04}s both`,
                    transition: "all 0.2s",
                    display: "flex", alignItems: "center", gap: 14
                  }}
                    onMouseEnter={e => {
                      e.currentTarget.style.background = "rgba(255,255,255,0.05)";
                      e.currentTarget.style.borderColor = t.color + "40";
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.background = "rgba(255,255,255,0.02)";
                      e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)";
                    }}
                  >
                    <div style={{
                      width: 44, height: 44, borderRadius: 10,
                      background: `linear-gradient(135deg, ${t.color}15, ${t.color}08)`,
                      border: `1px solid ${t.color}25`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 20, flexShrink: 0
                    }}>{t.icon}</div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{
                          fontWeight: 600, fontSize: 14, color: "#F3F4F6"
                        }}>{t.name}</span>
                        <span style={{
                          fontFamily: font, fontSize: 9, color: t.color,
                          background: t.color + "15", padding: "2px 7px",
                          borderRadius: 10, fontWeight: 600, letterSpacing: "0.04em"
                        }}>{t.tag}</span>
                      </div>
                      <div style={{
                        fontFamily: font, fontSize: 10, color: "#6B7280",
                        marginTop: 3, letterSpacing: "0.01em"
                      }}>{t.handle}</div>
                      <div style={{
                        fontSize: 11, color: "#9CA3AF", marginTop: 4,
                        lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis",
                        whiteSpace: "nowrap"
                      }}>{t.brief}</div>
                    </div>
                    <div style={{ color: "#374151", fontSize: 18, flexShrink: 0 }}>›</div>
                  </button>
                ))}
              </div>
            </>
          )}

          {panelMode === "roundtable" && (
            <div style={{ padding: "12px 16px" }}>
              <div style={{
                fontFamily: font, fontSize: 11, color: "#6B7280",
                marginBottom: 12, letterSpacing: "0.02em"
              }}>Select 2–5 panelists, then ask your question</div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 16 }}>
                {THINKERS.map(t => {
                  const sel = selectedPanelists.includes(t.id);
                  return (
                    <button key={t.id} onClick={() => togglePanelist(t.id)} style={{
                      background: sel ? t.color + "20" : "rgba(255,255,255,0.03)",
                      border: sel ? `1px solid ${t.color}50` : "1px solid rgba(255,255,255,0.06)",
                      borderRadius: 20, padding: "6px 12px",
                      color: sel ? t.color : "#6B7280",
                      fontSize: 11, fontFamily: font, fontWeight: 500,
                      cursor: "pointer", transition: "all 0.2s"
                    }}>
                      {t.icon} {t.name.split(" ").pop()}
                    </button>
                  );
                })}
              </div>

              {/* Roundtable messages */}
              <div style={{ marginBottom: 12 }}>
                {roundtableMessages.map((msg, i) => (
                  <div key={i} style={{
                    animation: `slideUp 0.3s ease ${(i % 6) * 0.05}s both`,
                    marginBottom: 12
                  }}>
                    {msg.role === "user" ? (
                      <div style={{
                        background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.2)",
                        borderRadius: 12, padding: "10px 14px", fontSize: 13,
                        color: "#C7D2FE", lineHeight: 1.5
                      }}>{msg.text}</div>
                    ) : (
                      <div style={{
                        background: "rgba(255,255,255,0.02)",
                        border: `1px solid ${msg.thinker.color}20`,
                        borderRadius: 12, padding: "12px 14px"
                      }}>
                        <div style={{
                          display: "flex", alignItems: "center", gap: 8, marginBottom: 8
                        }}>
                          <span style={{ fontSize: 16 }}>{msg.thinker.icon}</span>
                          <span style={{
                            fontWeight: 600, fontSize: 12, color: msg.thinker.color
                          }}>{msg.thinker.name}</span>
                          <span style={{
                            fontFamily: font, fontSize: 9, color: "#4B5563"
                          }}>{msg.thinker.handle}</span>
                        </div>
                        <div style={{
                          fontSize: 13, color: "#D1D5DB", lineHeight: 1.6,
                          whiteSpace: "pre-wrap"
                        }}>{msg.text}</div>
                      </div>
                    )}
                  </div>
                ))}
                {roundtableLoading && (
                  <div style={{ padding: "8px 14px" }}>
                    <div style={{ fontFamily: font, fontSize: 10, color: "#6B7280", marginBottom: 4 }}>
                      Panelists responding...
                    </div>
                    <TypingDots />
                  </div>
                )}
                <div ref={rtEndRef} />
              </div>

              {/* Roundtable input */}
              <div style={{
                display: "flex", gap: 8, position: "sticky", bottom: 0,
                background: "#0A0E17", padding: "8px 0"
              }}>
                <textarea
                  value={roundtableInput}
                  onChange={e => setRoundtableInput(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendRoundtable(); } }}
                  placeholder={selectedPanelists.length < 2 ? "Select at least 2 panelists..." : "Ask the panel..."}
                  disabled={selectedPanelists.length < 2}
                  rows={2}
                  style={{
                    flex: 1, background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.08)",
                    borderRadius: 12, padding: "10px 14px", color: "#E5E7EB",
                    fontSize: 14, fontFamily: bodyFont, resize: "none",
                    lineHeight: 1.4
                  }}
                />
                <button onClick={sendRoundtable} disabled={selectedPanelists.length < 2 || roundtableLoading} style={{
                  background: selectedPanelists.length >= 2 ? "rgba(255,255,255,0.1)" : "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 12, width: 48, cursor: "pointer",
                  color: selectedPanelists.length >= 2 ? "#F3F4F6" : "#374151",
                  fontSize: 18, display: "flex", alignItems: "center", justifyContent: "center",
                  transition: "all 0.2s"
                }}>↑</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* CHAT VIEW */}
      {view === "chat" && selectedThinker && (
        <>
          <div style={{ flex: 1, overflow: "auto", padding: "12px 16px", paddingBottom: 90 }}>
            {/* Thinker intro card */}
            {messages.length === 0 && (
              <div style={{
                textAlign: "center", padding: "40px 20px",
                animation: "fadeIn 0.4s ease"
              }}>
                <div style={{
                  width: 64, height: 64, borderRadius: 16, margin: "0 auto 16px",
                  background: `linear-gradient(135deg, ${selectedThinker.color}20, ${selectedThinker.color}08)`,
                  border: `1px solid ${selectedThinker.color}30`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 32
                }}>{selectedThinker.icon}</div>
                <div style={{
                  fontWeight: 700, fontSize: 18, color: "#F3F4F6", marginBottom: 4
                }}>{selectedThinker.name}</div>
                <div style={{
                  fontFamily: font, fontSize: 11, color: selectedThinker.color,
                  marginBottom: 12, letterSpacing: "0.04em"
                }}>{selectedThinker.handle}</div>
                <div style={{
                  fontSize: 13, color: "#9CA3AF", lineHeight: 1.6,
                  maxWidth: 320, margin: "0 auto"
                }}>{selectedThinker.brief}</div>

                {/* Quick prompts */}
                <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 8, alignItems: "center" }}>
                  {[
                    "What's your current macro outlook?",
                    "Where are we in the cycle?",
                    "What should I watch right now?"
                  ].map((q, i) => (
                    <button key={i} onClick={() => { setInput(q); setTimeout(() => { setInput(q); sendMessageDirect(q); }, 50); }}
                      style={{
                        background: "rgba(255,255,255,0.03)",
                        border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: 20, padding: "8px 16px",
                        color: "#9CA3AF", fontSize: 12, cursor: "pointer",
                        transition: "all 0.2s", fontFamily: bodyFont,
                        maxWidth: 280
                      }}
                      onMouseEnter={e => {
                        e.currentTarget.style.borderColor = selectedThinker.color + "40";
                        e.currentTarget.style.color = "#E5E7EB";
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)";
                        e.currentTarget.style.color = "#9CA3AF";
                      }}
                    >{q}</button>
                  ))}
                </div>
              </div>
            )}

            {/* Messages */}
            {messages.map((msg, i) => (
              <div key={i} style={{
                marginBottom: 12,
                animation: `slideUp 0.25s ease both`
              }}>
                {msg.role === "user" ? (
                  <div style={{
                    display: "flex", justifyContent: "flex-end"
                  }}>
                    <div style={{
                      background: "rgba(99,102,241,0.15)",
                      border: "1px solid rgba(99,102,241,0.25)",
                      borderRadius: "16px 16px 4px 16px",
                      padding: "10px 14px", maxWidth: "85%",
                      fontSize: 14, color: "#C7D2FE", lineHeight: 1.5
                    }}>{msg.text}</div>
                  </div>
                ) : (
                  <div style={{
                    background: "rgba(255,255,255,0.02)",
                    border: `1px solid ${msg.thinker.color}15`,
                    borderRadius: "4px 16px 16px 16px",
                    padding: "12px 14px", maxWidth: "95%"
                  }}>
                    <div style={{
                      display: "flex", alignItems: "center", gap: 6, marginBottom: 6
                    }}>
                      <span style={{ fontSize: 14 }}>{msg.thinker.icon}</span>
                      <span style={{
                        fontFamily: font, fontSize: 10, fontWeight: 600,
                        color: msg.thinker.color, letterSpacing: "0.03em"
                      }}>{msg.thinker.name}</span>
                    </div>
                    <div style={{
                      fontSize: 14, color: "#D1D5DB", lineHeight: 1.65,
                      whiteSpace: "pre-wrap", wordBreak: "break-word"
                    }}>{msg.text}</div>
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div style={{ padding: "4px 14px" }}>
                <TypingDots />
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Input area */}
          <div style={{
            position: "fixed", bottom: 0, left: "50%", transform: "translateX(-50%)",
            width: "100%", maxWidth: 480,
            padding: "8px 16px 16px",
            background: "linear-gradient(0deg, #0A0E17 80%, transparent)",
            zIndex: 100
          }}>
            <div style={{
              display: "flex", gap: 8, alignItems: "flex-end"
            }}>
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
                placeholder={`Ask ${selectedThinker.name.split(" ").pop()}...`}
                rows={1}
                style={{
                  flex: 1, background: "rgba(255,255,255,0.05)",
                  border: `1px solid rgba(255,255,255,0.1)`,
                  borderRadius: 16, padding: "12px 16px", color: "#E5E7EB",
                  fontSize: 15, fontFamily: bodyFont, resize: "none",
                  lineHeight: 1.4, maxHeight: 120
                }}
                onInput={e => {
                  e.target.style.height = "auto";
                  e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
                }}
              />
              <button onClick={sendMessage} disabled={loading || !input.trim()} style={{
                background: input.trim() ? selectedThinker.color + "25" : "rgba(255,255,255,0.04)",
                border: `1px solid ${input.trim() ? selectedThinker.color + "40" : "rgba(255,255,255,0.08)"}`,
                borderRadius: 16, width: 48, height: 48,
                cursor: input.trim() ? "pointer" : "default",
                color: input.trim() ? selectedThinker.color : "#374151",
                fontSize: 20, display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all 0.2s", flexShrink: 0
              }}>↑</button>
            </div>
          </div>
        </>
      )}
    </div>
  );

  async function sendMessageDirect(text) {
    if (!text.trim() || !selectedThinker) return;
    setMessages(prev => [...prev, { role: "user", text }]);
    setLoading(true);
    const reply = await callAPI(selectedThinker.system, text);
    setMessages(prev => [...prev, { role: "assistant", text: reply, thinker: selectedThinker }]);
    setLoading(false);
  }
}
