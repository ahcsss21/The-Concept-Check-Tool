import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { currentUser, getSession, getChecklistResults, submitExplanation, submitJudgment } from '../api';

export default function SessionPage({ user }) {
  const { sessionId } = useParams();
  const [viewer, setViewer] = useState(user || null);
  const [session, setSession] = useState(null);
  const [attemptText, setAttemptText] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [judgment, setJudgment] = useState(null);
  const [checklist, setChecklist] = useState(null);

  useEffect(() => {
    async function loadSession() {
      try {
        const me = await currentUser();
        setViewer(me);
        const data = await getSession(sessionId);
        setSession(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadSession();
  }, [sessionId]);

  useEffect(() => {
    async function loadChecklist() {
      if (!session?.explanation2?.explanation_id) {
        setChecklist(null);
        return;
      }
      try {
        const data = await getChecklistResults(session.explanation2.explanation_id);
        setChecklist(data);
      } catch (err) {
        setError(err.message);
      }
    }
    loadChecklist();
  }, [session]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError(null);

    try {
      const payload = {
        session_id: sessionId,
        attempt_number: session.followup ? 2 : 1,
        raw_text: attemptText,
      };
      if (session.followup) {
        payload.prompted_by_question_id = session.followup.question_id;
      }
      await submitExplanation(payload);
      setAttemptText('');
      const data = await getSession(sessionId);
      setSession(data);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleJudgment = async (gapClosed) => {
    setError(null);
    try {
      const payload = {
        session_id: sessionId,
        gap_closed: gapClosed,
        reviewer_name: 'Reviewer',
      };
      const result = await submitJudgment(payload);
      setJudgment(result);
    } catch (err) {
      setError(err.message);
    }
  };

  if (loading) {
    return <div className="page"><p>Loading session...</p></div>;
  }

  if (error) {
    return <div className="page"><p style={{ color: 'red' }}>{error}</p></div>;
  }

  const isReviewer = Boolean(session?.can_judge);
  const showFirstExplanation = !isReviewer && !session.explanation1;
  const showFollowup = !isReviewer && session.followup && !session.explanation2;
  const sessionComplete = session.explanation2 || (session.explanation1 && !session.followup);
  const latestJudgment = judgment || (session.judgments && session.judgments.length > 0 ? session.judgments[0] : null);

  return (
    <div className="page">
      <h1>Session</h1>
      <p className="small-text">Session ID: {session.session_id}</p>
      {isReviewer && (session.learner_name || session.learner_email) && (
        <p className="small-text">Learner: {session.learner_name || 'Unknown'}{session.learner_email ? ` (${session.learner_email})` : ''}</p>
      )}
      <p className="small-text">Concept: {session.concept_topic}</p>
      <p className="small-text">Description: {session.concept_description}</p>

      <div className="card-list">
        {showFirstExplanation && (
          <div className="card">
            <h2>First explanation</h2>
            <form onSubmit={handleSubmit}>
              <label>Explain the concept from first principles</label>
              <textarea value={attemptText} onChange={(e) => setAttemptText(e.target.value)} rows={8} required />
              <button type="submit" className="primary-button">Submit first explanation</button>
            </form>
          </div>
        )}

        {showFollowup && (
          <div className="card">
            <h2>Follow-up attempt</h2>
            <form onSubmit={handleSubmit}>
              <label>Answer the follow-up question</label>
              <textarea value={attemptText} onChange={(e) => setAttemptText(e.target.value)} rows={8} required />
              <p className="small-text"><strong>Follow-up:</strong> {session.followup.generated_question}</p>
              <button type="submit" className="primary-button">Submit follow-up answer</button>
            </form>
          </div>
        )}

        {sessionComplete && (
          <div className="card">
            <h2>Session complete</h2>
            {session.followup ? (
              <p className="small-text">The follow-up cycle is complete. Review the attempts below.</p>
            ) : (
              <p className="small-text">No follow-up was generated for this explanation.</p>
            )}
          </div>
        )}

        {isReviewer && !session.explanation1 && (
          <div className="card">
            <h2>Awaiting learner attempt</h2>
            <p className="small-text">This learner has not submitted attempt 1 yet.</p>
          </div>
        )}

        {isReviewer && session.explanation1 && !session.explanation2 && (
          <div className="card">
            <h2>Awaiting follow-up answer</h2>
            <p className="small-text">Learner has not submitted attempt 2 yet.</p>
          </div>
        )}

        {session.explanation1 && (
          <div className="card">
            <h3>Attempt 1</h3>
            <p>{session.explanation1.raw_text}</p>
            <p className="small-text"><strong>Exact phrase that looked memorized:</strong></p>
            <p className="gap-sentence">
              {session.explanation1.gap_sentence
                ? session.explanation1.gap_sentence
                : (session.followup
                  ? 'Not captured yet'
                  : 'No memorized phrase detected. The first explanation appears conceptually clear.')}
            </p>
          </div>
        )}

        {session.followup && (
          <div className="card">
            <h3>Follow-up question</h3>
            <p>{session.followup.generated_question}</p>
          </div>
        )}

        {session.explanation2 && (
          <div className="card">
            <h3>Attempt 2</h3>
            <p>{session.explanation2.raw_text}</p>
          </div>
        )}

        {session.explanation2 && checklist && (
          <div className="card">
            <h3>Deterministic checklist evaluation</h3>
            <p className="small-text">API/interface mention: {checklist.api_key_mention ? 'Yes' : 'No'}</p>
            <p className="small-text">Causal reasoning: {checklist.causal_reasoning ? 'Yes' : 'No'}</p>
            <p className="small-text">Concrete example: {checklist.concrete_example ? 'Yes' : 'No'}</p>
            <p className="small-text"><strong>Checklist passed:</strong> {checklist.passed ? 'Yes' : 'No'}</p>
          </div>
        )}

        {isReviewer ? (
          <div className="card">
            <h3>Human judgment</h3>
            <button type="button" className="link-button" onClick={() => handleJudgment(true)}>Mark gap closed</button>
            <button type="button" className="link-button" style={{ marginLeft: 10 }} onClick={() => handleJudgment(false)}>Mark gap open</button>
            {latestJudgment && (
              <p className="small-text">
                Last judgment: {latestJudgment.gap_closed ? 'Closed' : 'Open'}{latestJudgment.reviewer_name ? ` by ${latestJudgment.reviewer_name}` : ''}
              </p>
            )}
          </div>
        ) : (
          <div className="card">
            <h3>Final outcome</h3>
            {latestJudgment ? (
              <p className="small-text">
                {latestJudgment.gap_closed
                  ? 'Gap closed — you demonstrated understanding.'
                  : 'Gap open — your explanation missed key reasoning or examples.'}
              </p>
            ) : (
              <p className="small-text">Awaiting evaluator review.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
