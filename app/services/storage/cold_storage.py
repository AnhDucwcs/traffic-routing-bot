import asyncio
import json
import datetime
from app.core.logger import logger
from app.core.config import settings
import asyncio
import json
import logging
from pathlib import Path
from huggingface_hub import CommitScheduler

logger = logging.getLogger(__name__)

class ColdStorageManager:
    def __init__(self, sync_interval_minutes: int = 60):
        self.dataset_dir = Path("cold_data_buffer")
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        self.scheduler = CommitScheduler(
            repo_id="lnanhduc12/bus_speeds_inner_hcm",
            repo_type="dataset",
            folder_path=self.dataset_dir,
            every=sync_interval_minutes,
            token=settings.HF_TOKEN,
            # Tắt cảnh báo trên console của HF để tránh rác log
            squash_history=True 
        )
        logger.info(f"[Cold DB] Scheduler đã kích hoạt. Đồng bộ mỗi {sync_interval_minutes} phút.")

    async def insert_historical_data(self, cold_data: list):
        """Ghi dữ liệu vào file đệm một cách an toàn"""
        if not cold_data:
            return

        def _write_with_lock():
            # Sử dụng lock của scheduler để đảm bảo không bị xung đột khi ghi và đẩy
            with self.scheduler.lock:
                current_date = datetime.datetime.now().strftime("%Y-%m-%d")
                dynamic_file_path = self.dataset_dir / f"traffic_{current_date}.jsonl"
                with open(dynamic_file_path, "a", encoding="utf-8") as f:
                    for item in cold_data:
                        f.write(json.dumps(item) + "\n")
                        
        await asyncio.to_thread(_write_with_lock)