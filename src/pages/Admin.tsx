import { useCallback, useEffect, useRef, useState } from "react";
import { adminApi, fileToBase64 } from "../adminApi";
import "./Admin.css";

type FileEntry = { name: string; size: number };
type DocEntry = {
  docId: string;
  pages: number;
  chunks: number;
  totalBytes: number;
  meta?: { doc_name?: string; type?: string };
};

function formatSize(bytes: number): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function AdminPanel() {
  const [loggedIn, setLoggedIn] = useState(adminApi.isLoggedIn());
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");

  const [files, setFiles] = useState<FileEntry[]>([]);
  const [documents, setDocuments] = useState<DocEntry[]>([]);
  const [generatedAt, setGeneratedAt] = useState<string>("");
  const [allowedExt, setAllowedExt] = useState<string[]>([]);

  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "err" | "info"; text: string } | null>(null);
  const [log, setLog] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    const data = await adminApi.listFiles();
    if (data?.ok) {
      setFiles(data.files ?? []);
      setDocuments(data.documents ?? []);
      setGeneratedAt(data.generated_at ?? "");
      setAllowedExt(data.allowed_ext ?? []);
    } else if (data?.error === "unauthorized") {
      adminApi.logout();
      setLoggedIn(false);
    }
  }, []);

  useEffect(() => {
    if (loggedIn) refresh();
  }, [loggedIn, refresh]);

  const onLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError("");
    const ok = await adminApi.login(password);
    if (ok) {
      setLoggedIn(true);
      setPassword("");
    } else {
      setLoginError("Password salah / password incorrect.");
    }
  };

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (!file) return;

    setBusy(true);
    setMessage({ kind: "info", text: `Mengunggah ${file.name}…` });
    try {
      const dataUrl = await fileToBase64(file);
      const res = await adminApi.upload(file.name, dataUrl);
      if (res?.ok) {
        setMessage({ kind: "ok", text: `Berhasil unggah ${res.filename} (${formatSize(res.size)}).` });
        await refresh();
      } else {
        setMessage({ kind: "err", text: res?.error || "Unggah gagal." });
      }
    } catch (err) {
      setMessage({ kind: "err", text: String(err) });
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (name: string) => {
    if (!confirm(`Hapus ${name}?`)) return;
    setBusy(true);
    try {
      const res = await adminApi.remove(name);
      if (res?.ok) {
        setMessage({ kind: "ok", text: `Terhapus ${name}.` });
        await refresh();
      } else {
        setMessage({ kind: "err", text: res?.error || "Gagal hapus." });
      }
    } finally {
      setBusy(false);
    }
  };

  const onRebuild = async () => {
    setBusy(true);
    setLog("");
    setMessage({ kind: "info", text: "Membangun ulang knowledge base… (embed lokal, bisa beberapa menit)" });
    try {
      const res = await adminApi.rebuild();
      if (res?.ok) {
        const s = res.summary || {};
        setLog(
          `Dokumen: ${s.documents ?? 0}\nChunk: ${s.chunks ?? 0}\nUkuran: ${(s.totalBytes ?? 0) / 1024 < 1024
            ? `${((s.totalBytes ?? 0) / 1024).toFixed(1)} KB`
            : `${((s.totalBytes ?? 0) / 1024 / 1024).toFixed(2)} MB`}`
        );
        setMessage({ kind: "ok", text: "Knowledge base diperbarui. Vektor siap dipakai chat." });
        await refresh();
      } else {
        setLog(res?.detail ? String(res.detail) : "");
        setMessage({ kind: "err", text: res?.error || "Build gagal." });
      }
    } catch (err) {
      setMessage({ kind: "err", text: String(err) });
    } finally {
      setBusy(false);
    }
  };

  if (!loggedIn) {
    return (
      <div className="admin-shell">
        <form className="admin-login" onSubmit={onLogin}>
          <h1>Admin Panel</h1>
          <p className="admin-sub">Masukkan password admin untuk mengelola knowledge base.</p>
          <input
            type="password"
            placeholder="Admin password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
          />
          {loginError && <div className="admin-error">{loginError}</div>}
          <button type="submit" disabled={!password}>Login</button>
          <a className="admin-back" href="/">← Kembali ke chat</a>
        </form>
      </div>
    );
  }

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <h1>Admin Panel — Knowledge Base</h1>
        <div className="admin-actions-top">
          <span className="admin-meta">
            {documents.length} dokumen · {generatedAt ? `build ${new Date(generatedAt).toLocaleString()}` : "belum dibuild"}
          </span>
          <button className="admin-logout" onClick={() => { adminApi.logout(); setLoggedIn(false); }}>Logout</button>
        </div>
      </header>

      {message && (
        <div className={`admin-message admin-${message.kind}`}>{message.text}</div>
      )}

      <section className="admin-card">
        <h2>Unggah Dokumen</h2>
        <p className="admin-sub">
          Format: {allowedExt.join(", ") || ".pdf, .docx, .xlsx, .pptx"}. File tersimpan di
          folder upload agent, lalu klik “Build Ulang” di bawah.
        </p>
        <label className="admin-upload-btn">
          Pilih File
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.xlsx,.pptx" onChange={onUpload} disabled={busy} hidden />
        </label>
        <button className="admin-rebuild" onClick={onRebuild} disabled={busy}>
          {busy ? "Memproses…" : "Build Ulang (prepare-rag)"}
        </button>
      </section>

      <section className="admin-card">
        <h2>File Sumber ({files.length})</h2>
        {files.length === 0 ? (
          <p className="admin-empty">Belum ada file. Unggah dokumen di atas.</p>
        ) : (
          <ul className="admin-list">
            {files.map((f) => (
              <li key={f.name + f.source}>
                <span className="admin-file-name">{f.name}</span>
                <span className={`admin-file-tag ${f.source}`}>{f.source}</span>
                <span className="admin-file-size">{formatSize(f.size)}</span>
                {f.source === "upload" ? (
                  <button className="admin-del" onClick={() => onDelete(f.name)} disabled={busy}>Hapus</button>
                ) : (
                  <span className="admin-file-nodel" title="Dikelola di public/prepare-rag/files/">read-only</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="admin-card">
        <h2>Dokumen Terindeks ({documents.length})</h2>
        {documents.length === 0 ? (
          <p className="admin-empty">Belum dibuild. Unggah file lalu klik “Build Ulang”.</p>
        ) : (
          <ul className="admin-list">
            {documents.map((d) => (
              <li key={d.docId}>
                <span className="admin-file-name">
                  {d.meta?.doc_name || d.docId} <em>({d.meta?.type || "?"})</em>
                </span>
                <span className="admin-file-size">
                  {d.pages} hal · {d.chunks} chunk · {formatSize(d.totalBytes)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {log && (
        <section className="admin-card">
          <h2>Build Log</h2>
          <pre className="admin-log">{log}</pre>
        </section>
      )}

      <a className="admin-back" href="/">← Kembali ke chat</a>
    </div>
  );
}

export default AdminPanel;
