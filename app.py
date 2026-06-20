import os
import hashlib
import secrets
import re
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import requests
import openai
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from database import init_db, get_db
from models import (
    Learner,
    Concept,
    LoginToken,
    Session,
    Explanation,
    FollowupQuestion,
    GapJudgment,
    ChecklistResult,
)

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
IS_PRODUCTION = os.getenv("RENDER", "") == "true" or os.getenv("IS_PRODUCTION", "") == "true"
REVIEWER_EMAILS = {
    email.strip().lower()
    for email in os.getenv("REVIEWER_EMAILS", "").split(",")
    if email.strip()
}

if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

app = FastAPI(title="Concept Check API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SignUpRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SessionCreate(BaseModel):
    concept_id: int


class ExplanationCreate(BaseModel):
    session_id: str
    attempt_number: int
    raw_text: str
    prompted_by_question_id: Optional[str] = None


class GapJudgmentCreate(BaseModel):
    session_id: str
    gap_closed: bool
    reviewer_name: Optional[str] = None
    override_reason: Optional[str] = None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_auth_token(db: DBSession, learner_id: str) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    login_token = LoginToken(
        learner_id=learner_id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(hours=12),
        used=False,
    )
    db.add(login_token)
    db.commit()
    return token


def get_current_learner(request: Request, db = Depends(get_db)):
    token = request.cookies.get("auth_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    login_token = (
        db.query(LoginToken)
        .filter(LoginToken.token_hash == token_hash)
        .filter(LoginToken.expires_at > datetime.utcnow())
        .first()
    )
    if not login_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired auth token")

    learner = db.query(Learner).filter(Learner.learner_id == login_token.learner_id).first()
    if not learner:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Learner not found")

    database_url = os.getenv("DATABASE_URL", "sqlite:///./concept_check.db")
    if database_url.startswith("postgres"):
        db.execute(text("SET LOCAL app.current_learner = :learner_id"), {"learner_id": learner.learner_id})

    return learner


def get_session_for_learner(db = Depends(get_db), session_id: str = None, learner_id: str = None):
    session = (
        db.query(Session)
        .filter(Session.session_id == session_id)
        .filter(Session.learner_id == learner_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session not found or access denied")
    return session


def is_reviewer_account(learner: Learner) -> bool:
    return learner.email.lower() in REVIEWER_EMAILS


def generate_followup_question(raw_text: str, concept_name: str) -> Optional[dict]:
    prompt_text = (
        "You evaluate a learner's first explanation for conceptual understanding.\n"
        "Decision rule:\n"
        "- Respond NO_FOLLOWUP only when the explanation is concrete and mechanistic, not just abstractly correct\n"
        "- If explanation has a memorized/label-like weak line: return exactly two lines\n"
        "  GAP: <exact quote from learner text where understanding breaks>\n"
        "  FOLLOWUP: <one custom question that probes that exact gap; no generic templates>\n\n"
        "Treat it as weak/memorized if any of these are true:\n"
        "- mostly abstract definitions with no concrete runtime example\n"
        "- polished claims without showing what is exchanged, checked, or executed\n"
        "- generic causal statement (e.g., 'otherwise system fails') without mechanism\n\n"
        "Constraints for FOLLOWUP:\n"
        "- Must be grounded in the GAP quote\n"
        "- Must test whether learner truly understands that specific claim\n"
        "- Do not ask broad concept-overview questions\n"
        "- Do not use fixed reusable wording patterns"
    )
    user_content = f"Concept: {concept_name}\nLearner explanation:\n{raw_text}"

    def extract_memorized_phrase(text: str) -> Optional[str]:
        stripped = text.strip()
        if not stripped:
            return None
        # Prefer the first sentence because vague answers are usually short label statements.
        first_sentence = re.split(r"[.?!]", stripped)[0].strip()
        return first_sentence or stripped[:200]

    def appears_conceptually_weak(text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return True

        words = re.findall(r"\w+", stripped.lower())
        word_count = len(words)
        if word_count < 8:
            return True

        has_example = any(k in stripped.lower() for k in ["for example", "such as", "e.g.", "example"])
        has_causal = any(k in stripped.lower() for k in ["because", "therefore", "so that", "as a result", "leads to", "why"])
        has_mechanism = any(k in stripped.lower() for k in ["how", "step", "flow", "request", "response", "store", "retrieve", "query", "process"])

        # Generic one-liners often look polished but lack mechanism depth.
        generic_patterns = [
            r"\bthey communicate through\b",
            r"\bbridge between\b",
            r"\bhelps systems\b",
            r"\bcode\b",
        ]
        looks_generic = any(re.search(p, stripped.lower()) for p in generic_patterns)

        if looks_generic and not has_mechanism:
            return True
        if not has_example and not has_causal and not has_mechanism:
            return True
        return False

    def generate_question_for_phrase(phrase: str) -> Optional[str]:
        if not GROQ_API_KEY and not OPENAI_API_KEY:
            return None

        question_prompt = (
            "Write exactly one follow-up question. "
            "The question must test understanding of the quoted weak phrase. "
            "Do not ask generic concept overview questions. "
            "Keep it short and specific."
        )
        question_user = (
            f"Concept: {concept_name}\n"
            f"Weak phrase from learner answer: \"{phrase}\"\n"
            f"Learner full answer: {raw_text}"
        )

        if GROQ_API_KEY:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            candidate_models = [GROQ_MODEL, "llama-3.1-8b-instant"]
            seen = set()
            for candidate in candidate_models:
                if not candidate or candidate in seen:
                    continue
                seen.add(candidate)
                try:
                    payload = {
                        "model": candidate,
                        "messages": [
                            {"role": "system", "content": question_prompt},
                            {"role": "user", "content": question_user},
                        ],
                        "temperature": 0.0,
                        "max_tokens": 120,
                    }
                    resp = requests.post(url, json=payload, headers=headers, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    question = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if question:
                        q_match = re.search(r"([^?]*\?)", question, re.DOTALL)
                        return q_match.group(1).strip() if q_match else question
                except Exception:
                    continue

        if OPENAI_API_KEY:
            try:
                messages = [
                    {"role": "system", "content": question_prompt},
                    {"role": "user", "content": question_user},
                ]
                response = openai.ChatCompletion.create(
                    model=OPENAI_MODEL,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=120,
                )
                question = response.choices[0].message.content.strip()
                if question:
                    q_match = re.search(r"([^?]*\?)", question, re.DOTALL)
                    return q_match.group(1).strip() if q_match else question
            except Exception:
                pass
        return None

    def parse_response(output: str) -> Optional[dict]:
        if not output:
            return None
        normalized = output.strip()
        if re.match(r"^\s*NO_FOLLOWUP\b", normalized, re.IGNORECASE):
            # Guardrail: if model says NO_FOLLOWUP but answer is clearly weak/vague,
            # force a phrase-targeted follow-up to preserve the core product behavior.
            if appears_conceptually_weak(raw_text):
                phrase = extract_memorized_phrase(raw_text)
                if phrase:
                    generated = generate_question_for_phrase(phrase)
                    return {
                        "gap_sentence": phrase,
                        "generated_question": generated or f"You wrote '{phrase}'. What exactly do you mean by that here, and can you show one concrete mechanism?",
                    }
            return None

        gap_sentence = None
        generated_question = None

        # Parse both single-line and multi-line formats robustly.
        gap_match = re.search(r"GAP:\s*(.+?)(?:\n\s*FOLLOWUP:|$)", normalized, re.IGNORECASE | re.DOTALL)
        followup_match = re.search(r"FOLLOWUP:\s*(.+)$", normalized, re.IGNORECASE | re.DOTALL)

        if gap_match:
            gap_sentence = gap_match.group(1).strip().strip('"')
        if followup_match:
            generated_question = followup_match.group(1).strip()

        if not generated_question:
            if "?" in normalized:
                question_match = re.search(r"([^?]*\?)", normalized, re.DOTALL)
                generated_question = question_match.group(1).strip() if question_match else normalized

        if not gap_sentence:
            first_sentence = re.split(r"[.?!]", raw_text.strip())[0].strip() if raw_text.strip() else None
            gap_sentence = first_sentence or (raw_text.strip()[:200] if raw_text.strip() else None)

        if not generated_question:
            # If parser could not extract FOLLOWUP but text is weak, recover with phrase-targeted question.
            if appears_conceptually_weak(raw_text):
                phrase = gap_sentence or extract_memorized_phrase(raw_text)
                if phrase:
                    generated = generate_question_for_phrase(phrase)
                    if generated:
                        generated_question = generated
            if not generated_question:
                return None

        return {"gap_sentence": gap_sentence, "generated_question": generated_question}

    if GROQ_API_KEY:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        candidate_models = [GROQ_MODEL, "llama-3.1-8b-instant", "llama-3.1-70b-versatile"]
        seen = set()
        for candidate in candidate_models:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            try:
                payload = {
                    "model": candidate,
                    "messages": [
                        {"role": "system", "content": prompt_text},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 220,
                }
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                output = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                parsed = parse_response(output)
                if parsed is not None:
                    return parsed
            except Exception:
                continue

    if OPENAI_API_KEY:
        messages = [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": user_content},
        ]
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.0,
            max_tokens=180,
        )
        return parse_response(response.choices[0].message.content.strip())

    # If no model is available, still enforce core behavior for clearly weak answers.
    if appears_conceptually_weak(raw_text):
        phrase = extract_memorized_phrase(raw_text)
        if phrase:
            return {
                "gap_sentence": phrase,
                "generated_question": f"You wrote '{phrase}'. What exactly do you mean by that here, and can you explain one concrete step-by-step example?",
            }
    return None



def evaluate_checklist(raw_text: str) -> dict:
    text_lower = raw_text.lower()
    result = {
        "word_count": len(raw_text.split()),
        "api_key_mention": "api" in text_lower or "interface" in text_lower,
        "causal_reasoning": any(k in text_lower for k in ["because", "therefore", "so", "thus", "as a result", "leads to"]),
        "concrete_example": any(k in text_lower for k in ["for example", "such as", "like", "e.g.", "instance"]),
    }
    result["passed"] = result["api_key_mention"] and result["causal_reasoning"] and result["concrete_example"]
    return result


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok"}


@app.post("/signup", tags=["auth"])
def signup(request: SignUpRequest, db = Depends(get_db)):
    existing = db.query(Learner).filter(Learner.email == request.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    learner = Learner(
        name=request.name,
        email=request.email,
        password_hash=hash_password(request.password),
    )
    db.add(learner)
    db.commit()
    db.refresh(learner)
    auth_token = create_auth_token(db, learner.learner_id)

    response = {
        "learner_id": learner.learner_id,
        "name": learner.name,
        "email": learner.email,
        "is_reviewer": is_reviewer_account(learner),
    }
    fastapi_response = JSONResponse(content=response)
    fastapi_response.set_cookie(
        "auth_token", auth_token,
        httponly=True,
        max_age=43200,
        samesite="none" if IS_PRODUCTION else "lax",
        secure=IS_PRODUCTION,
    )
    return fastapi_response


@app.post("/login", tags=["auth"])
def login(request: LoginRequest, db = Depends(get_db)):
    learner = db.query(Learner).filter(Learner.email == request.email).first()
    if not learner or not verify_password(request.password, learner.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    auth_token = create_auth_token(db, learner.learner_id)
    response = {
        "learner_id": learner.learner_id,
        "name": learner.name,
        "email": learner.email,
        "is_reviewer": is_reviewer_account(learner),
    }
    fastapi_response = JSONResponse(content=response)
    fastapi_response.set_cookie(
        "auth_token", auth_token,
        httponly=True,
        max_age=43200,
        samesite="none" if IS_PRODUCTION else "lax",
        secure=IS_PRODUCTION,
    )
    return fastapi_response


@app.post("/logout", tags=["auth"])
def logout():
    response = JSONResponse(content={"message": "logged out"})
    response.delete_cookie("auth_token")
    return response


@app.get("/me", tags=["auth"])
def current_user(request: Request, db = Depends(get_db)):
    learner = get_current_learner(request, db)
    return {
        "learner_id": learner.learner_id,
        "name": learner.name,
        "email": learner.email,
        "is_reviewer": is_reviewer_account(learner),
    }


@app.get("/concepts", tags=["content"])
def list_concepts(db = Depends(get_db)):
    concepts = db.query(Concept).order_by(Concept.concept_id).all()
    return [{"concept_id": c.concept_id, "topic_name": c.topic_name, "description": c.description} for c in concepts]


@app.get("/sessions", tags=["sessions"])
def list_sessions(request: Request, db = Depends(get_db)):
    learner = get_current_learner(request, db)
    if is_reviewer_account(learner):
        sessions = db.query(Session).order_by(Session.started_at.desc()).all()
    else:
        sessions = db.query(Session).filter(Session.learner_id == learner.learner_id).order_by(Session.started_at.desc()).all()
    return [
        {
            "session_id": s.session_id,
            "concept_id": s.concept_id,
            "started_at": s.started_at.isoformat(),
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "learner_id": s.learner_id,
            "learner_name": s.learner.name if s.learner else None,
            "learner_email": s.learner.email if s.learner else None,
        }
        for s in sessions
    ]


@app.post("/sessions", tags=["sessions"])
def create_session(request: SessionCreate, db = Depends(get_db), current_user = Depends(get_current_learner)):
    session = Session(learner_id=current_user.learner_id, concept_id=request.concept_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"session_id": session.session_id}


@app.get("/sessions/{session_id}", tags=["sessions"])
def get_session(request: Request, session_id: str, db = Depends(get_db)):
    learner = get_current_learner(request, db)
    can_judge = is_reviewer_account(learner)
    if is_reviewer_account(learner):
        session = db.query(Session).filter(Session.session_id == session_id).first()
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    else:
        session = get_session_for_learner(db, session_id, learner.learner_id)
    explanation1 = (
        db.query(Explanation)
        .filter(Explanation.session_id == session_id, Explanation.attempt_number == 1)
        .first()
    )
    explanation2 = (
        db.query(Explanation)
        .filter(Explanation.session_id == session_id, Explanation.attempt_number == 2)
        .first()
    )
    followup = None
    if explanation1:
        followup = (
            db.query(FollowupQuestion)
            .filter(FollowupQuestion.explanation_id == explanation1.explanation_id)
            .first()
        )
    judgments = (
        db.query(GapJudgment)
        .filter(GapJudgment.session_id == session_id)
        .order_by(GapJudgment.judged_at.desc())
        .all()
    )
    return {
        "session_id": session.session_id,
        "concept_id": session.concept_id,
        "learner_id": session.learner_id,
        "learner_name": session.learner.name if session.learner else None,
        "learner_email": session.learner.email if session.learner else None,
        "can_judge": can_judge,
        "started_at": session.started_at.isoformat(),
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        "explanation1": {
            "explanation_id": explanation1.explanation_id,
            "raw_text": explanation1.raw_text,
            "gap_sentence": explanation1.gap_sentence,
        } if explanation1 else None,
        "concept_topic": session.concept.topic_name,
        "concept_description": session.concept.description,
        "explanation2": {
            "explanation_id": explanation2.explanation_id,
            "raw_text": explanation2.raw_text,
            "prompted_by_question_id": explanation2.prompted_by_question_id,
        } if explanation2 else None,
        "followup": {
            "question_id": followup.question_id,
            "generated_question": followup.generated_question,
            "gap_identified": followup.gap_identified,
        } if followup else None,
        "judgments": [
            {"judgment_id": j.judgment_id, "gap_closed": j.gap_closed, "reviewer_name": j.reviewer_name, "override_reason": j.override_reason, "judged_at": j.judged_at.isoformat()} for j in judgments
        ],
    }


@app.post("/explanations", tags=["explanations"])
def submit_explanation(request: ExplanationCreate, db = Depends(get_db), current_user = Depends(get_current_learner)):
    session = get_session_for_learner(db, request.session_id, current_user.learner_id)
    if request.attempt_number not in (1, 2):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="attempt_number must be 1 or 2")

    if request.attempt_number == 2:
        first_attempt = (
            db.query(Explanation)
            .filter(Explanation.session_id == request.session_id, Explanation.attempt_number == 1)
            .first()
        )
        if not first_attempt:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="First attempt must exist before second attempt")

    followup_payload = None
    followup_result = None
    gap_sentence = None
    if request.attempt_number == 1:
        concept = db.query(Concept).filter(Concept.concept_id == session.concept_id).first()
        followup_result = generate_followup_question(request.raw_text, concept.topic_name)
        if followup_result:
            gap_sentence = followup_result.get("gap_sentence")

    explanation = Explanation(
        session_id=request.session_id,
        attempt_number=request.attempt_number,
        raw_text=request.raw_text,
        word_count=len(request.raw_text.split()),
        prompted_by_question_id=request.prompted_by_question_id,
        gap_sentence=gap_sentence,
    )
    db.add(explanation)
    db.commit()
    db.refresh(explanation)

    if request.attempt_number == 1 and followup_result:
        followup = FollowupQuestion(
            explanation_id=explanation.explanation_id,
            generated_question=followup_result["generated_question"],
            gap_identified=followup_result.get("gap_sentence") or ""
        )
        db.add(followup)
        db.commit()
        db.refresh(followup)
        followup_payload = {
            "question_id": followup.question_id,
            "generated_question": followup.generated_question,
        }

    return {
        "explanation_id": explanation.explanation_id,
        "followup_question": followup_payload,
    }


@app.get("/followup_questions/{session_id}", tags=["followup_questions"])
def get_followup_question(session_id: str, request: Request, db = Depends(get_db)):
    learner = get_current_learner(request, db)
    session = get_session_for_learner(db, session_id, learner.learner_id)
    explanation1 = (
        db.query(Explanation)
        .filter(Explanation.session_id == session.session_id, Explanation.attempt_number == 1)
        .first()
    )
    if not explanation1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt 1 not found")
    followup = (
        db.query(FollowupQuestion)
        .filter(FollowupQuestion.explanation_id == explanation1.explanation_id)
        .first()
    )
    if not followup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow-up question not found")
    return {
        "question_id": followup.question_id,
        "generated_question": followup.generated_question,
        "gap_identified": followup.gap_identified,
    }


@app.get("/checklist_results/{explanation_id}", tags=["checklist_results"])
def get_checklist_results(explanation_id: str, request: Request, db = Depends(get_db)):
    learner = get_current_learner(request, db)
    explanation_query = (
        db.query(Explanation)
        .join(Session, Session.session_id == Explanation.session_id)
        .filter(Explanation.explanation_id == explanation_id)
    )
    if not is_reviewer_account(learner):
        explanation_query = explanation_query.filter(Session.learner_id == learner.learner_id)
    explanation = explanation_query.first()
    if not explanation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Explanation not found")

    checklist = db.query(ChecklistResult).filter(ChecklistResult.explanation_id == explanation_id).first()
    if checklist:
        return {
            "explanation_id": explanation_id,
            "api_key_mention": checklist.api_key_mention,
            "causal_reasoning": checklist.causal_reasoning,
            "concrete_example": checklist.concrete_example,
            "passed": checklist.passed,
            "evaluated_at": checklist.evaluated_at.isoformat(),
        }

    result = evaluate_checklist(explanation.raw_text)
    checklist = ChecklistResult(
        explanation_id=explanation_id,
        api_key_mention=result["api_key_mention"],
        causal_reasoning=result["causal_reasoning"],
        concrete_example=result["concrete_example"],
        passed=result["passed"],
    )
    db.add(checklist)
    db.commit()
    db.refresh(checklist)
    return {
        "explanation_id": explanation_id,
        "api_key_mention": checklist.api_key_mention,
        "causal_reasoning": checklist.causal_reasoning,
        "concrete_example": checklist.concrete_example,
        "passed": checklist.passed,
        "evaluated_at": checklist.evaluated_at.isoformat(),
    }


@app.post("/gap_closure_judgments", tags=["judgments"])
def create_gap_closure_judgment(request: GapJudgmentCreate, db = Depends(get_db), current_user = Depends(get_current_learner)):
    if not is_reviewer_account(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only reviewer accounts can submit human judgment")

    session = db.query(Session).filter(Session.session_id == request.session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    judgment = GapJudgment(
        session_id=session.session_id,
        gap_closed=request.gap_closed,
        reviewer_name=request.reviewer_name or current_user.name,
        override_reason=request.override_reason,
    )
    db.add(judgment)
    db.commit()
    db.refresh(judgment)
    return {
        "judgment_id": judgment.judgment_id,
        "session_id": judgment.session_id,
        "gap_closed": judgment.gap_closed,
        "reviewer_name": judgment.reviewer_name,
        "override_reason": judgment.override_reason,
        "judged_at": judgment.judged_at.isoformat(),
    }


@app.get("/gap_closure_judgments/{session_id}", tags=["judgments"])
def list_gap_closure_judgments(session_id: str, request: Request, db = Depends(get_db)):
    learner = get_current_learner(request, db)
    get_session_for_learner(db, session_id, learner.learner_id)
    judgments = (
        db.query(GapJudgment)
        .filter(GapJudgment.session_id == session_id)
        .order_by(GapJudgment.judged_at.desc())
        .all()
    )
    return [
        {
            "judgment_id": j.judgment_id,
            "gap_closed": j.gap_closed,
            "reviewer_name": j.reviewer_name,
            "override_reason": j.override_reason,
            "judged_at": j.judged_at.isoformat(),
        }
        for j in judgments
    ]
