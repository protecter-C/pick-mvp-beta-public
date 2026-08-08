"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Dashboard, Decision, money, request } from "../lib/api";

type AuthMode = "login" | "register";

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [mode, setMode] = useState<AuthMode>("register");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [history, setHistory] = useState<Decision[]>([]);
  const [result, setResult] = useState<Decision | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => setToken(localStorage.getItem("pick_token")), []);

  const refresh = useCallback(async (authToken: string) => {
    const [metrics, decisions] = await Promise.all([
      request<Dashboard>("/dashboard", authToken),
      request<Decision[]>("/decisions", authToken),
    ]);
    setDashboard(metrics);
    setHistory(decisions);
  }, []);

  useEffect(() => { if (token) refresh(token).catch((error) => setMessage(error.message)); }, [token, refresh]);

  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      const payload = mode === "register"
        ? { name: form.get("name"), email: form.get("email"), password: form.get("password"), referral_code: form.get("referral") || null }
        : { email: form.get("email"), password: form.get("password") };
      const response = await request<{ access_token: string }>(`/auth/${mode}`, undefined, { method: "POST", body: JSON.stringify(payload) });
      localStorage.setItem("pick_token", response.access_token); setToken(response.access_token);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not sign in"); }
    finally { setLoading(false); }
  }

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!token) return; setLoading(true); setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      const decision = await request<Decision>("/decisions/analyze", token, { method: "POST", body: JSON.stringify({ query: form.get("query"), budget_cents: Math.round(Number(form.get("budget")) * 100), urgency: Number(form.get("urgency")), fit: Number(form.get("fit")) }) });
      setResult(decision); await refresh(token);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Analysis failed"); }
    finally { setLoading(false); }
  }

  async function track() {
    if (!token || !result) return;
    await request("/price-watches", token, { method: "POST", body: JSON.stringify({ product_id: result.product.id, target_price_cents: Math.round(result.product.current_price_cents * 0.9) }) });
    setMessage("Tracking started. We’ll flag a 10% price drop.");
  }

  async function recordPurchase() {
    if (!token || !result) return;
    await request("/purchases", token, { method: "POST", body: JSON.stringify({ product_id: result.product.id, decision_id: result.id, price_paid_cents: result.product.current_price_cents }) });
    setMessage("Purchase protected. Add return and warranty dates from your purchase history."); await refresh(token);
  }

  function logout() { localStorage.removeItem("pick_token"); setToken(null); setDashboard(null); setHistory([]); setResult(null); }

  if (!token) return <main className="authShell"><section className="authStory"><a className="logo">PICK<span>.</span></a><div><p className="eyebrow">DECISIONS THAT PAY OFF</p><h1>Buy better.<br />Regret less.</h1><p className="lede">Independent verdicts, price protection, and rewards for every smart choice — including not buying.</p></div><div className="trust">Verdicts are never influenced by sponsors or affiliate revenue.</div></section><section className="authPanel"><form className="authCard" onSubmit={authenticate}><p className="eyebrow">{mode === "register" ? "START CHOOSING WELL" : "WELCOME BACK"}</p><h2>{mode === "register" ? "Create your account" : "Sign in to PICK"}</h2>{mode === "register" && <label>Name<input name="name" required placeholder="Your name" /></label>}<label>Email<input name="email" type="email" required placeholder="you@example.com" /></label><label>Password<input name="password" type="password" minLength={8} required placeholder="At least 8 characters" /></label>{mode === "register" && <label>Referral code <small>optional</small><input name="referral" placeholder="PICK code" /></label>}<button className="primary" disabled={loading}>{loading ? "Working…" : mode === "register" ? "Create account" : "Sign in"}</button>{message && <p className="error">{message}</p>}<button type="button" className="textButton" onClick={() => setMode(mode === "register" ? "login" : "register")}>{mode === "register" ? "Already a member? Sign in" : "New to PICK? Create account"}</button></form></section></main>;

  return <main className="appShell"><header><a className="logo">PICK<span>.</span></a><nav><a href="#decide">Decide</a><a href="#history">History</a><button onClick={logout}>Log out</button></nav></header><section className="hero" id="decide"><div><p className="eyebrow">YOUR INDEPENDENT BUYING SIGNAL</p><h1>Should you<br />buy it?</h1><p>Paste a product URL or search. PICK weighs price, budget, fit, timing, and quality — not commissions.</p></div><form className="decisionForm" onSubmit={analyze}><label>Product URL or search<input name="query" required placeholder="https://… or wireless headphones" /></label><div className="formGrid"><label>Budget (USD)<input name="budget" type="number" min="1" defaultValue="200" required /></label><label>Need it how soon?<select name="urgency" defaultValue="5"><option value="2">No rush</option><option value="5">This month</option><option value="8">This week</option><option value="10">Today</option></select></label><label>How well does it fit?<select name="fit" defaultValue="7"><option value="3">Not sure</option><option value="7">Good fit</option><option value="9">Excellent fit</option></select></label></div><button className="primary" disabled={loading}>{loading ? "Weighing evidence…" : "Get my verdict →"}</button></form></section>{message && <div className="toast">{message}</div>}{result && <section className={`verdict ${result.verdict.toLowerCase()}`}><div className="verdictMark"><span>{result.verdict}</span><strong>{result.score}</strong><small>/ 100</small></div><div className="verdictBody"><p className="eyebrow">INDEPENDENT VERDICT</p><h2>{result.product.name}</h2><p>{result.explanation}</p><ul>{result.evidence.map((item) => <li key={item}>{item}</li>)}</ul><div className="actions"><button className="primary" onClick={result.verdict === "BUY" ? recordPurchase : track}>{result.verdict === "BUY" ? "I bought it" : "Track this price"}</button><button className="secondary" onClick={track}>Alert me at {money(result.product.current_price_cents * .9)}</button></div>{result.alternatives.length > 0 && <div className="alternatives"><p className="eyebrow">LOWER-COST ALTERNATIVES</p>{result.alternatives.map((product) => <div key={product.id}><span>{product.name}</span><strong>{money(product.current_price_cents)}</strong></div>)}</div>}</div></section>}<section className="metrics"><article><span>Choice Score</span><strong>{dashboard?.choice_score ?? "—"}</strong><small>Value · Fit · Timing · Satisfaction</small></article><article><span>Saved</span><strong>{money(dashboard?.savings_cents ?? 0)}</strong><small>Against typical prices</small></article><article><span>Prevented spend</span><strong>{money(dashboard?.prevented_spend_cents ?? 0)}</strong><small>From smart PASS decisions</small></article><article><span>Points</span><strong>{dashboard?.points_balance ?? 0}</strong><small>WAIT and PASS earn more</small></article></section><section className="history" id="history"><div className="sectionHeading"><div><p className="eyebrow">YOUR DECISION TRAIL</p><h2>Recent choices</h2></div><span>{dashboard?.decision_count ?? 0} decisions</span></div>{history.length === 0 ? <div className="empty">Your first verdict will appear here.</div> : <div className="historyList">{history.map((decision) => <article key={decision.id}><span className={`pill ${decision.verdict.toLowerCase()}`}>{decision.verdict}</span><div><strong>{decision.product.name}</strong><small>{new Date(decision.created_at).toLocaleDateString()} · score {decision.score}</small></div><b>{money(decision.product.current_price_cents)}</b></article>)}</div>}</section><footer><a className="logo">PICK<span>.</span></a><p>Good decisions deserve better outcomes.</p><small>Affiliate relationships never affect verdicts or rank.</small></footer></main>;
}
