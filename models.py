from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()

def generate_id():
    return str(uuid.uuid4())[:8]

class Learner(Base):
    __tablename__ = 'learners'
    learner_id = Column(String, primary_key=True, default=generate_id)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("Session", back_populates="learner")
    tokens = relationship("LoginToken", back_populates="learner")

class Concept(Base):
    __tablename__ = 'concepts'
    concept_id = Column(Integer, primary_key=True)
    topic_name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    seeded = Column(Boolean, default=True)

    sessions = relationship("Session", back_populates="concept")

class LoginToken(Base):
    __tablename__ = 'login_tokens'
    token_id = Column(String, primary_key=True, default=generate_id)
    learner_id = Column(String, ForeignKey('learners.learner_id'))
    token_hash = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)

    learner = relationship("Learner", back_populates="tokens")

class Session(Base):
    __tablename__ = 'sessions'
    session_id = Column(String, primary_key=True, default=generate_id)
    learner_id = Column(String, ForeignKey('learners.learner_id'))  # ◯ ISOLATION BOUNDARY ◯
    concept_id = Column(Integer, ForeignKey('concepts.concept_id'))
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    learner = relationship("Learner", back_populates="sessions")
    concept = relationship("Concept", back_populates="sessions")
    explanations = relationship("Explanation", back_populates="session")
    judgments = relationship("GapJudgment", back_populates="session")
    checklists = relationship("ChecklistResult", back_populates="session")

class Explanation(Base):
    __tablename__ = 'explanations'
    explanation_id = Column(String, primary_key=True, default=generate_id)
    session_id = Column(String, ForeignKey('sessions.session_id'))
    attempt_number = Column(Integer)  # 1 or 2
    raw_text = Column(Text)
    word_count = Column(Integer)
    gap_detected = Column(Boolean, default=False)
    gap_sentence = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    prompted_by_question_id = Column(String, ForeignKey('followup_questions.question_id'), nullable=True)  # ◯ CRITICAL FK ◯

    session = relationship("Session", back_populates="explanations")
    checklists = relationship("ChecklistResult", back_populates="explanation")

class FollowupQuestion(Base):
    __tablename__ = 'followup_questions'
    question_id = Column(String, primary_key=True, default=generate_id)
    explanation_id = Column(String, ForeignKey('explanations.explanation_id'))
    generated_question = Column(Text, nullable=False)
    gap_identified = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    # No complex back-populate - keep it simple

class GapJudgment(Base):
    __tablename__ = 'gap_judgments'
    judgment_id = Column(String, primary_key=True, default=generate_id)
    session_id = Column(String, ForeignKey('sessions.session_id'))
    gap_closed = Column(Boolean, nullable=False)
    reviewer_name = Column(String, nullable=False)
    override_reason = Column(Text, nullable=True)
    judged_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="judgments")

class ChecklistResult(Base):
    __tablename__ = 'checklist_results'
    result_id = Column(String, primary_key=True, default=generate_id)
    session_id = Column(String, ForeignKey('sessions.session_id'))
    explanation_id = Column(String, ForeignKey('explanations.explanation_id'), nullable=True)
    api_key_mention = Column(Boolean, default=False)
    causal_reasoning = Column(Boolean, default=False)
    concrete_example = Column(Boolean, default=False)
    passed = Column(Boolean, default=False)
    evaluated_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("Session", back_populates="checklists")
    explanation = relationship("Explanation", back_populates="checklists")