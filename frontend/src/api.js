const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || res.statusText);
  }
  return res.json();
}

export const login = (payload) => request('/login', { method: 'POST', body: JSON.stringify(payload) });
export const signup = (payload) => request('/signup', { method: 'POST', body: JSON.stringify(payload) });
export const currentUser = () => request('/me');
export const logout = () => request('/logout', { method: 'POST' });
export const listConcepts = () => request('/concepts');
export const listSessions = () => request('/sessions');
export const createSession = (concept_id) => request('/sessions', { method: 'POST', body: JSON.stringify({ concept_id }) });
export const submitExplanation = (payload) => request('/explanations', { method: 'POST', body: JSON.stringify(payload) });
export const getFollowupQuestion = (session_id) => request(`/followup_questions/${session_id}`);
export const getChecklistResults = (explanation_id) => request(`/checklist_results/${explanation_id}`);
export const submitJudgment = (payload) => request('/gap_closure_judgments', { method: 'POST', body: JSON.stringify(payload) });
export const getSession = (session_id) => request(`/sessions/${session_id}`);
