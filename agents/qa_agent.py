from typing import Any, Dict
from agents.base_agent import BaseAgent
from core.database import SessionLocal, AgentEvent
from datetime import datetime


THRESHOLDS = {
    "score": {(0.9, 1.01): "excellent", (0.8, 0.9): "good", (0.6, 0.8): "retry", (0.0, 0.6): "fail"},
}


def _grade_score(score: float) -> str:
    for (lo, hi), label in THRESHOLDS["score"].items():
        if lo <= score < hi:
            return label
    return "fail"


class QAAgent(BaseAgent):
    name = "qa"

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        target_agent: str = task.get("agent", "unknown")
        result: Dict = task.get("result", {})
        goal: str = task.get("goal", "")

        score = result.get("score", 0.0)
        grade = _grade_score(score)

        issues = []
        improvements = []

        if score < 0.6:
            issues.append("Goal not achieved")
            improvements.append("Retry with different search terms or sources")

        if result.get("error"):
            issues.append(f"Error: {result['error']}")
            improvements.append("Inspect logs and fix root cause before retrying")

        leads_found = result.get("leads_found", 0)
        leads_target = result.get("leads_target", 0)
        if leads_target and leads_found < leads_target * 0.8:
            issues.append(f"Only {leads_found}/{leads_target} leads found")
            improvements.append("Broaden search query or try additional location")

        retry = score < 0.8

        evaluation = {
            "agent": target_agent,
            "goal": goal,
            "score": score,
            "grade": grade,
            "issues": issues,
            "improvements": improvements,
            "retry_required": retry,
        }

        await self._log_event(target_agent, goal, score, issues)
        return {"score": 1.0, "evaluation": evaluation}

    async def _log_event(self, agent: str, goal: str, score: float, issues: list):
        async with SessionLocal() as db:
            event = AgentEvent(
                agent=agent,
                action=goal[:255],
                detail="; ".join(issues) if issues else "OK",
                status="success" if score >= 0.8 else "warning" if score >= 0.6 else "error",
                score=score,
                created_at=datetime.utcnow(),
            )
            db.add(event)
            await db.commit()
