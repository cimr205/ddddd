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
    status: str  # idle | running | success | warning | error
    score: float = 0.0
    updated_at: str = ""

    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = datetime.utcnow().isoformat()


class Monitor:
    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()
        self._agent_states: Dict[str, AgentStatus] = {}
        self._stats = {
            "total_leads": 0,
            "emails_sent": 0,
            "campaigns_active": 0,
            "reply_rate": 0.0,
        }

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        self._subscribers.discard(q)

    async def emit(self, agent: str, action: str, detail: str, status: str, score: float = 0.0):
        state = AgentStatus(
            agent=agent,
            action=action,
            detail=detail,
            status=status,
            score=score,
        )
        self._agent_states[agent] = state

        event = {
            "type": "agent_event",
            "data": asdict(state),
        }
        await self._broadcast(event)

    async def update_stats(self, **kwargs):
        self._stats.update(kwargs)
        await self._broadcast({"type": "stats", "data": self._stats.copy()})

    def get_all_states(self) -> Dict:
        return {
            "agents": {k: asdict(v) for k, v in self._agent_states.items()},
            "stats": self._stats.copy(),
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
