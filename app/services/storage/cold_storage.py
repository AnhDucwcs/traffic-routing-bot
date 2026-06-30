from app.core.logger import logger
from app.core.config import settings
import asyncio
import json
import datetime
from pathlib import Path
import pandas as pd
from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import EntryNotFoundError

class ColdStorageManager:
    def __init__(self, sync_interval_minutes: int = 60):
        self.repo_id="lnanhduc12/bus_speeds_inner_hcm"
        self.token = settings.HF_TOKEN
        self.api = HfApi()
        
        # Thư mục đệm này chỉ chứa dữ liệu tạm thời của GIỜ HIỆN TẠI
        self.dataset_dir = Path("cold_data_buffer")
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_month = datetime.datetime.now().strftime("%Y-%m")
        self.local_jsonl = self.dataset_dir / f"buffer_{self.current_month}.jsonl"
        
        self.sync_interval = sync_interval_minutes * 60
        asyncio.create_task(self._auto_sync_loop())
        logger.info(f"[Cold DB] Hệ thống Stateless kích hoạt. Chu kỳ đồng bộ: {sync_interval_minutes} phút.")

    async def insert_historical_data(self, cold_data: list):
        """Ghi tạm dữ liệu cào được vào bộ đệm giờ hiện tại"""
        if not cold_data:
            return

        def _write():
            check_month = datetime.datetime.now().strftime("%Y-%m")
            if check_month != self.current_month:
                self.current_month = check_month
                self.local_jsonl = self.dataset_dir / f"buffer_{self.current_month}.jsonl"

            with open(self.local_jsonl, "a", encoding="utf-8") as f:
                for item in cold_data:
                    f.write(json.dumps(item) + "\n")
                    
        await asyncio.to_thread(_write)

    async def _auto_sync_loop(self):
        while True:
            await asyncio.sleep(self.sync_interval)
            try:
                await self.sync_and_convert_parquet()
            except asyncio.CancelledError:
                logger.info("[Cold DB] Tiến trình ngầm nhận lệnh dừng hệ thống.")
                break
            except Exception as e:
                logger.error(f"[Cold DB] Lỗi đóng gói Parquet: {e}")
                await asyncio.sleep(60)

    async def sync_and_convert_parquet(self):
        """Quy trình cốt lõi: Tải về -> Trộn dữ liệu -> Đẩy lên -> Xóa sạch local"""
        logger.info("[Cold DB] Bắt đầu chu trình đồng bộ an toàn...")
        
        current_month = datetime.datetime.now().strftime("%Y-%m")
        jsonl_path = self.dataset_dir / f"buffer_{current_month}.jsonl"
        parquet_name = f"traffic_{current_month}.parquet"
        parquet_path = self.dataset_dir / parquet_name

        # Nếu trong 1 tiếng qua không cào được gì, hủy tiến trình để tiết kiệm I/O
        if not jsonl_path.exists() or jsonl_path.stat().st_size == 0:
            logger.info("[Cold DB] Không có dữ liệu mới. Bỏ qua nhịp đồng bộ.")
            return

        def _merge_and_upload():
            # 1. Đọc dữ liệu mới cào được trong 1 tiếng vừa qua
            try:
                new_df = pd.read_json(jsonl_path, lines=True)
            except Exception as e:
                logger.error(f"Không thể đọc file đệm local: {e}")
                return

            # 2. Tải file Parquet lịch sử (3 ngày trước hoặc nhiều hơn) từ Hugging Face về RAM
            old_df = pd.DataFrame()
            try:
                downloaded_path = hf_hub_download(
                    repo_id=self.repo_id,
                    filename=parquet_name,
                    repo_type="dataset",
                    token=self.token,
                    local_dir=str(self.dataset_dir)
                )
                old_df = pd.read_parquet(downloaded_path)
                logger.info(f"[Cold DB] Đã tải file lịch sử từ Web thành công ({len(old_df)} dòng).")
            except EntryNotFoundError:
                logger.info("[Cold DB] Chưa có file lịch sử trên Web (Tháng mới). Tạo file gốc.")
            except Exception as e:
                logger.warning(f"[Cold DB] Cảnh báo khi đọc file lịch sử từ xa: {e}")

            # 3. Tiến hành HỢP NHẤT (Concatenate) dữ liệu cũ và mới
            if not old_df.empty:
                final_df = pd.concat([old_df, new_df], ignore_index=True)
            else:
                final_df = new_df

            # 4. Ép nén thành file Parquet tổng lực
            final_df.to_parquet(parquet_path, index=False, compression="snappy")
            
            # 5. Đẩy file Parquet tổng ngược lên Hugging Face (An toàn tuyệt đối)
            self.api.upload_file(
                path_or_fileobj=str(parquet_path),
                path_in_repo=parquet_name,
                repo_id=self.repo_id,
                repo_type="dataset",
                token=self.token
            )
            logger.info(f"[Cold DB] Đã đồng bộ file tổng lên Web thành công ({len(final_df)} dòng).")

            # 6. XÓA SẠCH FILE LOCAL ĐỂ GIẢI PHÓNG Ổ CỨNG CONTAINER
            jsonl_path.unlink()
            if parquet_path.exists():
                parquet_path.unlink()
            logger.info("[Cold DB] Đã dọn dẹp bộ đệm local. Ổ cứng quay về 0 MB.")

        await asyncio.to_thread(_merge_and_upload)
