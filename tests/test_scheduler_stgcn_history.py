import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.services.crawler.scheduler import CrawlerScheduler

@pytest.fixture
def mock_scheduler():
    crawler = MagicMock()
    traffic_manager = MagicMock()
    traffic_manager.history_buffer = [] # list thay vì deque để dễ test
    hot_storage = MagicMock()
    cold_storage = MagicMock()
    
    # Bọc các hàm async
    hot_storage.get_active_traffic_data = AsyncMock(return_value=[])
    hot_storage.load_stgcn_history = AsyncMock(return_value=[1, 2, 3])
    hot_storage.save_stgcn_history = AsyncMock()
    
    scheduler = CrawlerScheduler(crawler, traffic_manager, hot_storage, cold_storage)
    
    # Bọc hàm async _update_hot_db
    scheduler._update_hot_db = AsyncMock()
    return scheduler

@pytest.mark.asyncio
async def test_hydrate_ram_stgcn_history(mock_scheduler):
    # Chạy hàm hydrate_ram
    await mock_scheduler.hydrate_ram()
    
    # Kiểm tra xem load_stgcn_history có được gọi không
    mock_scheduler.hot_storage.load_stgcn_history.assert_awaited_once()
    
    # Kiểm tra xem history_buffer đã được ghi đè chưa
    assert mock_scheduler.traffic_manager.history_buffer == [1, 2, 3]

@pytest.mark.asyncio
async def test_background_loop_save_history(mock_scheduler):
    # Mock return của crawler.run_campaign
    mock_scheduler.crawler.run_campaign = AsyncMock(return_value=([{'from_stop_id': 1}], []))
    mock_scheduler.hot_storage.upsert_traffic_data = AsyncMock()
    
    # Giả lập history_buffer có data
    mock_scheduler.traffic_manager.history_buffer = [1, 2, 3]
    
    # Dừng loop sau 1 chu kỳ bằng cách raise CancelledError thay vì sleep
    async def mock_sleep(*args, **kwargs):
        raise asyncio.CancelledError()
    
    with pytest.MonkeyPatch.context() as m:
        m.setattr(asyncio, "sleep", mock_sleep)
        
        await mock_scheduler._background_loop()
        
    # Kiểm tra xem save_stgcn_history có được gọi với list history không
    mock_scheduler.hot_storage.save_stgcn_history.assert_awaited_once_with([1, 2, 3])
