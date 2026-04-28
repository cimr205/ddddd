import asyncio
import json
from datetime import datetime
from typing import Any, Dict, Set
from dataclasses import dataclass, asdict


@dataclass
class AgentStatus:
    agent: str
    action: str
    detail: str
    status: str
    score: float = 0.0
    updated_at: str = ""

    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = datetime.utcnow().isoformat()


class Monitor:
    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()
        self._agent_states: Dict[str, AgentStatus] = {}
        self._stats = {"total_leads": 0, "emails_sent": 0, "campaigns_active": 0}
        self._last_frames: Dict[str, Dict] = {}  # panel_id → last frame
        self._telegram_callback = None  # set by TelegramBot on startup

    def set_telegram(self, callback):
        self._telegram_callback = callback

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers.discard(q)

    async def emit(self, agent: str, action: str, detail: str, status: str, score: float = 0.0):
        state = AgentStatus(agent=agent, action=action, detail=detail, status=status, score=score)
        self._agent_states[agent] = state
        await self._broadcast({"type": "agent_event", "data": asdict(state)})

    async def emit_browser_frame(
        self,
        screenshot_b64: str,
        cursor_x: int = 0,
        cursor_y: int = 0,
        page_url: str = "",
        label: str = "",
        panel_id: str = "maps",
    ):
        frame = {
            "panel_id": panel_id,
            "screenshot": screenshot_b64,
            "cursor_x": cursor_x,
            "cursor_y": cursor_y,
            "page_url": page_url,
            "label": label,
            "ts": datetime.utcnow().isoformat(),
        }
        self._last_frames[panel_id] = frame
        await self._broadcast({"type": "browser_frame", "data": frame})

    async def emit_chat(self, role: str, content: str, msg_type: str = "text"):
        await self._broadcast({
            "type": "chat_message",
            "data": {
                "role": role,
                "content": content,
                "msg_type": msg_type,
                "ts": datetime.utcnow().isoformat(),
            },
        })
        # Forward important agent messages to Telegram
        if role == "agent" and msg_type in ("result", "error") and self._telegram_callback:
            try:
                await self._telegram_callback(content, msg_type)
            except Exception:
                pass

    async def update_stats(self, **kwargs):
        self._stats.update(kwargs)
        await self._broadcast({"type": "stats", "data": self._stats.copy()})

    def get_all_states(self) -> Dict:
        return {
            "agents": {k: asdict(v) for k, v in self._agent_states.items()},
            "stats": self._stats.copy(),
            "last_frames": self._last_frames,
        }

    async def _broadcast(self, event: Dict[str, Any]):
        if not self._subscribers:
            return
        msg = json.dumps(event, default=str)
        dead = set()
        for q in self._subscribers:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                dead.add(q)
        self._subscribers -= dead


monitor = Monitor()
