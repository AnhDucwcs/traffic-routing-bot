import pytest
import numpy as np
from pathlib import Path
from app.ml.stgcn_inference import STGCNInference

def test_stgcn_inference_load():
    pth_path = Path("data/stgcn_best.pth")
    if not pth_path.exists():
        pytest.skip("stgcn_best.pth not found, skipping inference load test.")
    
    edge_index = np.array([[0, 1], [1, 0]], dtype=np.int64)
    edge_weight = np.array([0.5, 0.5], dtype=np.float32)

    # Khởi tạo mô hình (TDD: sẽ lỗi nếu stgcn_inference.py chưa lọc edge_weight)
    inference = STGCNInference(pth_path=pth_path, edge_index=edge_index, edge_weight=edge_weight)
    
    assert inference is not None
    assert hasattr(inference, 'model')

def test_stgcn_inference_predict():
    pth_path = Path("data/stgcn_best.pth")
    if not pth_path.exists():
        pytest.skip("stgcn_best.pth not found, skipping inference predict test.")
    
    # Số lượng node phải khớp với dữ liệu thực tế (mock hoặc dựa trên model_state)
    # Lấy num_nodes từ pth
    import torch
    ckpt = torch.load(pth_path, weights_only=False, map_location='cpu')
    num_nodes = ckpt['num_nodes']

    edge_index = np.array([[0, 1], [1, 0]], dtype=np.int64)
    edge_weight = np.array([0.5, 0.5], dtype=np.float32)

    inference = STGCNInference(pth_path=pth_path, edge_index=edge_index, edge_weight=edge_weight)
    
    # 4 bước thời gian, shape (1, num_nodes, 1, 4)
    fake_x = np.ones((1, num_nodes, 1, 4), dtype=np.float32)
    
    output = inference.predict(fake_x)
    assert output is not None
    assert output.shape == (1, num_nodes, 3), f"Expected shape (1, {num_nodes}, 3), got {output.shape}"
