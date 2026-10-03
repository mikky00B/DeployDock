import { useState, type FormEvent } from "react";

import { resendVerification, verifyEmail } from "../api/auth";
import { navigateTo } from "../routes";
import { useAuth } from "../hooks/useAuth";

type Stage = "register" | "verify";

export function RegisterPage() {
  const { signUp, completeAuth, authError, clearAuthError } = useAuth();
  const [stage, setStage] = useState<Stage>("register");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const response = await signUp({ email, password, full_name: fullName || undefined });
      if (response.email_verification_required) {
        setStage("verify");
        setNotice(`We emailed a 6-digit code to ${email}. It expires in 15 minutes.`);
      } else {
        navigateTo("/dashboard");
      }
    } catch {
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

  function clearRegisterError() {
    clearAuthError();
  }

  return (
    <main className="auth-page">
      <section className="auth-intro" aria-label="DeployDock overview">
        <div className="auth-brand-mark">DeployDock</div>
        <h1>Bring your VPS deployment flow under control.</h1>
        <p>
          Start with one server, save repeatable deploy commands, and grow into a cleaner release workflow without
          adding orchestration overhead.
        </p>
        <div className="auth-proof-grid" aria-label="Deployment workflow highlights">
          <span>Server inventory</span>
          <span>App registry</span>
          <span>Logs</span>
          <span>Rollbacks</span>
        </div>
      </section>
      <section className="auth-panel" aria-labelledby="register-title">
        <div className="auth-brand">DeployDock</div>
        {stage === "verify" ? (
          <>
            <h1 id="register-title">Check your inbox</h1>
            <p className="auth-panel-copy">Enter the 6-digit code we emailed you to finish creating your account.</p>
            {notice ? <p className="success-message">{notice}</p> : null}
            {verifyError ? <p className="form-error">{verifyError}</p> : null}
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
                {isSubmitting ? "Verifying" : "Verify and continue"}
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
            <h1 id="register-title">Create account</h1>
            <p className="auth-panel-copy">Create a local DeployDock workspace.</p>
            {authError ? <p className="form-error">{authError}</p> : null}
            <form className="auth-form" onSubmit={(event) => void handleRegister(event)}>
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
                    clearRegisterError();
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
                    clearRegisterError();
                    setPassword(event.target.value);
                  }}
                  required
                  type="password"
                  value={password}
                />
              </label>
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
          </>
        )}
      </section>
    </main>
  );
}
