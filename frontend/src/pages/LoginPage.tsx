import { useState, type FormEvent } from "react";

import { navigateTo } from "../routes";
import { useAuth } from "../hooks/useAuth";

export function LoginPage() {
  const { signIn, authError, clearAuthError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await signIn({ email, password });
      navigateTo("/dashboard");
    } catch {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-intro" aria-label="DeployDock overview">
        <div className="auth-brand-mark">DeployDock</div>
        <h1>Ship VPS apps from one quiet control room.</h1>
        <p>
          Connect servers, register deploy commands, watch rollout history, and keep service operations in one focused
          workspace.
        </p>
        <div className="auth-proof-grid" aria-label="Deployment workflow highlights">
          <span>SSH deploys</span>
          <span>Service restarts</span>
          <span>Audit trail</span>
          <span>Health checks</span>
        </div>
      </section>
      <section className="auth-panel" aria-labelledby="login-title">
        <div className="auth-brand">DeployDock</div>
        <h1 id="login-title">Sign in</h1>
        <p className="auth-panel-copy">Enter your workspace credentials to continue.</p>
        <form className="auth-form" onSubmit={(event) => void handleSubmit(event)}>
          <label>
            Email
            <input
              autoComplete="email"
              name="email"
              onChange={(event) => {
                clearAuthError();
                setEmail(event.target.value);
              }}
              required
              type="email"
              value={email}
            />
          </label>
          <label>
            Password
            <input
              autoComplete="current-password"
              name="password"
              onChange={(event) => {
                clearAuthError();
                setPassword(event.target.value);
              }}
              required
              type="password"
              value={password}
            />
          </label>
          {authError ? <p className="form-error">{authError}</p> : null}
          <button className="primary-button" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Signing in" : "Sign in"}
          </button>
        </form>
        <p className="auth-switch">
          No account yet?{" "}
          <button type="button" onClick={() => navigateTo("/register")}>
            Create one
          </button>
        </p>
      </section>
    </main>
  );
}
