import { useEffect, useRef, useState } from "react";
import {
  ArrowDown, ArrowUp, BookOpen, Bot, Check, ChevronDown, Clock3, ExternalLink,
  GraduationCap, Menu, MessageCircle, Plus, ShieldCheck, Sparkles, X, Link2
} from "lucide-react";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const suggestions = [
  { title: "Academic information", question: "Tell me about the academic calendar and semester schedule." },
  { title: "Placement details", question: "Tell me about the placement process at KGRCET." },
  { title: "College leadership", question: "Who is the principal of KG Reddy College?" },
  { title: "College facilities", question: "What facilities are available at KGRCET?" },
];

const quickLinks = [
  { label: "Official Website", href: "https://kgr.ac.in/", icon: ExternalLink },
  { label: "Academic Calendars", href: "https://kgr.ac.in/academic-calenders/", icon: BookOpen },
  { label: "Placements", href: "https://kgr.ac.in/placements/", icon: GraduationCap },
];

function newConversation() {
  return { id: crypto.randomUUID(), title: "New conversation", messages: [], updatedAt: Date.now() };
}

function formatTime(timestamp) {
  return new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit" }).format(timestamp);
}

function App() {
  const [conversations, setConversations] = useState(() => {
    try {
      const saved = localStorage.getItem("kgrcet-rag-conversations");
      const parsed = saved ? JSON.parse(saved) : null;
      return Array.isArray(parsed) && parsed.length ? parsed : [newConversation()];
    } catch {
      return [newConversation()];
    }
  });
  const [activeId, setActiveId] = useState(() => {
    try {
      return localStorage.getItem("kgrcet-rag-active-chat") || null;
    } catch {
      return null;
    }
  });
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showQuickLinks, setShowQuickLinks] = useState(true);
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    if (!activeId && conversations.length) setActiveId(conversations[0].id);
  }, [activeId, conversations]);

  // Save chat history in this browser so it survives page refreshes.
  useEffect(() => {
    try {
      localStorage.setItem("kgrcet-rag-conversations", JSON.stringify(conversations));
      if (activeId) localStorage.setItem("kgrcet-rag-active-chat", activeId);
    } catch (err) {
      console.warn("Could not save local chat history:", err);
    }
  }, [conversations, activeId]);

  const active = conversations.find((item) => item.id === activeId) || conversations[0];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [active?.messages, busy]);

  function createChat() {
    if (busy) return;
    const chat = newConversation();
    setConversations((previous) => [chat, ...previous]);
    setActiveId(chat.id);
    setInput("");
    setError("");
    setSidebarOpen(false);
  }

  function selectChat(id) {
    if (busy) return;
    setActiveId(id);
    setError("");
    setSidebarOpen(false);
  }

  async function sendQuestion(rawQuestion = input) {
    const question = rawQuestion.trim();
    if (!question || busy || !active) return;

    const userMessage = { id: crypto.randomUUID(), role: "user", content: question, timestamp: Date.now() };
    const chatId = active.id;
    setInput("");
    setError("");
    setBusy(true);

    setConversations((previous) => previous.map((chat) => chat.id === chatId
      ? {
          ...chat,
          title: chat.messages.length === 0 ? question.slice(0, 42) + (question.length > 42 ? "…" : "") : chat.title,
          updatedAt: Date.now(),
          messages: [...chat.messages, userMessage],
        }
      : chat
    ));

    try {
      const response = await fetch(`${API_BASE}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          // Send recent turns from this conversation so the backend can resolve
          // follow-up questions such as "what is his qualification?"
          history: (conversations.find((chat) => chat.id === chatId)?.messages || [])
            .slice(-50)
            .map((message) => ({
              role: message.role,
              content: message.content,
            })),
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || `Request failed (${response.status}).`);
      }
      const assistantMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: payload.answer || "I couldn't generate an answer.",
        sources: Array.isArray(payload.sources) ? payload.sources : [],
        timestamp: Date.now(),
      };
      setConversations((previous) => previous.map((chat) => chat.id === chatId
        ? { ...chat, updatedAt: Date.now(), messages: [...chat.messages, assistantMessage] }
        : chat
      ));
    } catch (err) {
      setError(err.message || "Could not connect to the assistant. Please try again.");
    } finally {
      setBusy(false);
      setTimeout(() => textareaRef.current?.focus(), 0);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    sendQuestion();
  }

  return (
    <div className="flex h-dvh min-h-[600px] overflow-hidden bg-[#f5f7fb] text-slate-800">
      {sidebarOpen && <button aria-label="Close sidebar" onClick={() => setSidebarOpen(false)} className="fixed inset-0 z-30 bg-slate-950/40 md:hidden" />}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-[280px] shrink-0 flex-col border-r border-white/10 bg-[#102b4e] text-white transition-transform md:static md:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center gap-3 px-5 pb-5 pt-6">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-[#12355b] shadow-lg">
            <GraduationCap size={27} />
          </div>
          <div>
            <p className="text-[15px] font-extrabold tracking-wide">KGRCET</p>
            <p className="mt-0.5 text-[11px] text-blue-100/75">AI Campus Assistant</p>
          </div>
          <button className="ml-auto rounded-lg p-2 text-blue-100 hover:bg-white/10 md:hidden" onClick={() => setSidebarOpen(false)} aria-label="Close menu"><X size={18} /></button>
        </div>

        <div className="px-4">
          <button onClick={createChat} disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-sm font-semibold transition hover:bg-white/15 disabled:opacity-50">
            <Plus size={17} /> New conversation
          </button>
        </div>

        <div className="mt-7 px-5">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-100/50">Workspace</p>
        </div>
        <div className="mt-3 flex-1 overflow-y-auto px-3">
          <p className="px-2 pb-2 text-xs font-medium text-blue-100/55">Recent conversations</p>
          <div className="space-y-1">
            {conversations.map((chat) => (
              <button key={chat.id} onClick={() => selectChat(chat.id)} className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm transition ${chat.id === activeId ? "bg-white/15 text-white" : "text-blue-50/75 hover:bg-white/8 hover:text-white"}`}>
                <MessageCircle size={16} className="shrink-0 opacity-80" />
                <span className="min-w-0 flex-1 truncate">{chat.title}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="mx-4 mb-4 rounded-2xl border border-white/10 bg-white/[0.06] p-4">
          <div className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck size={17} className="text-emerald-300" /> Evidence-based answers</div>
          <p className="mt-2 text-xs leading-5 text-blue-100/65">Answers are generated from indexed KGRCET website content. Check the cited sources for confirmation.</p>
        </div>
        <div className="border-t border-white/10 px-5 py-3 text-[11px] text-blue-100/50">KGRCET · Student information assistant</div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[76px] shrink-0 items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 sm:px-7">
          <div className="flex min-w-0 items-center gap-3">
            <button onClick={() => setSidebarOpen(true)} aria-label="Open menu" className="rounded-xl p-2 hover:bg-slate-100 md:hidden"><Menu size={20} /></button>
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-[#164779]"><Bot size={22} /></div>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-bold text-slate-900 sm:text-base">KGRCET Campus Assistant</h1>
              <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-500 sm:text-xs"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> AI-powered college information</p>
            </div>
          </div>
          <button onClick={() => setShowQuickLinks((v) => !v)} className="hidden items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 sm:flex">
            Quick links <ChevronDown size={14} className={`transition ${showQuickLinks ? "rotate-180" : ""}`} />
          </button>
        </header>

        {showQuickLinks && (
          <div className="flex shrink-0 gap-2 overflow-x-auto border-b border-slate-200/70 bg-white px-4 py-3 sm:px-7">
            {quickLinks.map(({ label, href, icon: Icon }) => (
              <a key={label} href={href} target="_blank" rel="noreferrer" className="flex shrink-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-800">
                <Icon size={14} /> {label} <ExternalLink size={11} className="opacity-50" />
              </a>
            ))}
          </div>
        )}

        <section className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-4xl px-4 pb-8 pt-6 sm:px-8 sm:pt-10">
            {active?.messages.length === 0 ? (
              <div className="pt-5 sm:pt-12">
                <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-[22px] bg-gradient-to-br from-[#12365d] to-[#2878ba] text-white shadow-lg shadow-blue-900/15"><Sparkles size={29} /></div>
                <p className="mt-6 text-center text-xs font-bold uppercase tracking-[0.2em] text-blue-700">Your campus, one conversation away</p>
                <h2 className="mx-auto mt-3 max-w-2xl text-center text-3xl font-extrabold leading-tight tracking-tight text-slate-900 sm:text-4xl">How can I help you today?</h2>
                <p className="mx-auto mt-4 max-w-xl text-center text-sm leading-6 text-slate-500 sm:text-base">Ask about academics, placements, college leadership, facilities and other information published on the KGRCET website.</p>
                <div className="mt-9 grid gap-3 sm:grid-cols-2">
                  {suggestions.map((item, index) => (
                    <button key={item.title} onClick={() => sendQuestion(item.question)} disabled={busy} className="group rounded-2xl border border-slate-200/90 bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-md disabled:opacity-50 sm:p-5">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-bold text-slate-800">{item.title}</p>
                          <p className="mt-2 text-xs leading-5 text-slate-500">{item.question}</p>
                        </div>
                        <div className="rounded-xl bg-blue-50 p-2 text-blue-700 transition group-hover:bg-blue-100"><ArrowUp size={15} /></div>
                      </div>
                    </button>
                  ))}
                </div>
                <div className="mt-8 flex items-center justify-center gap-2 text-[11px] text-slate-400"><ShieldCheck size={14} /> Answers may be incomplete; verify important details using official sources.</div>
              </div>
            ) : (
              <div className="space-y-8">
                {active?.messages.map((message) => (
                  <article key={message.id} className={`flex gap-3 sm:gap-4 ${message.role === "user" ? "flex-row-reverse" : ""}`}>
                    <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${message.role === "user" ? "bg-slate-200 text-slate-700" : "bg-[#12365d] text-white"}`}>
                      {message.role === "user" ? <GraduationCap size={18} /> : <Bot size={19} />}
                    </div>
                    <div className={`min-w-0 max-w-[88%] sm:max-w-[82%] ${message.role === "user" ? "text-right" : ""}`}>
                      <div className="mb-1.5 flex items-center gap-2 text-xs font-bold text-slate-700">
                        {message.role === "user" ? "You" : "KGRCET Assistant"}
                        <span className="font-normal text-slate-400">{formatTime(message.timestamp)}</span>
                      </div>
                      <div className={`inline-block rounded-2xl px-4 py-3 text-left text-sm ${message.role === "user" ? "rounded-tr-md bg-[#174775] text-white" : "rounded-tl-md border border-slate-200/80 bg-white text-slate-700 shadow-sm"}`}>
                        <div className="markdown-answer">{message.content}</div>
                      </div>
                      {message.role === "assistant" && message.sources?.length > 0 && (
                        <div className="mt-3 rounded-2xl border border-slate-200/80 bg-white p-3 text-left shadow-sm">
                          <div className="mb-2 flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-slate-500"><Link2 size={13} /> Official sources ({message.sources.length})</div>
                          <div className="space-y-1.5">
                            {message.sources.map((source, i) => (
                              <a key={`${source.url}-${i}`} href={source.url} target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded-lg px-2 py-2 text-xs text-blue-800 transition hover:bg-blue-50">
                                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-blue-50 text-[10px] font-bold">{i + 1}</span>
                                <span className="min-w-0 flex-1 truncate">{source.title || source.url}</span>
                                <ExternalLink size={12} className="shrink-0 opacity-60" />
                              </a>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </article>
                ))}
                {busy && (
                  <div className="flex gap-3 sm:gap-4">
                    <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#12365d] text-white"><Bot size={19} /></div>
                    <div className="rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 shadow-sm">
                      <div className="flex items-center gap-2 text-xs text-slate-500"><span className="flex gap-1"><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-600 [animation-delay:-0.2s]" /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-600 [animation-delay:-0.1s]" /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-blue-600" /></span> Searching college information…</div>
                    </div>
                  </div>
                )}
                <div ref={bottomRef} />
              </div>
            )}
            {error && (
              <div role="alert" className="mt-5 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                <span className="flex-1">{error}</span>
                <button onClick={() => { setError(""); }} className="rounded p-1 hover:bg-red-100" aria-label="Dismiss error"><X size={15} /></button>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </section>

        <footer className="shrink-0 border-t border-slate-200/80 bg-[#f5f7fb]/95 px-3 pb-3 pt-3 sm:px-8 sm:pb-5">
          <div className="mx-auto max-w-4xl">
            <form onSubmit={handleSubmit} className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-[0_8px_30px_rgba(15,35,65,0.06)] transition focus-within:border-blue-300 focus-within:ring-4 focus-within:ring-blue-100/70">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    handleSubmit(event);
                  }
                }}
                placeholder="Ask anything about KGRCET…"
                rows={1}
                maxLength={1000}
                disabled={busy}
                className="max-h-32 min-h-[42px] flex-1 resize-y bg-transparent px-3 py-3 text-sm text-slate-800 outline-none placeholder:text-slate-400 disabled:opacity-60"
              />
              <button type="submit" disabled={!input.trim() || busy} aria-label="Send question" className="mb-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#174775] text-white transition hover:bg-[#10385f] disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"><ArrowUp size={19} /></button>
            </form>
            <div className="mt-2 flex items-center justify-between gap-3 px-1 text-[10px] text-slate-400 sm:text-[11px]">
              <span>AI-generated responses · Verify important details with official sources</span>
              <span className="hidden sm:inline">{input.length}/1000 · Shift + Enter for a new line</span>
            </div>
          </div>
        </footer>
      </main>
    </div>
  );
}

export default App;
