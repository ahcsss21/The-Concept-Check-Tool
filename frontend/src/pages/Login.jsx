import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { login } from '../api';

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const user = await login({ email, password });
      onLogin(user);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page">
      <h1>Login</h1>
      <form onSubmit={handleSubmit} autoComplete="off">
        <label>Email</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="off" required />
        <label>Password</label>
        <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="new-password" required />
        {error && <p className="small-text" style={{ color: 'red' }}>{error}</p>}
        <button type="submit" className="primary-button" disabled={submitting}>{submitting ? 'Signing in...' : 'Sign In'}</button>
      </form>
      <p className="small-text">
        Don’t have an account? <Link to="/signup">Create one</Link>.
      </p>
    </div>
  );
}
