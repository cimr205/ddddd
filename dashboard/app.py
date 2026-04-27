import asyncio
import json
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, desc, func

from core.database import init_db, Lead, Campaign, EmailLog, AgentEvent, ChatHistory, Job, SessionLocal
from core.monitor import monitor
from agents.ceo_agent import CEOAgent
from agents.commander import parse_command, HELP_TEXT

app = FastAPI(title="Lead Agent System", version="2.0.0")
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

ceo = CEOAgent()
_active_tasks: dict = {}


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str

class ScrapeRequest(BaseModel):
    query: str
    location: str
    count: int = 50  # default 50, ingen øvre grænse
    niche: str = ""

class CampaignCreate(BaseModel):
    name: str
    niche: str = ""

class CampaignLaunch(BaseModel):
    campaign_id: int
    lead_ids: List[int]
    context: str = ""
    from_name: str = "Lead System"

class JobCreate(BaseModel):
    name: str = ""
    query: str
    location: str = "Danmark"
    count: int = 1000
    niche: str = ""
    pipeline: str = "scrape"  # scrape or full


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    await init_db()
    await monitor.emit("ceo", "CEO Agent", "System klar", "idle")


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/")
async def dashboard():
    return FileResponse("dashboard/static/index.html")


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    q = monitor.subscribe()
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


# ── Chat / Prompt ─────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: ChatRequest, background_tasks: BackgroundTasks):
    msg = req.message.strip()
    if not msg:
        return {"ok": False}

    # Save user message
    await _save_chat("user", msg)
    await monitor.emit_chat("user", msg)

    # Parse command
    action = await parse_command(msg)
    background_tasks.add_task(_execute_action, action, msg)
    return {"ok": True, "action": action}


async def _execute_action(action: dict, raw: str):
    a = action.get("action", "unknown")

    if a == "help":
        await monitor.emit_chat("agent", HELP_TEXT, "text")
        await _save_chat("agent", HELP_TEXT)

    elif a == "status":
        async with SessionLocal() as db:
            leads = (await db.execute(select(func.count(Lead.id)))).scalar()
            sent = (await db.execute(select(func.count(EmailLog.id)).where(EmailLog.status == "sent"))).scalar()
            camps = (await db.execute(select(func.count(Campaign.id)))).scalar()
        msg = f"**System Status**\n\nLeads i database: **{leads}**\nEmails sendt: **{sent}**\nKampagner: **{camps}**"
        await monitor.emit_chat("agent", msg)
        await _save_chat("agent", msg)

    elif a == "leads":
        async with SessionLocal() as db:
            result = await db.execute(select(Lead).order_by(desc(Lead.created_at)).limit(10))
            leads = result.scalars().all()
        lines = [f"**{l.company}** – {l.email or '—'} ({l.status})" for l in leads]
        msg = f"**Seneste leads:**\n\n" + "\n".join(lines) if lines else "Ingen leads endnu."
        await monitor.emit_chat("agent", msg)
        await _save_chat("agent", msg)

    elif a == "scrape":
        query = action.get("query", "")
        location = action.get("location", "Danmark")
        count = action.get("count", 50)
        niche = action.get("niche", query)
        reply = f"Starter scraping: **{count} {query}** i **{location}**..."
        await monitor.emit_chat("agent", reply)
        await _save_chat("agent", reply)

        result = await ceo.run_scrape_pipeline(query, location, count, niche)
        found = result.get("leads_found", 0)
        done_msg = f"Scraping færdig. Fandt og gemte **{found} leads**."
        await monitor.emit_chat("agent", done_msg, "result")
        await _save_chat("agent", done_msg)

    elif a == "full_pipeline":
        query = action.get("query", "")
        location = action.get("location", "Danmark")
        count = action.get("count", 50)
        niche = action.get("niche", query)
        reply = f"Starter **4-browser pipeline**: Maps + ejer-finder + LinkedIn for **{query}** i **{location}**..."
        await monitor.emit_chat("agent", reply)
        await _save_chat("agent", reply)

        result = await ceo.run_full_pipeline(query, location, count, niche)
        found = result.get("leads_found", 0)
        owners = result.get("owners_found", 0)
        emails = result.get("emails_found", 0)
        done_msg = f"Pipeline færdig.\nFirmaer: **{found}** · Ejere: **{owners}** · LinkedIn-emails: **{emails}**"
        await monitor.emit_chat("agent", done_msg, "result")
        await _save_chat("agent", done_msg)

    elif a == "create_campaign":
        name = action.get("name", "Ny kampagne")
        niche = action.get("niche", "")
        async with SessionLocal() as db:
            camp = Campaign(name=name, niche=niche, status="idle")
            db.add(camp)
            await db.commit()
            await db.refresh(camp)
        msg = f"Kampagne oprettet: **{name}** (ID: {camp.id})\nBrug 'launch kampagne {camp.id}' for at sende."
        await monitor.emit_chat("agent", msg, "result")
        await _save_chat("agent", msg)

    elif a == "launch_campaign":
        campaign_id = action.get("campaign_id")
        context = action.get("context", raw)
        from_name = action.get("from_name", "Lead System")

        # Find latest campaign if no ID given
        if not campaign_id:
            async with SessionLocal() as db:
                result = await db.execute(select(Campaign).order_by(desc(Campaign.created_at)).limit(1))
                camp = result.scalar_one_or_none()
                campaign_id = camp.id if camp else None

        if not campaign_id:
            await monitor.emit_chat("agent", "Ingen kampagne fundet. Opret én med 'opret kampagne navn'.", "error")
            return

        # Get all new leads
        async with SessionLocal() as db:
            result = await db.execute(select(Lead).where(Lead.status == "new"))
            leads = result.scalars().all()

        if not leads:
            await monitor.emit_chat("agent", "Ingen nye leads at sende til. Scrape flere leads først.", "error")
            return

        lead_ids = [l.id for l in leads]
        msg = f"Starter kampagne til **{len(lead_ids)} leads**..."
        await monitor.emit_chat("agent", msg)
        await _save_chat("agent", msg)

        result = await ceo.run_campaign_pipeline(campaign_id, lead_ids, context, from_name)
        sent = result.get("sending", {}).get("sent", 0)
        done = f"Kampagne færdig. Sendt: **{sent}/{len(lead_ids)}** emails."
        await monitor.emit_chat("agent", done, "result")
        await _save_chat("agent", done)

    elif a == "create_job":
        query = action.get("query", "")
        location = action.get("location", "Danmark")
        count = action.get("count", 1000)
        niche = action.get("niche", query)
        pipeline = action.get("pipeline", "scrape")

        async with SessionLocal() as db:
            job = Job(name=f"{query} i {location}",
                      query=query, location=location, count=count,
                      niche=niche, pipeline=pipeline, status="pending")
            db.add(job)
            await db.commit()
            await db.refresh(job)

        msg = (f"**Job oprettet** og kører i baggrunden!\n\n"
               f"Job: **{query}** i **{location}**\n"
               f"Mål: **{count} leads**\n"
               f"Jeg arbejder på det – du kan se fremskridt i chat og i **Jobs** fanen.")
        await monitor.emit_chat("agent", msg, "result")
        await _save_chat("agent", msg)

        # Start it
        asyncio.create_task(_run_job(job.id))

    else:
        reply = f"Forstod ikke: '{raw}'\n\nSkriv `hjælp` for at se hvad du kan gøre."
        await monitor.emit_chat("agent", reply, "error")
        await _save_chat("agent", reply)


async def _save_chat(role: str, content: str, msg_type: str = "text"):
    async with SessionLocal() as db:
        db.add(ChatHistory(role=role, content=content, msg_type=msg_type))
        await db.commit()


# ── Chat history ──────────────────────────────────────────────────────────────

@app.get("/api/history")
async def get_history(limit: int = 100):
    async with SessionLocal() as db:
        result = await db.execute(
            select(ChatHistory).order_by(ChatHistory.created_at).limit(limit)
        )
        rows = result.scalars().all()
    return [
        {"id": r.id, "role": r.role, "content": r.content, "msg_type": r.msg_type, "created_at": r.created_at}
        for r in rows
    ]


@app.delete("/api/history")
async def clear_history():
    async with SessionLocal() as db:
        rows = await db.execute(select(ChatHistory))
        for r in rows.scalars().all():
            await db.delete(r)
        await db.commit()
    return {"ok": True}


# ── Leads ─────────────────────────────────────────────────────────────────────

@app.get("/api/leads")
async def list_leads(page: int = 1, limit: int = 50, search: str = "", status: str = "", niche: str = ""):
    async with SessionLocal() as db:
        q = select(Lead).order_by(desc(Lead.created_at))
        if search:
            q = q.where(Lead.company.ilike(f"%{search}%") | Lead.email.ilike(f"%{search}%"))
        if status:
            q = q.where(Lead.status == status)
        if niche:
            q = q.where(Lead.niche.ilike(f"%{niche}%"))
        total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar()
        q = q.offset((page - 1) * limit).limit(limit)
        leads = (await db.execute(q)).scalars().all()
    return {
        "total": total, "page": page, "limit": limit,
        "leads": [
            {"id": l.id, "name": l.name, "company": l.company, "email": l.email,
             "phone": l.phone, "website": l.website, "niche": l.niche,
             "status": l.status, "email_confidence": l.email_confidence,
             "source": l.source, "created_at": l.created_at}
            for l in leads
        ],
    }


@app.get("/api/categories")
async def get_categories():
    async with SessionLocal() as db:
        leads = (await db.execute(select(Lead))).scalars().all()

    cats: Dict[str, dict] = {}
    for l in leads:
        key = (l.niche or "Uden kategori").strip().lower().title()
        if key not in cats:
            cats[key] = {"name": key, "total": 0, "new": 0, "contacted": 0,
                         "replied": 0, "conf_sum": 0.0}
        cats[key]["total"] += 1
        cats[key][l.status or "new"] = cats[key].get(l.status or "new", 0) + 1
        cats[key]["conf_sum"] += l.email_confidence or 0.0

    result = []
    for k, v in sorted(cats.items(), key=lambda x: -x[1]["total"]):
        avg_conf = v["conf_sum"] / max(v["total"], 1)
        result.append({
            "name": v["name"],
            "total": v["total"],
            "new": v.get("new", 0),
            "contacted": v.get("contacted", 0),
            "replied": v.get("replied", 0),
            "avg_confidence": round(avg_conf, 2),
        })
    return result


from typing import Dict  # noqa – already imported above but ensure available


@app.delete("/api/leads/{lead_id}")
async def delete_lead(lead_id: int):
    async with SessionLocal() as db:
        lead = await db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(status_code=404)
        await db.delete(lead)
        await db.commit()
    return {"ok": True}


# ── Campaigns ─────────────────────────────────────────────────────────────────

@app.get("/api/campaigns")
async def list_campaigns():
    async with SessionLocal() as db:
        camps = (await db.execute(select(Campaign).order_by(desc(Campaign.created_at)))).scalars().all()
    return [
        {"id": c.id, "name": c.name, "niche": c.niche, "status": c.status,
         "leads_total": c.leads_total, "sent_count": c.sent_count,
         "reply_count": c.reply_count, "failed_count": c.failed_count, "created_at": c.created_at}
        for c in camps
    ]


@app.post("/api/campaigns")
async def create_campaign(req: CampaignCreate):
    async with SessionLocal() as db:
        camp = Campaign(name=req.name, niche=req.niche, status="idle")
        db.add(camp)
        await db.commit()
        await db.refresh(camp)
    return {"id": camp.id, "name": camp.name}


@app.post("/api/campaigns/launch")
async def launch_campaign(req: CampaignLaunch, background_tasks: BackgroundTasks):
    async with SessionLocal() as db:
        camp = await db.get(Campaign, req.campaign_id)
        if not camp:
            raise HTTPException(status_code=404)
        camp.status = "running"
        camp.leads_total = len(req.lead_ids)
        await db.commit()

    task_id = f"camp_{req.campaign_id}_{datetime.utcnow().timestamp()}"

    async def _run():
        result = await ceo.run_campaign_pipeline(req.campaign_id, req.lead_ids, req.context, req.from_name)
        _active_tasks[task_id] = {"status": "done", "result": result}

    _active_tasks[task_id] = {"status": "running"}
    background_tasks.add_task(_run)
    return {"task_id": task_id}


@app.get("/api/campaigns/{campaign_id}/logs")
async def campaign_logs(campaign_id: int):
    async with SessionLocal() as db:
        result = await db.execute(
            select(EmailLog, Lead).join(Lead, EmailLog.lead_id == Lead.id)
            .where(EmailLog.campaign_id == campaign_id)
            .order_by(desc(EmailLog.created_at))
        )
    return [
        {"id": log.id, "lead_email": lead.email, "lead_company": lead.company,
         "subject": log.subject, "status": log.status, "sent_at": log.sent_at, "error": log.error}
        for log, lead in result.all()
    ]


# ── Stats & Events ────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats():
    async with SessionLocal() as db:
        total_leads = (await db.execute(select(func.count(Lead.id)))).scalar()
        emails_sent = (await db.execute(select(func.count(EmailLog.id)).where(EmailLog.status == "sent"))).scalar()
        campaigns_active = (await db.execute(select(func.count(Campaign.id)).where(Campaign.status == "running"))).scalar()
    return {"total_leads": total_leads, "emails_sent": emails_sent, "campaigns_active": campaigns_active}


@app.get("/api/events")
async def get_events(limit: int = 100):
    async with SessionLocal() as db:
        events = (await db.execute(
            select(AgentEvent).order_by(desc(AgentEvent.created_at)).limit(limit)
        )).scalars().all()
    return [
        {"id": e.id, "agent": e.agent, "action": e.action, "detail": e.detail,
         "status": e.status, "score": e.score, "created_at": e.created_at}
        for e in events
    ]


# ── Scrape (direct) ───────────────────────────────────────────────────────────

@app.post("/api/scrape")
async def start_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    task_id = f"scrape_{datetime.utcnow().timestamp()}"

    async def _run():
        result = await ceo.run_scrape_pipeline(req.query, req.location, req.count, req.niche or req.query)
        _active_tasks[task_id] = {"status": "done", "result": result}

    _active_tasks[task_id] = {"status": "running"}
    background_tasks.add_task(_run)
    return {"task_id": task_id}


@app.post("/api/scrape/full")
async def start_full_pipeline(req: ScrapeRequest, background_tasks: BackgroundTasks):
    """4-browser pipeline: Maps → Owner finder → LinkedIn → email"""
    task_id = f"full_{datetime.utcnow().timestamp()}"

    async def _run():
        result = await ceo.run_full_pipeline(req.query, req.location, req.count, req.niche or req.query)
        _active_tasks[task_id] = {"status": "done", "result": result}

    _active_tasks[task_id] = {"status": "running"}
    background_tasks.add_task(_run)
    return {"task_id": task_id}


@app.get("/api/tasks/{task_id}")
async def task_status(task_id: str):
    return _active_tasks.get(task_id, {"status": "not_found"})


# ── Jobs (Overnight / Scheduled) ─────────────────────────────────────────────

@app.get("/api/jobs")
async def list_jobs():
    async with SessionLocal() as db:
        jobs = (await db.execute(
            select(Job).order_by(desc(Job.created_at)).limit(50)
        )).scalars().all()
    return [
        {"id": j.id, "name": j.name, "query": j.query, "location": j.location,
         "count": j.count, "pipeline": j.pipeline, "status": j.status,
         "created_at": j.created_at, "started_at": j.started_at,
         "finished_at": j.finished_at, "leads_found": j.leads_found,
         "result_summary": j.result_summary}
        for j in jobs
    ]


@app.post("/api/jobs")
async def create_job_api(req: JobCreate, background_tasks: BackgroundTasks):
    async with SessionLocal() as db:
        job = Job(
            name=req.name or f"{req.query} i {req.location}",
            query=req.query, location=req.location, count=req.count,
            niche=req.niche or req.query, pipeline=req.pipeline, status="pending",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
    background_tasks.add_task(_run_job, job.id)
    return {"id": job.id, "status": "pending"}


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job:
            await db.delete(job)
            await db.commit()
    return {"ok": True}


async def _run_job(job_id: int):
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            return
        job.status = "running"
        job.started_at = datetime.utcnow()
        await db.commit()
        job_name = job.name
        job_query = job.query
        job_location = job.location
        job_count = job.count
        job_niche = job.niche or job.query
        job_pipeline = job.pipeline

    try:
        if job_pipeline == "full":
            result = await ceo.run_full_pipeline(job_query, job_location, job_count, job_niche)
        else:
            result = await ceo.run_scrape_pipeline(job_query, job_location, job_count, job_niche)

        found = result.get("leads_found", 0)
        async with SessionLocal() as db:
            job = await db.get(Job, job_id)
            if job:
                job.status = "done"
                job.finished_at = datetime.utcnow()
                job.leads_found = found
                job.result_summary = f"Fandt {found} leads"
                await db.commit()

        await monitor.emit_chat(
            "agent",
            f"**Job færdig:** {job_name}\nLeads fundet: **{found}**\nÅbn Leads-fanen for at se resultaterne.",
            "result"
        )
    except Exception as e:
        async with SessionLocal() as db:
            job = await db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.finished_at = datetime.utcnow()
                job.result_summary = str(e)[:300]
                await db.commit()
        await monitor.emit_chat("agent", f"**Job fejlede:** {job_name}\n{str(e)[:200]}", "error")


# ── Owner search (triggered from dashboard panel) ─────────────────────────────

@app.post("/api/owner/run")
async def run_owner_search(background_tasks: BackgroundTasks):
    background_tasks.add_task(_do_owner_search)
    return {"ok": True}


async def _do_owner_search():
    async with SessionLocal() as db:
        result = await db.execute(select(Lead).where(Lead.status == "new"))
        leads = result.scalars().all()

    if not leads:
        await monitor.emit_chat("agent", "Ingen nye leads at søge ejere for.", "error")
        return

    await monitor.emit_chat("agent", f"Starter ejer-søgning for **{len(leads)} leads**...")

    mid = len(leads) // 2 + 1
    lead_dicts_a = [{"company": l.company, "email": l.email or "", "owner_name": l.name or ""} for l in leads[:mid]]
    lead_dicts_b = [{"company": l.company, "email": l.email or "", "owner_name": l.name or ""} for l in leads[mid:]]

    import asyncio as _aio
    await _aio.gather(
        ceo.owner1.execute({"leads": lead_dicts_a}),
        ceo.owner2.execute({"leads": lead_dicts_b}),
        return_exceptions=True,
    )
    await monitor.emit_chat("agent", f"Ejer-søgning færdig for **{len(leads)} leads**.", "result")
