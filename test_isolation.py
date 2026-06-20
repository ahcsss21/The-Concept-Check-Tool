"""
API-driven test script to verify:
1. Two-user isolation: User A cannot read User B's sessions or vice versa.
2. Gap-to-second-pass foreign key proof: second explanation is linked by prompted_by_question_id.
"""
from fastapi.testclient import TestClient
from app import app
from database import init_db


def run_tests():
    init_db()

    print("=" * 50)
    print("TEST 1: CREATE TWO USERS VIA API")
    print("=" * 50)

    client_a = TestClient(app)
    client_b = TestClient(app)

    resp_a = client_a.post("/signup", json={"name": "LearnerA", "email": "usera@example.com", "password": "password123"})
    resp_b = client_b.post("/signup", json={"name": "LearnerB", "email": "userb@example.com", "password": "password123"})

    assert resp_a.status_code == 200, f"Signup A failed: {resp_a.text}"
    assert resp_b.status_code == 200, f"Signup B failed: {resp_b.text}"

    print("Created User A and User B via signup endpoints")

    print("\n" + "=" * 50)
    print("TEST 2: USER A CREATES A SESSION AND FIRST EXPLANATION")
    print("=" * 50)

    resp = client_a.post("/sessions", json={"concept_id": 1})
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["session_id"]
    print(f"User A created session: {session_id}")

    resp = client_a.post("/explanations", json={
        "session_id": session_id,
        "attempt_number": 1,
        "raw_text": "Frontend uses an API to communicate with the backend."
    })
    assert resp.status_code == 200, resp.text
    print("User A submitted first explanation")

    session_data_a = client_a.get(f"/sessions/{session_id}")
    assert session_data_a.status_code == 200, session_data_a.text
    session_json_a = session_data_a.json()
    print(f"Session data for User A includes followup: {bool(session_json_a.get('followup'))}")

    followup_question_id = None
    if session_json_a.get("followup"):
        followup_question_id = session_json_a["followup"]["question_id"]
        print(f"Follow-up question id: {followup_question_id}")

    print("\n" + "=" * 50)
    print("TEST 3: USER B CANNOT ACCESS USER A'S SESSION")
    print("=" * 50)

    resp = client_b.get(f"/sessions/{session_id}")
    print(f"User B GET /sessions/{session_id} status: {resp.status_code}")
    print(resp.json())
    if resp.status_code in (403, 404):
        print("✓ ISOLATION WORKS: User B cannot read User A's session details")
    else:
        print("✗ ISOLATION FAILURE: User B was able to read User A's session")

    resp = client_b.get("/sessions")
    assert resp.status_code == 200, resp.text
    sessions_b = resp.json()
    print(f"User B sessions list contains User A's session? {any(s.get('session_id') == session_id for s in sessions_b)}")
    if not any(s.get('session_id') == session_id for s in sessions_b):
        print("✓ ISOLATION WORKS: User B's session list does not include User A's session")
    else:
        print("✗ ISOLATION FAILURE: User B sees User A's session in list")

    print("\n" + "=" * 50)
    print("TEST 4: SECOND PASS LINKAGE PROOF")
    print("=" * 50)

    if followup_question_id:
        resp = client_a.post("/explanations", json={
            "session_id": session_id,
            "attempt_number": 2,
            "raw_text": "The frontend captures the click, sends a fetch request to the backend API, the backend processes it, and the frontend updates the screen.",
            "prompted_by_question_id": followup_question_id
        })
        assert resp.status_code == 200, resp.text
        print("User A submitted second attempt linked to the follow-up question")

        session_data_a = client_a.get(f"/sessions/{session_id}").json()
        print("Session data after second attempt:")
        print({
            "followup_question_id": session_data_a.get("followup", {}).get("question_id"),
            "attempt2_prompted_by_question_id": session_data_a.get("explanation2", {}).get("prompted_by_question_id")
        })
        if session_data_a.get("followup", {}).get("question_id") == session_data_a.get("explanation2", {}).get("prompted_by_question_id"):
            print("✓ CRITICAL FK LINK: attempt 2 points back to the follow-up question.")
        else:
            print("✗ FK LINK MISSING: attempt 2 is not linked to the follow-up question.")
    else:
        print("Cannot run second-pass linkage proof because followup was not generated.")

    print("\n" + "=" * 50)
    print("ALL TESTS COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    run_tests()
