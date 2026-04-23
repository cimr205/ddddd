import asyncio
import json
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, desc, func

from core.database import init_db, get_db, Lead, Campaign, EmailLog, AgentEvent, SessionLocal
from core.monitor import monitor
from agents.ceo_agent import CEOAgent

app = FastAPI(title="Lead Generation System", version="1.0.0")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

ceo = CEOAgent()
_active_tasks: dict = {}


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    query: str
    location: str
    count: int = 50
    niche: str = ""

class CampaignCreate(BaseModel):
    name: str
    niche: str = ""
    subject_template: str = ""
    body_template: str = ""

class CampaignLaunch(BaseModel):
    campaign_id: int
    lead_ids: List[int]
    context: str = ""
    from_name: str = "Lead System"


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    await init_db()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/")
async def dashboard():
    return FileResponse("dashboard/static/index.html")


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    q = monitor.subscribe()

    # Send current state immediately on connect
    state = monitor.get_all_states()
    await ws.send_text(json.dumps({"type": "init", "data": state}, default=str))

    try:
        while True:
            msg = await asyncio.wait_for(q.get(), timeout=30)
            await ws.send_text(msg)
    except (WebSocketDisconnect, asyncio.TimeoutError, Exception):
        pass
    finally:
        monitor.unsubscribe(q)


# ── Leads API ─────────────────────────────────────────────────────────────────

@app.get("/api/leads")
async def list_leads(
    page: int = 1,
    limit: int = 50,
    search: str = "",
    status: str = "",
    niche: str = "",
):
    async with SessionLocal() as db:
        q = select(Lead).order_by(desc(Lead.created_at))
        if search:
            q = q.where(
                Lead.company.ilike(f"%{search}%") | Lead.email.ilike(f"%{search}%")
            )
        if status:
            q = q.where(Lead.status == status)
        if niche:
            q = q.where(Lead.niche.ilike(f"%{niche}%"))

        total_result = await db.execute(select(func.count()).select_from(q.subquery()))
        total = total_result.scalar()

        q = q.offset((page - 1) * limit).limit(limit)
        result = await db.execute(q)
        leads = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "leads": [
            {
                "id": l.id, "name": l.name, "company": l.company, "email": l.email,
                "phone": l.phone, "website": l.website, "niche": l.niche,
                "status": l.status, "email_confidence": l.email_confidence,
                "source": l.source, "created_at": l.created_at,
            }
            for l in leads
        ],
    }


@app.delete("/api/leads/{lead_id}")
async def delete_lead(lead_id: int):
    async with SessionLocal() as db:
        lead = await db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404)
        await db.delete(lead)
        await db.commit()
    return {"ok": True}


# ── Scrape API ────────────────────────────────────────────────────────────────

@app.post("/api/scrape")
async def start_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    task_id = f"scrape_{datetime.utcnow().timestamp()}"

    async def _run():
        result = await ceo.run_scrape_pipeline(
            req.query, req.location, req.count, req.niche or req.query
        )
        _active_tasks[task_id] = {"status": "done", "result": result}

    _active_tasks[task_id] = {"status": "running"}
    background_tasks.add_task(_run)
    return {"task_id": task_id}


@app.get("/api/tasks/{task_id}")
async def task_status(task_id: str):
    return _active_tasks.get(task_id, {"status": "not_found"})


# ── Campaign API ──────────────────────────────────────────────────────────────

@app.get("/api/campaigns")
async def list_campaigns():
    async with SessionLocal() as db:
        result = await db.execute(select(Campaign).order_by(desc(Campaign.created_at)))
        camps = result.scalars().all()
    return [
        {
            "id": c.id, "name": c.name, "niche": c.niche, "status": c.status,
            "leads_total": c.leads_total, "sent_count": c.sent_count,
            "reply_count": c.reply_count, "failed_count": c.failed_count,
            "created_at": c.created_at,
        }
        for c in camps
    ]


@app.post("/api/campaigns")
async def create_campaign(req: CampaignCreate):
    async with SessionLocal() as db:
        camp = Campaign(
            name=req.name,
            niche=req.niche,
            subject_template=req.subject_template,
            body_template=req.body_template,
            status="idle",
        )
        db.add(camp)
        await db.commit()
        await db.refresh(camp)
    return {"id": camp.id, "name": camp.name, "status": camp.status}


@app.post("/api/campaigns/launch")
async def launch_campaign(req: CampaignLaunch, background_tasks: BackgroundTasks):
    task_id = f"campaign_{req.campaign_id}_{datetime.utcnow().timestamp()}"

    async with SessionLocal() as db:
        camp = await db.get(Campaign, req.campaign_id)
        if not camp:
            raise HTTPException(status_code=404, detail="Campaign not found")
        camp.status = "running"
        camp.leads_total = len(req.lead_ids)
        await db.commit()

    async def _run():
        result = await ceo.run_campaign_pipeline(
            req.campaign_id, req.lead_ids, req.context, req.from_name
        )
        _active_tasks[task_id] = {"status": "done", "result": result}

    _active_tasks[task_id] = {"status": "running"}
    background_tasks.add_task(_run)
    return {"task_id": task_id}


@app.get("/api/campaigns/{campaign_id}/logs")
async def campaign_logs(campaign_id: int):
    async with SessionLocal() as db:
        result = await db.execute(
            select(EmailLog, Lead)
            .join(Lead, EmailLog.lead_id == Lead.id)
            .where(EmailLog.campaign_id == campaign_id)
            .order_by(desc(EmailLog.created_at))
        )
        rows = result.all()
    return [
        {
            "id": log.id, "lead_email": lead.email, "lead_company": lead.company,
            "subject": log.subject, "status": log.status,
            "sent_at": log.sent_at, "error": log.error,
        }
        for log, lead in rows
    ]


# ── Stats & Events ────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats():
    async with SessionLocal() as db:
        total_leads = (await db.execute(select(func.count(Lead.id)))).scalar()
        emails_sent = (await db.execute(select(func.count(EmailLog.id)).where(EmailLog.status == "sent"))).scalar()
        campaigns_active = (await db.execute(select(func.count(Campaign.id)).where(Campaign.status == "running"))).scalar()
    return {
        "total_leads": total_leads,
        "emails_sent": emails_sent,
        "campaigns_active": campaigns_active,
    }


@app.get("/api/events")
async def get_events(limit: int = 50):
    async with SessionLocal() as db:
        result = await db.execute(
            select(AgentEvent).order_by(desc(AgentEvent.created_at)).limit(limit)
        )
        events = result.scalars().all()
    return [
        {
            "id": e.id, "agent": e.agent, "action": e.action, "detail": e.detail,
            "status": e.status, "score": e.score, "created_at": e.created_at,
        }
        for e in events
    ]
