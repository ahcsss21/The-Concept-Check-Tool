import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { listConcepts, listSessions, createSession } from '../api';

export default function Dashboard({ user }) {
  const [concepts, setConcepts] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const isReviewer = Boolean(user?.is_reviewer);

  useEffect(() => {
    async function load() {
      try {
        setConcepts(await listConcepts());
        setSessions(await listSessions());
      } catch (err) {
        setError(err.message);
      }
    }
    load();
  }, []);

  const handleStart = async (concept_id) => {
    try {
      const session = await createSession(concept_id);
      navigate(`/session/${session.session_id}`);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="page">
      <h1>Concept Check</h1>
      {error && <p className="small-text" style={{ color: 'red' }}>{error}</p>}

      {!isReviewer && (
        <section className="card-list">
          <div className="card">
            <h2>Which topic do you want to choose?</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '15px' }}>
              {concepts.map((concept) => (
                <button
                  key={concept.concept_id}
                  onClick={() => handleStart(concept.concept_id)}
                  style={{
                    padding: '12px 16px',
                    textAlign: 'left',
                    border: '1px solid #ccc',
                    borderRadius: '4px',
                    backgroundColor: '#ffffff',
                    color: '#000000',
                    cursor: 'pointer',
                    fontSize: '16px',
                    fontWeight: '500',
                    transition: 'background-color 0.2s, border-color 0.2s'
                  }}
                  onMouseOver={(e) => {
                    e.target.style.backgroundColor = '#4169e1';
                    e.target.style.color = '#ffffff';
                    e.target.style.borderColor = '#4169e1';
                  }}
                  onMouseOut={(e) => {
                    e.target.style.backgroundColor = '#ffffff';
                    e.target.style.color = '#000000';
                    e.target.style.borderColor = '#ccc';
                  }}
                >
                  {concept.topic_name}
                </button>
              ))}
            </div>
          </div>
        </section>
      )}

      <section className="card-list" style={{ marginTop: 30 }}>
        <div className="card">
          <h2>{isReviewer ? 'Sessions to review' : 'Your sessions'}</h2>
          {sessions.length === 0 ? (
            <p className="small-text">{isReviewer ? 'No learner sessions available yet.' : 'No sessions yet. Choose a topic above to start one.'}</p>
          ) : (
            sessions.map((session) => (
              <div key={session.session_id} className="card">
                <p>Session ID: {session.session_id}</p>
                {isReviewer && (
                  <p>Learner: {session.learner_name || 'Unknown'}{session.learner_email ? ` (${session.learner_email})` : ''}</p>
                )}
                <p>Started: {new Date(session.started_at).toLocaleString()}</p>
                <Link to={`/session/${session.session_id}`} className="link-button">{isReviewer ? 'Review session' : 'View session'}</Link>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
