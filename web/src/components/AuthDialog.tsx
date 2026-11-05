import { useEffect, useRef, useState } from "preact/hooks";
import { api, ApiError, errorText } from "../api";

/**
 * Token entry shown when the API answers 401. The token is sent once to
 * POST /v1/session, which sets an HttpOnly cookie; it is not kept in state
 * after submission, nor written to storage or URLs.
 */
export function AuthDialog({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => inputRef.current?.focus(), []);

  async function submit(e: Event) {
    e.preventDefault();
    const input = inputRef.current;
    const token = input?.value.trim() ?? "";
    if (!token) {
      setError("Enter the API token.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.createSession(token);
      if (input) input.value = "";
      onAuthenticated();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Token rejected." : errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div class="modal-backdrop">
      <form
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-title"
        aria-describedby="auth-desc"
        onSubmit={submit}
      >
        <h2 id="auth-title">Sign in to the workbench</h2>
        <p id="auth-desc" class="muted">
          The API requires an access token. It is exchanged for an HttpOnly session cookie and is not stored by this
          page.
        </p>
        <label class="field">
          <span>API token</span>
          <input
            ref={inputRef}
            type="password"
            name="token"
            autoComplete="off"
            spellcheck={false}
            required
            disabled={busy}
          />
        </label>
        {error && (
          <p class="alert alert-error" role="alert">
            {error}
          </p>
        )}
        <div class="row end">
          <button class="btn btn-primary" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </div>
      </form>
    </div>
  );
}
