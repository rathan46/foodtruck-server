import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from app.core.config import get_settings


class OTPService:
    def __init__(self) -> None:
        self._otps: Dict[str, Dict[str, Any]] = {}
        self._queue: asyncio.Queue[Dict[str, str]] = asyncio.Queue()
        self._sent: List[Dict[str, str]] = []
        self._failed: List[Dict[str, str]] = []

    @staticmethod
    def key(mobile: str, role: str) -> str:
        return f"{role}:{mobile}"

    async def create_request(self, mobile: str, role: str) -> Dict[str, str]:
        settings = get_settings()
        otp = f"{secrets.randbelow(900000) + 100000}"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.otp_expiry_seconds)
        self._otps[self.key(mobile, role)] = {
            "otp": otp,
            "expires_at": expires_at,
            "attempts": 0,
        }
        payload = {"mobile": mobile, "role": role, "otp": otp}
        await self._queue.put(payload)
        return {"status": "queued", "mobile": mobile, "role": role}

    async def next_request(self) -> Dict[str, str]:
        return await self._queue.get()

    def verify(self, mobile: str, role: str, otp: str) -> bool:
        settings = get_settings()
        record = self._otps.get(self.key(mobile, role))
        if not record:
            return False
        record["attempts"] += 1
        if record["attempts"] > settings.otp_max_attempts:
            self._otps.pop(self.key(mobile, role), None)
            return False
        if datetime.now(timezone.utc) > record["expires_at"]:
            self._otps.pop(self.key(mobile, role), None)
            return False
        if record["otp"] != otp:
            return False
        self._otps.pop(self.key(mobile, role), None)
        return True

    def mark_sent(self, payload: Dict[str, str]) -> None:
        self._sent.insert(0, payload)
        self._sent[:] = self._sent[:100]

    def mark_failed(self, payload: Dict[str, str]) -> None:
        self._failed.insert(0, payload)
        self._failed[:] = self._failed[:100]

    def dashboard(self) -> Dict[str, Any]:
        return {
            "pending": self._queue.qsize(),
            "active_otps": len(self._otps),
            "sent": self._sent[:20],
            "failed": self._failed[:20],
        }


otp_service = OTPService()
