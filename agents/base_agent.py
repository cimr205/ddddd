import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from core.monitor import monitor


class BaseAgent(ABC):
    """
    Every agent follows the OBSERVE → THINK → ACT → EVALUATE loop.
    Subclasses implement `execute()` and call `self.emit()` to report status.
    """

    name: str = "base"
    max_retries: int = 3
    min_success_score: float = 0.8

    async def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        attempt = 0
        last_result = {}

        while attempt < self.max_retries:
            attempt += 1
            await self.emit("running", f"Attempt {attempt}/{self.max_retries}: {task.get('goal', '')}")

            try:
                result = await self.execute(task)
                score = result.get("score", 0.0)

                if score >= self.min_success_score:
                    await self.emit("success", f"Done – score {score:.2f}", score=score)
                    return result

                await self.emit(
                    "warning",
                    f"Score {score:.2f} < {self.min_success_score} – retrying",
                    score=score,
                )
                task["_prev_result"] = result
                task["_attempt"] = attempt
                last_result = result
                await asyncio.sleep(1)

            except Exception as exc:
                await self.emit("error", str(exc))
                last_result = {"score": 0.0, "error": str(exc)}
                await asyncio.sleep(2 ** attempt)

        await self.emit("error", f"Failed after {self.max_retries} attempts", score=0.0)
        return last_result

    @abstractmethod
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        ...

    async def emit(self, status: str, detail: str, score: float = 0.0):
        await monitor.emit(
            agent=self.name,
            action=self.name.replace("_", " ").title(),
            detail=detail,
            status=status,
            score=score,
        )
