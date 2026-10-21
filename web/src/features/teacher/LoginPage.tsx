import { useState, type FormEvent } from 'react';
import { SCHOOL } from '../../config/school';
import { CheckCircleIcon } from '../../components/Icons';

interface Props {
  defaultEmail?: string;
  onSignIn: () => void;
}

/**
 * Teacher sign-in. UI preview only: nothing is checked or sent yet.
 * "Keep me signed in" will later keep the session on this phone.
 */
export function LoginPage({ defaultEmail = '', onSignIn }: Props) {
  const [email, setEmail] = useState(defaultEmail);
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSignIn();
  };

  return (
    <main className="page login">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">
          <CheckCircleIcon className="brand-icon" />
        </div>
        <div>
          <p className="brand-name">{SCHOOL.appName}</p>
          <p className="brand-tagline">{SCHOOL.appTagline}</p>
        </div>
      </div>

      <section className="card login-card" aria-labelledby="login-title">
        <h1 id="login-title">Teacher sign in</h1>
        <p className="lead">Sign in to see the class you are teaching now.</p>

        <form className="login-form" onSubmit={submit}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              className="input"
              type="email"
              inputMode="email"
              autoComplete="username"
              placeholder="name@school.edu"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <div className="password-wrap">
              <input
                id="password"
                className="input"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          <label className="checkbox">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            Keep me signed in on this phone
          </label>

          <button type="submit" className="btn btn-primary btn-block">
            Sign in
          </button>
        </form>

        <p className="demo-note">Preview only — sign-in is not connected yet. Tap “Sign in” to see the class page.</p>
      </section>
    </main>
  );
}
