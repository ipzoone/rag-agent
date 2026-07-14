/**
 * Admin Panel API client.
 *
 * Endpoints are EdgeOne Makers agent functions (POST-only). They require:
 *   - Content-Type: application/json
 *   - a non-empty JSON body
 *   - the makers-conversation-id header (enforced by the agents/ runtime)
 *
 * Auth is a simple token gate: login with ADMIN_PASSWORD to get a token,
 * then send it in the body of every protected call. The token is persisted
 * in localStorage so the dashboard stays logged in across refreshes.
 */

const ADMIN_TOKEN_KEY = "rag_admin_token";
const ADMIN_CID_KEY = "rag_admin_cid";

function getAdminCid(): string {
  let cid = localStorage.getItem(ADMIN_CID_KEY);
  if (!cid) {
    cid = "admin-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(ADMIN_CID_KEY, cid);
  }
  return cid;
}

function getToken(): string {
  return localStorage.getItem(ADMIN_TOKEN_KEY) || "";
}

function setToken(t: string): void {
  localStorage.setItem(ADMIN_TOKEN_KEY, t);
}

export function clearAdminToken(): void {
  localStorage.removeItem(ADMIN_TOKEN_KEY);
}

async function adminFetch(path: string, payload: Record<string, unknown>): Promise<any> {
  const res = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "makers-conversation-id": getAdminCid(),
    },
    body: JSON.stringify(payload),
  });
  return res.json().catch(() => ({}));
}

export const adminApi = {
  isLoggedIn: () => !!getToken(),

  login: async (password: string): Promise<boolean> => {
    const data = await adminFetch("/admin-login", { password });
    if (data?.ok && data?.token) {
      setToken(data.token);
      return true;
    }
    return false;
  },

  logout: () => clearAdminToken(),

  listFiles: () => adminFetch("/admin-files", { token: getToken() }),

  upload: (filename: string, dataBase64: string) =>
    adminFetch("/admin-upload", { token: getToken(), filename, data: dataBase64 }),

  remove: (filename: string) =>
    adminFetch("/admin-delete", { token: getToken(), filename }),

  rebuild: () => adminFetch("/admin-rebuild", { token: getToken() }),
};

/** Read a File as a base64 data URL (prefix preserved; backend strips it). */
export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
