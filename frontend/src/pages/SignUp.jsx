import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { signup } from '../api';

export default function SignUp({ onSignUp }) {
  const [name, setName] = useState('');
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
      const user = await signup({ name, email, password });
      onSignUp(user);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page">
      <h1>Sign Up</h1>
      <form onSubmit={handleSubmit} autoComplete="off">
        <label>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} type="text" autoComplete="off" required />
        <label>Email</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="off" required />
        <label>Password</label>
        <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="new-password" required />
        {error && <p className="small-text" style={{ color: 'red' }}>{error}</p>}
        <button type="submit" className="primary-button" disabled={submitting}>{submitting ? 'Creating account...' : 'Create account'}</button>
      </form>
      <p className="small-text">
        Already have an account? <Link to="/login">Login</Link>.
      </p>
    </div>
  );
}
