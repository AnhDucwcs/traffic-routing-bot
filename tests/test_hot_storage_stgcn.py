import pytest
import numpy as np
from bson.binary import Binary
from app.services.storage.hot_storage import HotStorageManager
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_hot_storage():
    with patch("app.services.storage.hot_storage.AsyncIOMotorClient") as mock_client:
        manager = HotStorageManager()
        # Mock the db and collection
        manager.db = AsyncMock()
        manager.collection = AsyncMock()
        yield manager

@pytest.mark.asyncio
async def test_save_stgcn_history(mock_hot_storage):
    # Tạo 2 mảng NumPy giả lập buffer
    arr1 = np.array([1.5, 2.5, 3.5], dtype=np.float32)
    arr2 = np.array([4.0, 5.0, 6.0], dtype=np.float32)
    history_buffer = [arr1, arr2]

    # Mock update_one
    mock_hot_storage.db["stgcn_history"].update_one = AsyncMock()

    await mock_hot_storage.save_stgcn_history(history_buffer)

    # Kiểm tra xem có gọi update_one chưa
    assert mock_hot_storage.db["stgcn_history"].update_one.called
    
    # Lấy các tham số gọi update_one
    call_args = mock_hot_storage.db["stgcn_history"].update_one.call_args
    args, kwargs = call_args
    
    assert args[0] == {"_id": "stgcn_history_doc"}
    assert kwargs.get("upsert") == True
    
    update_doc = args[1]
    assert "$set" in update_doc
    assert "frames" in update_doc["$set"]
    assert len(update_doc["$set"]["frames"]) == 2
    
    # Kiểm tra frames lưu dưới dạng bson Binary
    assert isinstance(update_doc["$set"]["frames"][0], Binary)

@pytest.mark.asyncio
async def test_load_stgcn_history(mock_hot_storage):
    # Tạo mock DB response
    arr1 = np.array([1.5, 2.5, 3.5], dtype=np.float32)
    arr2 = np.array([4.0, 5.0, 6.0], dtype=np.float32)
    binary_frames = [Binary(arr1.tobytes()), Binary(arr2.tobytes())]
    
    mock_hot_storage.db["stgcn_history"].find_one = AsyncMock(return_value={
        "_id": "stgcn_history_doc",
        "frames": binary_frames
    })

    restored_history = await mock_hot_storage.load_stgcn_history()

    assert len(restored_history) == 2
    assert isinstance(restored_history[0], np.ndarray)
    assert restored_history[0].dtype == np.float32
    
    # Kiểm tra tính vẹn toàn dữ liệu (Data Integrity)
    assert np.array_equal(restored_history[0], arr1)
    assert np.array_equal(restored_history[1], arr2)
