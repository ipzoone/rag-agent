import { useRef, useState } from "react";
import { I18nProvider, LangToggle } from "./i18n";
import RagChat from "./components/RagChat";
import HeroSection from "./components/HeroSection";
import KnowledgeBaseSummary from "./components/KnowledgeBaseSummary";
import GitHubLink from "./components/GitHubLink";
import DeployLink from "./components/DeployLink";
import "./App.css";

const CONVERSATION_ID_KEY = "rag_conversation_id";

function getOrCreateConversationId(): string {
  const cached = localStorage.getItem(CONVERSATION_ID_KEY);
  if (cached) return cached;
  const id = crypto.randomUUID();
  localStorage.setItem(CONVERSATION_ID_KEY, id);
  return id;
}

export default function App() {
  return (
    <I18nProvider>
      <LangToggle />
      <AppInner />
      <GitHubLink />
      <DeployLink />
    </I18nProvider>
  );
}

function AppInner() {
  const conversationIdRef = useRef<string>(getOrCreateConversationId());
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <>
      <div className="app-wrap">
        <HeroSection />

        <div className="kb-mini">
          <KnowledgeBaseSummary conversationId={conversationIdRef.current} />
        </div>
      </div>

      <div className={`chat-fab ${chatOpen ? "chat-fab--hidden" : ""}`}>
        <button className="chat-fab-btn" onClick={() => setChatOpen(true)} aria-label="Open chat">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </button>
      </div>

      <div className={`chat-widget ${chatOpen ? "chat-widget--open" : ""}`}>
        <div className="chat-widget-header">
          <div className="chat-widget-title">
            <span className="widget-indicator" />
            <span className="widget-title-text">Chat</span>
          </div>
          <button className="widget-close-btn" onClick={() => setChatOpen(false)}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div className="chat-widget-body">
          <RagChat />
        </div>
      </div>
    </>
  );
}
