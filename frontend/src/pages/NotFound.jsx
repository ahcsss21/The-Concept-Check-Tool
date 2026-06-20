import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="page">
      <h1>Page not found</h1>
      <p className="small-text">The page you are looking for does not exist.</p>
      <Link to="/" className="link-button">Go home</Link>
    </div>
  );
}
