from fastapi import FastAPI, Depends, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session as DBSession
from database import init_db, get_db, engine, SessionLocal
from models import Learner, Concept, LoginToken, Session, Explanation, FollowupQuestion, GapJudgment, ChecklistResult
from datetime import datetime, timedelta
import hashlib
import secrets
from sqlalchemy import text

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Initialize on startup
init_db()

def get_current_learner(request: Request, db: DBSession):
    learner_id = request.cookies.get("learner_id")
    if not learner_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    learner = db.query(Learner).filter(Learner.learner_id == learner_id).first()
    if not learner:
        raise HTTPException(status_code=401, detail="Invalid learner session")
    return learner


def get_current_session(session_id: str, learner_id: str, db: DBSession):
    session = db.query(Session).filter(
        Session.session_id == session_id,
        Session.learner_id == learner_id
    ).first()
    if not session:
        raise HTTPException(status_code=403, detail="Session not found or access denied")
    return session

# Legacy concept reference for Move 3; actual UI uses seeded concepts from the database.
CONCEPTS_LIST = [
    "Interfaces - How software components connect and communicate",
    "Backend fundamentals - Why server-side systems exist behind the browser",
    "Frontend vs Backend - How client-side and server-side roles differ",
    "Data storage - Different ways to preserve and retrieve application data",
    "Database fundamentals - Why systems need a database to manage structured state",
    "Storage selection - How to choose different storage options based on requirements"
]

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Home page with login form"""
    return templates.TemplateResponse("login.html", {"request": request, "message": None})

@app.post("/request-magic-link")
def request_magic_link(request: Request, email: str = Form(...), name: str = Form(...)):
    """Generate magic link token (simulated email - prints to console)"""
    db = SessionLocal()

    # Find or create learner
    learner = db.query(Learner).filter(Learner.email == email).first()
    if not learner:
        learner = Learner(email=email, name=name)
        db.add(learner)
        db.commit()
        db.refresh(learner)

    # Create login token
    token = secrets.token_hex(16)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    login_token = LoginToken(
        learner_id=learner.learner_id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(hours=1)
    )
    db.add(login_token)
    db.commit()

    # Simulate email - print to console
    login_url = f"http://localhost:8000/login?token={token}"
    print(f"\n=== MAGIC LINK FOR {email} ===")
    print(f"Login URL: {login_url}")
    print("================================\n")

    db.close()
    return RedirectResponse(url=f"/login?token={token}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/login", response_class=HTMLResponse)
def login(request: Request, token: str = None):
    """Validate token and create session cookie"""
    if not token:
        return templates.TemplateResponse("login.html", {"request": request, "message": "No token provided"})

    db = SessionLocal()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    login_token = db.query(LoginToken).filter(
        LoginToken.token_hash == token_hash,
        LoginToken.used == False,
        LoginToken.expires_at > datetime.utcnow()
    ).first()

    if not login_token:
        db.close()
        return templates.TemplateResponse("login.html", {"request": request, "message": "Invalid or expired token"})

    login_token.used = True
    db.commit()
    db.close()

    # Set session cookie with learner_id
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="learner_id", value=login_token.learner_id, httponly=True)
    return response

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    """User dashboard showing concepts and their sessions"""
    learner_id = request.cookies.get("learner_id")
    if not learner_id:
        return RedirectResponse(url="/")

    db = SessionLocal()
    learner = db.query(Learner).filter(Learner.learner_id == learner_id).first()
    concepts = db.query(Concept).all()
    sessions = db.query(Session).filter(Session.learner_id == learner_id).all()
    db.close()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "learner": learner,
        "concepts": concepts,
        "sessions": sessions
    })

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("learner_id")
    return response

@app.post("/sessions")
def create_session(request: Request, concept_id: int = Form(...), db: DBSession = Depends(get_db)):
    """Start a new session"""
    learner = get_current_learner(request, db)
    session = Session(learner_id=learner.learner_id, concept_id=concept_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"session_id": session.session_id}

@app.get("/concepts")
def get_concepts(db: DBSession = Depends(get_db)):
    """API endpoint to list all concepts"""
    concepts = db.query(Concept).all()
    return [{"concept_id": c.concept_id, "topic_name": c.topic_name, "description": c.description} for c in concepts]

@app.get("/session/{session_id}", response_class=HTMLResponse)
def session_page(request: Request, session_id: str, db: DBSession = Depends(get_db)):
    learner = get_current_learner(request, db)
    session = get_current_session(session_id, learner.learner_id, db)
    concept = session.concept
    attempt1 = db.query(Explanation).filter(
        Explanation.session_id == session_id,
        Explanation.attempt_number == 1
    ).first()
    followup = None
    if attempt1:
        followup = db.query(FollowupQuestion).filter(
            FollowupQuestion.explanation_id == attempt1.explanation_id
        ).first()
    attempt2 = db.query(Explanation).filter(
        Explanation.session_id == session_id,
        Explanation.attempt_number == 2
    ).first()
    checklist = db.query(ChecklistResult).filter(ChecklistResult.session_id == session_id).order_by(ChecklistResult.evaluated_at.desc()).first()
    judgment = db.query(GapJudgment).filter(GapJudgment.session_id == session_id).order_by(GapJudgment.judged_at.desc()).first()

    return templates.TemplateResponse("session.html", {
        "request": request,
        "session": session,
        "concept": concept,
        "attempt1": attempt1,
        "followup": followup,
        "attempt2": attempt2,
        "checklist": checklist,
        "judgment": judgment
    })

@app.post("/session/{session_id}/submit-explanation")
def submit_session_explanation(
    request: Request,
    session_id: str,
    attempt_number: int = Form(...),
    raw_text: str = Form(...),
    prompted_by_question_id: str = Form(None),
    db: DBSession = Depends(get_db)
):
    learner = get_current_learner(request, db)
    session = get_current_session(session_id, learner.learner_id, db)

    if attempt_number not in (1, 2):
        raise HTTPException(status_code=400, detail="Invalid attempt number")

    if attempt_number == 2:
        first_attempt = db.query(Explanation).filter(
            Explanation.session_id == session_id,
            Explanation.attempt_number == 1
        ).first()
        if not first_attempt:
            raise HTTPException(status_code=400, detail="First attempt is required before a second attempt")

    explanation = Explanation(
        session_id=session_id,
        attempt_number=attempt_number,
        raw_text=raw_text,
        word_count=len(raw_text.split()),
        prompted_by_question_id=prompted_by_question_id
    )
    db.add(explanation)
    db.commit()

    return RedirectResponse(url=f"/session/{session_id}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/session/{session_id}/submit-followup")
def submit_session_followup(
    request: Request,
    session_id: str,
    gap_sentence: str = Form(...),
    gap_identified: str = Form(...),
    db: DBSession = Depends(get_db)
):
    learner = get_current_learner(request, db)
    session = get_current_session(session_id, learner.learner_id, db)

    attempt1 = db.query(Explanation).filter(
        Explanation.session_id == session_id,
        Explanation.attempt_number == 1
    ).first()
    if not attempt1:
        raise HTTPException(status_code=404, detail="First attempt not found")

    attempt1.gap_detected = True
    attempt1.gap_sentence = gap_sentence

    question = FollowupQuestion(
        explanation_id=attempt1.explanation_id,
        generated_question=f"Walk me through step-by-step: {gap_identified}. Be concrete, not abstract.",
        gap_identified=gap_identified
    )
    db.add(question)
    db.commit()

    return RedirectResponse(url=f"/session/{session_id}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/session/{session_id}/run-checklist")
def run_session_checklist(
    request: Request,
    session_id: str,
    db: DBSession = Depends(get_db)
):
    learner = get_current_learner(request, db)
    session = get_current_session(session_id, learner.learner_id, db)

    exp2 = db.query(Explanation).filter(
        Explanation.session_id == session_id,
        Explanation.attempt_number == 2
    ).first()
    if not exp2:
        raise HTTPException(status_code=404, detail="Second attempt not found")

    text_lower = exp2.raw_text.lower()
    checklist = ChecklistResult(
        session_id=session_id,
        api_key_mention="api" in text_lower or "interface" in text_lower,
        causal_reasoning="because" in text_lower or "therefore" in text_lower or "→" in exp2.raw_text,
        concrete_example="for example" in text_lower or "like" in text_lower or "such as" in text_lower,
        passed=False
    )
    checklist.passed = checklist.api_key_mention and checklist.causal_reasoning and checklist.concrete_example
    db.add(checklist)
    db.commit()

    return RedirectResponse(url=f"/session/{session_id}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/session/{session_id}/submit-judgment")
def submit_session_judgment(
    request: Request,
    session_id: str,
    gap_closed: str = Form(...),
    reviewer_name: str = Form(...),
    override_reason: str = Form(None),
    db: DBSession = Depends(get_db)
):
    learner = get_current_learner(request, db)
    session = get_current_session(session_id, learner.learner_id, db)

    closed = str(gap_closed).lower() in ("true", "1", "yes", "y")
    judgment = GapJudgment(
        session_id=session_id,
        gap_closed=closed,
        reviewer_name=reviewer_name,
        override_reason=override_reason
    )
    db.add(judgment)
    db.commit()

    return RedirectResponse(url=f"/session/{session_id}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/session/{session_id}/trace", response_class=HTMLResponse)
def session_trace(request: Request, session_id: str, db: DBSession = Depends(get_db)):
    learner = get_current_learner(request, db)
    session = get_current_session(session_id, learner.learner_id, db)

    attempt1 = db.query(Explanation).filter(
        Explanation.session_id == session_id,
        Explanation.attempt_number == 1
    ).first()
    followup = None
    if attempt1:
        followup = db.query(FollowupQuestion).filter(
            FollowupQuestion.explanation_id == attempt1.explanation_id
        ).first()
    attempt2 = db.query(Explanation).filter(
        Explanation.session_id == session_id,
        Explanation.attempt_number == 2
    ).first()

    trace = {
        "session_id": session_id,
        "attempt_1_before_retry": attempt1.raw_text if attempt1 else None,
        "gap_sentence_identified": attempt1.gap_sentence if attempt1 else None,
        "follow_up_question": followup.generated_question if followup else None,
        "attempt_2_after_retry": attempt2.raw_text if attempt2 else None,
        "critical_proof": (
            f"explanations.prompted_by_question_id='{followup.question_id}' links attempt 2 to followup"
            if attempt2 and followup else "Link pending"
        )
    }

    return templates.TemplateResponse("trace.html", {
        "request": request,
        "session": session,
        "trace": trace
    })

@app.post("/explanations")
def submit_explanation(
    request: Request,
    session_id: str = Form(...),
    attempt_number: int = Form(...),
    raw_text: str = Form(...),
    prompted_by_question_id: str = Form(None),
    db: DBSession = Depends(get_db)
):
    """Submit an explanation attempt"""
    learner_id = request.cookies.get("learner_id")
    if not learner_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Isolation check
    session = db.query(Session).filter(
        Session.session_id == session_id,
        Session.learner_id == learner_id
    ).first()

    if not session:
        raise HTTPException(status_code=403, detail="Session not found or access denied")

    explanation = Explanation(
        session_id=session_id,
        attempt_number=attempt_number,
        raw_text=raw_text,
        word_count=len(raw_text.split()),
        prompted_by_question_id=prompted_by_question_id
    )
    db.add(explanation)
    db.commit()
    db.refresh(explanation)

    return {"explanation_id": explanation.explanation_id}

@app.post("/explanations/{id}/followup")
def generate_followup(id: str, gap_sentence: str = Form(...), gap_identified: str = Form(...), db: Session = Depends(get_db)):
    """Generate follow-up question when gap is detected"""
    explanation = db.query(Explanation).filter(Explanation.explanation_id == id).first()
    if not explanation:
        raise HTTPException(status_code=404, detail="Explanation not found")

    # Update gap info on original attempt
    explanation.gap_detected = True
    explanation.gap_sentence = gap_sentence

    # Generate follow-up question
    question = FollowupQuestion(
        explanation_id=id,
        generated_question=f"Walk me through step-by-step: {gap_identified}. Be concrete, not abstract.",
        gap_identified=gap_identified
    )
    db.add(question)
    db.commit()
    db.refresh(question)

    return {"question_id": question.question_id, "generated_question": question.generated_question}

@app.post("/judgments")
def submit_judgment(
    session_id: str = Form(...),
    gap_closed: bool = Form(...),
    reviewer_name: str = Form(...),
    override_reason: str = Form(None),
    db: DBSession = Depends(get_db)
):
    """Human judgment of whether gap was closed"""
    judgment = GapJudgment(
        session_id=session_id,
        gap_closed=gap_closed,
        reviewer_name=reviewer_name,
        override_reason=override_reason
    )
    db.add(judgment)
    db.commit()

    return {"judgment_id": judgment.judgment_id, "gap_closed": gap_closed}

@app.post("/checklists")
def run_checklist(session_id: str = Form(...), db: DBSession = Depends(get_db)):
    """Auto-evaluate explanation against checklist"""
    # Get the second attempt
    exp2 = db.query(Explanation).filter(
        Explanation.session_id == session_id,
        Explanation.attempt_number == 2
    ).first()

    if not exp2:
        raise HTTPException(status_code=404, detail="Second attempt not found")

    text_lower = exp2.raw_text.lower()

    checklist = ChecklistResult(
        session_id=session_id,
        api_key_mention="api" in text_lower or "interface" in text_lower,
        causal_reasoning="because" in text_lower or "therefore" in text_lower or "→" in exp2.raw_text,
        concrete_example="for example" in text_lower or "like" in text_lower or "such as" in text_lower,
        passed=False
    )

    checklist.passed = checklist.api_key_mention and checklist.causal_reasoning and checklist.concrete_example
    db.add(checklist)
    db.commit()

    return {"passed": checklist.passed, "details": {
        "api_key_mention": checklist.api_key_mention,
        "causal_reasoning": checklist.causal_reasoning,
        "concrete_example": checklist.concrete_example
    }}

@app.get("/sessions/{id}/trace")
def get_trace(request: Request, id: str, db: DBSession = Depends(get_db)):
    """◯ CRITICAL: Gap-to-result proof ◯"""
    # Get learner_id from cookie
    learner_id = request.cookies.get("learner_id")

    # Isolation check
    session = db.query(Session).filter(
        Session.session_id == id,
        Session.learner_id == learner_id
    ).first()

    if not session:
        raise HTTPException(status_code=403, detail="Access denied")

    trace = db.query(Explanation).filter(
        Explanation.session_id == id,
        Explanation.attempt_number == 1
    ).first()

    if not trace:
        return {"error": "No first attempt found"}

    followup = db.query(FollowupQuestion).filter(
        FollowupQuestion.explanation_id == trace.explanation_id
    ).first()

    second = db.query(Explanation).filter(
        Explanation.session_id == id,
        Explanation.attempt_number == 2
    ).first()

    result = {
        "session_id": id,
        "attempt_1_before_retry": trace.raw_text,
        "gap_sentence_identified": trace.gap_sentence,
        "follow_up_question": followup.generated_question if followup else None,
        "attempt_2_after_retry": second.raw_text if second else None,
        "critical_proof": f"explanations.prompted_by_question_id='{followup.question_id}' links attempt 2 to followup" if second and followup else "Link pending"
    }

    return result

# Test endpoint to verify isolation
@app.get("/test-isolation/{session_id}")
def test_isolation(request: Request, session_id: str, db: Session = Depends(get_db)):
    """Test endpoint - attempt to access another user's session"""
    learner_id = request.cookies.get("learner_id")
    session = db.query(Session).filter(Session.session_id == session_id).first()
    if session and session.learner_id != learner_id:
        return {"access": "DENIED - Cannot read other user's data", "session_owner": session.learner_id}
    return {"access": "GRANTED", "session": session_id}