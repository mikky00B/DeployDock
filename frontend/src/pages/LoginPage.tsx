import { useState, type FormEvent } from "react";

import { navigateTo } from "../routes";
import { resendVerification, verifyEmail } from "../api/auth";
import { useAuth } from "../hooks/useAuth";

const UNVERIFIED_PREFIX = "Email not verified";

type Stage = "login" | "verify";

export function LoginPage() {
  const { signIn, completeAuth, authError, clearAuthError } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [stage, setStage] = useState<Stage>("login");
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const response = await signIn({ email, password });
      if (response.email_verification_required) {
        // Unverified account: signIn surfaced a fresh code; collect it here.
        setStage("verify");
        setNotice("We emailed you a 6-digit code to verify this account.");
        setIsSubmitting(false);
        return;
      }
      navigateTo("/dashboard");
    } catch (error) {
      // The hook populates authError; detect the unverified gate from the
      // thrown message and switch to the code form.
      if (error instanceof Error && error.message.startsWith(UNVERIFIED_PREFIX)) {
        setStage("verify");
        setNotice("We emailed you a 6-digit code to verify this account.");
      }
      setIsSubmitting(false);
    }
  }

  async function handleVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setVerifyError(null);
    try {
      const response = await verifyEmail({ email, code });
      completeAuth(response);
      navigateTo("/dashboard");
    } catch (verifyError_) {
      setVerifyError(verifyError_ instanceof Error ? verifyError_.message : "Could not verify the code");
      setIsSubmitting(false);
    }
  }

  async function handleResend() {
    setIsSubmitting(true);
    setVerifyError(null);
    try {
      await resendVerification({ email });
      setNotice("A new code is on its way. It expires in 15 minutes.");
    } catch {
      setVerifyError("Could not resend the code");
    } finally {
      setIsSubmitting(false);
    }
  }

  const shownError = stage === "login" ? authError : verifyError;

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
        {stage === "verify" ? (
          <>
            <h1 id="login-title">Verify your email</h1>
            <p className="auth-panel-copy">
              Enter the 6-digit code we sent to <b>{email}</b> to finish signing in.
            </p>
            {notice ? <p className="success-message">{notice}</p> : null}
            {shownError ? <p className="form-error">{shownError}</p> : null}
            <form className="auth-form" onSubmit={(event) => void handleVerify(event)}>
              <label>
                Verification code
                <input
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  maxLength={6}
                  name="code"
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                  pattern="\d{6}"
                  required
                  value={code}
                />
              </label>
              <button className="primary-button" disabled={isSubmitting || code.length !== 6} type="submit">
                {isSubmitting ? "Verifying" : "Verify and sign in"}
              </button>
            </form>
            <p className="auth-switch">
              Didn't get it?{" "}
              <button type="button" onClick={() => void handleResend()}>
                Send a new code
              </button>
            </p>
          </>
        ) : (
          <>
            <h1 id="login-title">Sign in</h1>
            <p className="auth-panel-copy">Enter your workspace credentials to continue.</p>
            {authError ? <p className="form-error">{authError}</p> : null}
            <form className="auth-form" onSubmit={(event) => void handleLogin(event)}>
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
          </>
        )}
      </section>
    </main>
  );
}
