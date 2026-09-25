"""Stage 3–5 prototype: accounts, collaboration, indicators, scenarios, discovery and exports.

No claim of production-grade security or policy causality. All datasets and indicators
must be supplied with their real provenance. No fabricated government data.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import os
import secrets
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field

from .gis import geo_connection

router = APIRouter(prefix="/platform", tags=["Research Platform"])
DB_URL = os.getenv("DATABASE_URL", "postgresql://bhoomi:bhoomi_dev_only@localhost:5433/bhoomiai")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
BOOTSTRAP_KEY = os.getenv("BOOTSTRAP_KEY", "")


def conn():
    return psycopg.connect(DB_URL)


def init_platform_database():
    with conn() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS platform_users(
            id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN
            ('admin','researcher','official','viewer')), active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW())""")
        db.execute("""CREATE TABLE IF NOT EXISTS research_projects(
            id BIGSERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
            region TEXT DEFAULT '', created_by BIGINT REFERENCES platform_users(id),
            created_at TIMESTAMPTZ DEFAULT NOW())""")
        db.execute("""CREATE TABLE IF NOT EXISTS project_members(
            project_id BIGINT REFERENCES research_projects(id) ON DELETE CASCADE,
            user_id BIGINT REFERENCES platform_users(id) ON DELETE CASCADE,
            PRIMARY KEY(project_id,user_id))""")
        db.execute("""CREATE TABLE IF NOT EXISTS research_notes(
            id BIGSERIAL PRIMARY KEY, project_id BIGINT REFERENCES research_projects(id)
            ON DELETE CASCADE, author_id BIGINT REFERENCES platform_users(id),
            body TEXT NOT NULL, source_url TEXT DEFAULT '', document_id BIGINT
            REFERENCES documents(id) ON DELETE SET NULL,
            review_status TEXT NOT NULL DEFAULT 'pending' CHECK
            (review_status IN ('pending','confirmed','rejected')),
            reviewed_by BIGINT REFERENCES platform_users(id), created_at
            TIMESTAMPTZ DEFAULT NOW())""")
        db.execute("""CREATE TABLE IF NOT EXISTS innovation_challenges(
            id BIGSERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
            deadline DATE, created_by BIGINT REFERENCES platform_users(id),
            created_at TIMESTAMPTZ DEFAULT NOW())""")
        db.execute("""CREATE TABLE IF NOT EXISTS challenge_submissions(
            id BIGSERIAL PRIMARY KEY, challenge_id BIGINT REFERENCES innovation_challenges(id)
            ON DELETE CASCADE, submitted_by BIGINT REFERENCES platform_users(id),
            title TEXT NOT NULL, abstract TEXT NOT NULL, created_at
            TIMESTAMPTZ DEFAULT NOW())""")
        db.execute("""CREATE TABLE IF NOT EXISTS land_indicators(
            id BIGSERIAL PRIMARY KEY, state TEXT NOT NULL, district TEXT NOT NULL,
            year INTEGER NOT NULL, indicator TEXT NOT NULL, value DOUBLE PRECISION NOT NULL,
            unit TEXT NOT NULL, source_url TEXT NOT NULL, dataset_name TEXT NOT NULL,
            entered_by BIGINT REFERENCES platform_users(id), created_at
            TIMESTAMPTZ DEFAULT NOW())""")
        db.execute("""CREATE TABLE IF NOT EXISTS platform_audit(
            id BIGSERIAL PRIMARY KEY, actor_id BIGINT REFERENCES platform_users(id),
            event TEXT NOT NULL, target TEXT NOT NULL, created_at
            TIMESTAMPTZ DEFAULT NOW())""")


def password_hash(password):
    salt = secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 350000)
    return salt.hex() + ":" + hashed.hex()


def password_matches(password, stored):
    try:
        salt, hashed = stored.split(":")
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 350000)
        return hmac.compare_digest(test, bytes.fromhex(hashed))
    except (ValueError, TypeError):
        return False


def serializer():
    if len(SESSION_SECRET) < 32 or SESSION_SECRET.startswith("REPLACE"):
        raise HTTPException(503, "Configure a random SESSION_SECRET (at least 32 characters) in backend/.env.")
    return URLSafeTimedSerializer(SESSION_SECRET, salt="bhoomiai-session-v1")


def authenticate_token(token):
    if not token:
        raise HTTPException(401, "Sign in to use BhoomiAI.")
    try:
        payload = serializer().loads(token, max_age=8*60*60)
    except SignatureExpired as exc:
        raise HTTPException(401, "Your session expired. Sign in again.") from exc
    except BadSignature as exc:
        raise HTTPException(401, "Invalid session.") from exc
    try:
        with conn() as db:
            user = db.execute(
                "SELECT id,name,email,role FROM platform_users WHERE id=%s AND active=TRUE",
                (int(payload["uid"]),)).fetchone()
    except (ValueError, KeyError, TypeError):
        user = None
    if not user:
        raise HTTPException(401, "Account is unavailable.")
    return {"id": user[0], "name": user[1], "email": user[2], "role": user[3]}


def current_user(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Sign in first.")
    return user


def require_admin(request: Request):
    user = current_user(request)
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access required.")
    return user


def audit(db, user_id, event, target):
    db.execute("INSERT INTO platform_audit(actor_id,event,target) VALUES (%s,%s,%s)",
               (user_id,event,str(target)))


class AccountIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=250)
    password: str = Field(min_length=12, max_length=200)


class BootstrapIn(AccountIn):
    setup_key: str


@router.post("/auth/bootstrap")
def bootstrap_account(body: BootstrapIn):
    if len(BOOTSTRAP_KEY) < 20 or BOOTSTRAP_KEY.startswith("REPLACE"):
        raise HTTPException(503, "Set BOOTSTRAP_KEY in backend/.env first.")
    if not hmac.compare_digest(body.setup_key, BOOTSTRAP_KEY):
        raise HTTPException(403, "Invalid setup key.")
    with conn() as db:
        db.execute("SELECT pg_advisory_xact_lock(725001)")
        if db.execute("SELECT 1 FROM platform_users LIMIT 1").fetchone():
            raise HTTPException(409, "An account already exists. Ask the admin to invite you.")
        uid = db.execute(
            "INSERT INTO platform_users(name,email,password_hash,role) "
            "VALUES (%s,%s,%s,'admin') RETURNING id",
            (body.name.strip(),body.email.lower().strip(),password_hash(body.password))).fetchone()[0]
        audit(db,uid,"bootstrap_admin",uid)
    return {"created": True, "user_id": uid}


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn):
    with conn() as db:
        user = db.execute("SELECT id,name,email,role,password_hash FROM platform_users "
                          "WHERE email=%s AND active=TRUE",
                          (body.email.lower().strip(),)).fetchone()
    if not user or not password_matches(body.password, user[4]):
        raise HTTPException(401, "Invalid email or password.")
    return {"access_token": serializer().dumps({"uid":user[0]}),
            "user":{"id":user[0],"name":user[1],"email":user[2],"role":user[3]},
            "expires_in_seconds":28800}


@router.get("/auth/me")
def me(user=Depends(current_user)):
    return user


class InviteIn(AccountIn):
    role: Literal["researcher","official","viewer"] = "researcher"


@router.post("/users", status_code=201)
def create_user(body: InviteIn, user=Depends(require_admin)):
    try:
        with conn() as db:
            uid=db.execute("INSERT INTO platform_users(name,email,password_hash,role) "
                           "VALUES (%s,%s,%s,%s) RETURNING id",
                           (body.name.strip(),body.email.lower().strip(),
                            password_hash(body.password),body.role)).fetchone()[0]
            audit(db,user["id"],"create_user",uid)
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "Email already registered.") from exc
    return {"id":uid,"email":body.email.lower().strip(),"role":body.role}


@router.get("/users")
def list_users(user=Depends(require_admin)):
    with conn() as db:
        rows=db.execute("SELECT id,name,email,role,active FROM platform_users ORDER BY id").fetchall()
    return [{"id":r[0],"name":r[1],"email":r[2],"role":r[3],"active":r[4]} for r in rows]


class ProjectIn(BaseModel):
    title: str = Field(min_length=3,max_length=200)
    description: str = Field(min_length=3,max_length=2000)
    region: str = Field(default="",max_length=150)


def can_view_project(db, project_id, user):
    row=db.execute("SELECT created_by FROM research_projects WHERE id=%s",(project_id,)).fetchone()
    if not row:
        raise HTTPException(404,"Project not found.")
    if user["role"]=="admin" or row[0]==user["id"]:
        return
    member=db.execute("SELECT 1 FROM project_members WHERE project_id=%s AND user_id=%s",
                      (project_id,user["id"])).fetchone()
    if not member:
        raise HTTPException(403,"Not a member of this project.")


@router.get("/projects")
def projects(user=Depends(current_user)):
    with conn() as db:
        rows=db.execute(
            """SELECT p.id,p.title,p.description,p.region,p.created_at,
                      p.created_by FROM research_projects p
               WHERE %s='admin' OR p.created_by=%s OR EXISTS(
                   SELECT 1 FROM project_members pm WHERE pm.project_id=p.id AND pm.user_id=%s)
               ORDER BY p.created_at DESC""",
            (user["role"],user["id"],user["id"])).fetchall()
    return [{"id":r[0],"title":r[1],"description":r[2],"region":r[3],
             "created_at":r[4].isoformat(),"owner_id":r[5]} for r in rows]


@router.post("/projects",status_code=201)
def new_project(body:ProjectIn,user=Depends(current_user)):
    if user["role"]=="viewer":
        raise HTTPException(403,"Read-only account.")
    with conn() as db:
        pid=db.execute("INSERT INTO research_projects(title,description,region,created_by) "
                       "VALUES (%s,%s,%s,%s) RETURNING id",
                       (body.title,body.description,body.region,user["id"])).fetchone()[0]
        audit(db,user["id"],"new_project",pid)
    return {"id":pid,**body.model_dump()}


class MemberIn(BaseModel):
    user_id:int


@router.post("/projects/{project_id}/members")
def add_member(project_id:int,body:MemberIn,user=Depends(current_user)):
    with conn() as db:
        can_view_project(db,project_id,user)
        owner=db.execute("SELECT created_by FROM research_projects WHERE id=%s",
                         (project_id,)).fetchone()[0]
        if user["role"]!="admin" and user["id"]!=owner:
            raise HTTPException(403,"Project owner or admin required.")
        if not db.execute("SELECT 1 FROM platform_users WHERE id=%s",(body.user_id,)).fetchone():
            raise HTTPException(404,"Member does not exist.")
        db.execute("INSERT INTO project_members(project_id,user_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                   (project_id,body.user_id))
        audit(db,user["id"],"add_project_member",project_id)
    return {"added":body.user_id}


class NoteIn(BaseModel):
    body:str=Field(min_length=3,max_length=10000)
    source_url:str=Field(default="",max_length=1000)
    document_id:int|None=None


@router.get("/projects/{project_id}/notes")
def notes(project_id:int,user=Depends(current_user)):
    with conn() as db:
        can_view_project(db,project_id,user)
        rows=db.execute(
            """SELECT n.id,n.body,n.source_url,n.document_id,n.review_status,
                      u.name,n.created_at FROM research_notes n
               JOIN platform_users u ON u.id=n.author_id
               WHERE n.project_id=%s ORDER BY n.created_at DESC""",
            (project_id,)).fetchall()
    return [{"id":r[0],"body":r[1],"source_url":r[2],"document_id":r[3],
             "review_status":r[4],"author":r[5],"created_at":r[6].isoformat()} for r in rows]


@router.post("/projects/{project_id}/notes",status_code=201)
def add_note(project_id:int,body:NoteIn,user=Depends(current_user)):
    if user["role"]=="viewer":
        raise HTTPException(403,"Read-only account.")
    with conn() as db:
        can_view_project(db,project_id,user)
        if body.document_id and not db.execute(
            "SELECT 1 FROM documents WHERE id=%s",(body.document_id,)).fetchone():
            raise HTTPException(404,"Referenced document does not exist.")
        nid=db.execute(
            "INSERT INTO research_notes(project_id,author_id,body,source_url,document_id) "
            "VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (project_id,user["id"],body.body,body.source_url,body.document_id)).fetchone()[0]
        audit(db,user["id"],"add_evidence",nid)
    return {"id":nid,"status":"pending"}


class ReviewIn(BaseModel):
    decision:Literal["confirmed","rejected"]


@router.post("/notes/{note_id}/review")
def review(note_id:int,body:ReviewIn,user=Depends(current_user)):
    if user["role"]=="viewer":
        raise HTTPException(403,"Read-only account.")
    with conn() as db:
        note=db.execute("SELECT project_id,author_id FROM research_notes WHERE id=%s",
                        (note_id,)).fetchone()
        if not note:
            raise HTTPException(404,"Note not found.")
        can_view_project(db,note[0],user)
        if user["id"]==note[1]:
            raise HTTPException(409,"Another researcher must review this note.")
        db.execute("UPDATE research_notes SET review_status=%s,reviewed_by=%s WHERE id=%s",
                   (body.decision,user["id"],note_id))
        audit(db,user["id"],"review_"+body.decision,note_id)
    return {"id":note_id,"decision":body.decision}


class ChallengeIn(BaseModel):
    title:str=Field(min_length=3,max_length=200)
    description:str=Field(min_length=5,max_length=3000)
    deadline:str|None=None


@router.get("/challenges")
def challenges(user=Depends(current_user)):
    with conn() as db:
        rows=db.execute("SELECT id,title,description,deadline FROM innovation_challenges "
                        "ORDER BY created_at DESC").fetchall()
    return [{"id":r[0],"title":r[1],"description":r[2],
             "deadline":r[3].isoformat() if r[3] else None} for r in rows]


@router.post("/challenges",status_code=201)
def new_challenge(body:ChallengeIn,user=Depends(require_admin)):
    try:
        due=datetime.fromisoformat(body.deadline).date() if body.deadline else None
    except ValueError as exc:
        raise HTTPException(422,"Use YYYY-MM-DD for deadline.") from exc
    with conn() as db:
        cid=db.execute("INSERT INTO innovation_challenges(title,description,deadline,created_by) "
                       "VALUES(%s,%s,%s,%s) RETURNING id",
                       (body.title,body.description,due,user["id"])).fetchone()[0]
        audit(db,user["id"],"new_challenge",cid)
    return {"id":cid}


class SubmissionIn(BaseModel):
    title:str=Field(min_length=3,max_length=200)
    abstract:str=Field(min_length=10,max_length=5000)


@router.post("/challenges/{challenge_id}/submissions",status_code=201)
def submit_challenge(challenge_id:int,body:SubmissionIn,user=Depends(current_user)):
    if user["role"]=="viewer":
        raise HTTPException(403,"Read-only account.")
    with conn() as db:
        if not db.execute("SELECT 1 FROM innovation_challenges WHERE id=%s",
                          (challenge_id,)).fetchone():
            raise HTTPException(404,"Challenge not found.")
        sid=db.execute("INSERT INTO challenge_submissions(challenge_id,submitted_by,title,abstract)"
                       " VALUES(%s,%s,%s,%s) RETURNING id",
                       (challenge_id,user["id"],body.title,body.abstract)).fetchone()[0]
        audit(db,user["id"],"challenge_submission",sid)
    return {"id":sid}


class IndicatorIn(BaseModel):
    state:str=Field(min_length=2,max_length=100)
    district:str=Field(min_length=2,max_length=100)
    year:int=Field(ge=1990,le=2100)
    indicator:str=Field(min_length=2,max_length=120)
    value:float
    unit:str=Field(min_length=1,max_length=50)
    source_url:str=Field(min_length=8,max_length=1000)
    dataset_name:str=Field(min_length=3,max_length=200)


@router.post("/indicators",status_code=201)
def add_indicator(body:IndicatorIn,user=Depends(require_admin)):
    if not body.source_url.startswith(("https://","http://")):
        raise HTTPException(422,"Provide an original source URL.")
    with conn() as db:
        iid=db.execute(
            "INSERT INTO land_indicators(state,district,year,indicator,value,unit,"
            "source_url,dataset_name,entered_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (*body.model_dump().values(),user["id"])).fetchone()[0]
        audit(db,user["id"],"add_indicator",iid)
    return {"id":iid}


@router.get("/indicators")
def indicators(state:str="",district:str="",indicator:str="",user=Depends(current_user)):
    with conn() as db:
        rows=db.execute(
            """SELECT id,state,district,year,indicator,value,unit,source_url,dataset_name
               FROM land_indicators WHERE (%s='' OR state ILIKE %s)
               AND (%s='' OR district ILIKE %s)
               AND (%s='' OR indicator ILIKE %s)
               ORDER BY year,indicator LIMIT 2000""",
            (state,state,district,district,indicator,indicator)).fetchall()
    return [{"id":r[0],"state":r[1],"district":r[2],"year":r[3],"indicator":r[4],
             "value":r[5],"unit":r[6],"source_url":r[7],"dataset_name":r[8]} for r in rows]


class ScenarioIn(BaseModel):
    total_area_ha:float=Field(gt=0,le=1e9)
    baseline_conversion_ha:float=Field(ge=0,le=1e9)
    proposed_restriction_fraction:float=Field(ge=0,le=1)
    assumed_compliance_fraction:float=Field(ge=0,le=1)


def scenario_calculation(b):
    """Transparent arithmetic, not a fitted model or causal policy-effect estimate."""
    if b.baseline_conversion_ha > b.total_area_ha:
        raise ValueError("Baseline conversion cannot exceed total area.")
    avoided=b.baseline_conversion_ha*b.proposed_restriction_fraction*b.assumed_compliance_fraction
    return {"baseline_conversion_ha":round(b.baseline_conversion_ha,3),
            "hypothetical_conversion_ha":round(b.baseline_conversion_ha-avoided,3),
            "hypothetical_avoided_conversion_ha":round(avoided,3),
            "total_area_ha":b.total_area_ha,
            "formula":"avoided = baseline_conversion × restriction_fraction × compliance_fraction",
            "assumptions":"All inputs are user-provided. No displacement, price, migration or enforcement effects are modelled.",
            "warning":"Illustrative scenario arithmetic only; NOT a forecast or measured policy impact."}


@router.post("/scenarios")
def scenario(body:ScenarioIn,user=Depends(current_user)):
    try:
        return scenario_calculation(body)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@router.get("/insights")
def research_insights(user=Depends(current_user)):
    """Counts describe ONLY the indexed repository, never nationwide coverage."""
    with conn() as db:
        rows=db.execute(
            "SELECT COALESCE(NULLIF(state,''),'Unspecified'),"
            " COALESCE(NULLIF(district,''),'Unspecified'),COUNT(*) "
            "FROM documents GROUP BY 1,2 ORDER BY COUNT(*) DESC").fetchall()
        totals=db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    return {"total_indexed_documents":totals,
            "by_region":[{"state":r[0],"district":r[1],"count":r[2]} for r in rows],
            "interpretation":"Repository coverage only. Missing documents do not prove a scientific research gap."}


@router.get("/graph")
def research_graph(user=Depends(current_user)):
    """Deterministic evidence graph using recorded documents, regions and projects."""
    nodes,edges=[],[]
    with conn() as db:
        docs=db.execute("SELECT id,title,filename,state,district FROM documents LIMIT 250").fetchall()
        for did,title,filename,state,district in docs:
            did_key=f"doc:{did}"
            nodes.append({"id":did_key,"label":title or filename,"type":"document"})
            if state:
                key=f"state:{state.casefold()}"
                nodes.append({"id":key,"label":state,"type":"state"})
                edges.append({"source":did_key,"target":key,"relation":"tagged_with"})
            if district:
                key=f"district:{(state or '').casefold()}:{district.casefold()}"
                nodes.append({"id":key,"label":district,"type":"district"})
                edges.append({"source":did_key,"target":key,"relation":"tagged_with"})
        project_rows=db.execute(
            "SELECT id,title FROM research_projects WHERE %s='admin' OR created_by=%s "
            "OR EXISTS(SELECT 1 FROM project_members WHERE project_id=research_projects.id AND user_id=%s) "
            "LIMIT 100",(user["role"],user["id"],user["id"])).fetchall()
        for pid,title in project_rows:
            nodes.append({"id":f"project:{pid}","label":title,"type":"project"})
            refs=db.execute("SELECT DISTINCT document_id FROM research_notes "
                            "WHERE project_id=%s AND document_id IS NOT NULL",(pid,)).fetchall()
            edges.extend({"source":f"project:{pid}","target":f"doc:{d[0]}",
                          "relation":"research_note_evidence"} for d in refs)
    unique={n["id"]:n for n in nodes}
    return {"nodes":list(unique.values()),"edges":edges,
            "note":"Relationships come from explicit metadata and research notes, not inferred causal links."}


@router.get("/recommendations/{document_id}")
def recommendations(document_id:int,limit:int=5,user=Depends(current_user)):
    limit=max(1,min(limit,15))
    with conn() as db:
        row=db.execute("SELECT embedding FROM chunks WHERE document_id=%s ORDER BY id LIMIT 1",
                       (document_id,)).fetchone()
        if not row:
            raise HTTPException(404,"Document has no indexed chunks.")
        emb=str(row[0])
        result=db.execute(
            """SELECT d.id,COALESCE(d.title,d.filename),d.source_url,
                      MAX(1-(c.embedding <=> %s::vector)) similarity
               FROM chunks c JOIN documents d ON d.id=c.document_id
               WHERE d.id<>%s GROUP BY d.id ORDER BY similarity DESC LIMIT %s""",
            (emb,document_id,limit)).fetchall()
    return [{"document_id":r[0],"title":r[1],"source_url":r[2],
             "similarity":round(float(r[3]),3)} for r in result]


@router.get("/projects/{project_id}/report")
def export_report(project_id:int,user=Depends(current_user)):
    with conn() as db:
        can_view_project(db,project_id,user)
        project=db.execute("SELECT title,description,region FROM research_projects WHERE id=%s",
                           (project_id,)).fetchone()
    evidence=notes(project_id,user)
    lines=["# "+project[0],"",project[1],"","Region: "+(project[2] or "Not specified"),
           "","Generated UTC: "+datetime.now(timezone.utc).isoformat(),
           "","## Evidence review",""]
    for item in evidence:
        lines.extend(["### "+item["review_status"].upper()+" — "+item["author"],
                      item["body"],"Source: "+(item["source_url"] or "Not provided"),
                      "Indexed document ID: "+str(item["document_id"] or "Not linked"),""])
    lines.extend(["## Methodological limitations","",
                  "This export contains user-entered project notes and review decisions. "
                  "It does not validate the original sources, establish causation, or constitute a policy recommendation."])
    content="\n".join(lines).encode("utf-8")
    return StreamingResponse(io.BytesIO(content),media_type="text/markdown",
                             headers={"Content-Disposition":f'attachment; filename="bhoomiai-project-{project_id}.md"'})


@router.get("/audit")
def audit_log(user=Depends(require_admin)):
    with conn() as db:
        rows=db.execute("SELECT actor_id,event,target,created_at FROM platform_audit "
                        "ORDER BY id DESC LIMIT 100").fetchall()
    return [{"actor_id":r[0],"event":r[1],"target":r[2],
             "created_at":r[3].isoformat()} for r in rows]
