import { useState, type FormEvent } from "react";

import { navigateTo } from "../routes";
import { useAuth } from "../hooks/useAuth";

export function RegisterPage() {
  const { signUp, authError, clearAuthError } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await signUp({ email, password, full_name: fullName || undefined });
      navigateTo("/dashboard");
    } catch {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="register-title">
        <div className="auth-brand">DeployDock</div>
        <h1 id="register-title">Create account</h1>
        <form className="auth-form" onSubmit={(event) => void handleSubmit(event)}>
          <label>
            Full name
            <input
              autoComplete="name"
              name="full_name"
              onChange={(event) => setFullName(event.target.value)}
              type="text"
              value={fullName}
            />
          </label>
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
              autoComplete="new-password"
              minLength={8}
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
            {isSubmitting ? "Creating account" : "Create account"}
          </button>
        </form>
        <p className="auth-switch">
          Already registered?{" "}
          <button type="button" onClick={() => navigateTo("/login")}>
            Sign in
          </button>
        </p>
      </section>
    </main>
  );
}
