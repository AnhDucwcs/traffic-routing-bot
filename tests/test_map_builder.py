import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from app.services.routing.map_builder import load_edge_index, load_stgcn_model
from app.ml.stgcn_inference import STGCNInference

def test_load_edge_index_returns_edge_weight(tmp_path):
    # Dùng tmp_path để giả lập thư mục data/
    edge_index_data = np.array([[0, 1], [1, 2]])
    edge_weight_data = np.array([0.5, 0.8])
    
    # Mock SRC_DIR path in map_builder
    with patch('app.services.routing.map_builder.SRC_DIR', tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        
        np.save(data_dir / "edge_index.npy", edge_index_data)
        np.save(data_dir / "edge_weight.npy", edge_weight_data)
        
        # Tạo fake pkl
        import pickle
        with open(data_dir / "id_to_edge.pkl", 'wb') as f:
            pickle.dump({0: (0, 1)}, f)
            
        result = load_edge_index()
        
        assert result is not None
        assert len(result) == 3, "Phải trả về 3 phần tử: id_to_edge, edge_index, edge_weight"
        
        id_to_edge, edge_index, edge_weight = result
        assert np.array_equal(edge_index, edge_index_data)
        assert np.array_equal(edge_weight, edge_weight_data)
