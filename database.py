import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import Base, Concept

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./concept_check.db")
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def configure_postgres_rls(engine):
    if DATABASE_URL.startswith("postgres"):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE IF EXISTS sessions ENABLE ROW LEVEL SECURITY;"))
            conn.execute(
                text(
                    "CREATE POLICY IF NOT EXISTS learner_isolation ON sessions "
                    "FOR SELECT USING (learner_id = current_setting('app.current_learner', true));"
                )
            )


def ensure_sqlite_schema():
    if DATABASE_URL.startswith("sqlite"):
        with engine.begin() as conn:
            result = conn.execute(text("PRAGMA table_info('checklist_results');")).fetchall()
            columns = [row[1] for row in result]
            if "explanation_id" not in columns:
                conn.execute(text("ALTER TABLE checklist_results ADD COLUMN explanation_id TEXT"))


def init_db():
    """Create tables and seed concepts"""
    Base.metadata.create_all(bind=engine)
    configure_postgres_rls(engine)
    ensure_sqlite_schema()

    # Seed concepts if not exists
    db = SessionLocal()
    if db.query(Concept).count() == 0:
        concepts = [
            {"topic_name": "Interfaces", "description": "How software components connect and communicate."},
            {"topic_name": "Backend fundamentals", "description": "Why server-side systems exist behind the browser."},
            {"topic_name": "Frontend vs Backend", "description": "How client-side and server-side roles differ."},
            {"topic_name": "Data storage", "description": "Different ways to preserve and retrieve application data."},
            {"topic_name": "Database fundamentals", "description": "Why systems need a database to manage structured state."},
            {"topic_name": "Storage selection", "description": "How to choose different storage options based on requirements."}
        ]
        for i, c in enumerate(concepts, 1):
            db.add(Concept(concept_id=i, **c))
        db.commit()
    else:
        updates = {
            "What is an interface, really?": ("Interfaces", "How software components connect and communicate."),
            "Interfaces": ("Interfaces", "How software components connect and communicate."),
            "Backend existence": ("Backend fundamentals", "Why server-side systems exist behind the browser."),
            "Backend fundamentals": ("Backend fundamentals", "Why server-side systems exist behind the browser."),
            "Frontend vs Backend": ("Frontend vs Backend", "How client-side and server-side roles differ."),
            "Data storage options": ("Data storage", "Different ways to preserve and retrieve application data."),
            "Data storage": ("Data storage", "Different ways to preserve and retrieve application data."),
            "Database fundamentals": ("Database fundamentals", "Why systems need a database to manage structured state."),
            "Storage selection factors": ("Storage selection", "How to choose different storage options based on requirements."),
            "Storage selection": ("Storage selection", "How to choose different storage options based on requirements."),
        }
        updated = False
        for concept in db.query(Concept).filter(Concept.seeded == True).all():
            if concept.topic_name in updates:
                new_topic, new_description = updates[concept.topic_name]
                concept.topic_name = new_topic
                concept.description = new_description
                updated = True
        if updated:
            db.commit()
    db.close()

def get_db():
    """Dependency for FastAPI routes"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()