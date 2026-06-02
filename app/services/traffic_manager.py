import json
import threading
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class TrafficManager:
    def __init__(self, routing_graph):
        self.G = routing_graph
        self.segment_index = {}
        # Khóa chặn ghi để chống đụng độ RAM giữa thao tác Read (A*) và Write (Crawler)
        self.write_lock = threading.Lock()

    def build_index(self, segments_path: Path):
        logger.info(f"Building Traffic Index from {segments_path}...")
        
        with open(segments_path, 'r', encoding='utf-8') as f:
            segments = json.load(f)

        for segment_id, data in segments.items():
            nodes = data.get('osmnx_nodes', [])
            edges_list = []
            
            for i in range(len(nodes) - 1):
                u = nodes[i]
                v = nodes[i + 1]
                
                # Kiểm tra cạnh có tồn tại không
                if self.G.has_edge(u, v):
                    for k in self.G[u][v]:
                        if self.G[u][v][k].get('is_bus_route', False):
                            edges_list.append((u, v, k))
            
            self.segment_index[segment_id] = edges_list
            
        logger.info(f"Traffic Index được xây dựng với {len(self.segment_index)} bus segments.")

    def apply_traffic_penalty(self, segment_id: str, penalty_factor: float, spillover_alpha: float = 0.4):
        """
        Crawler gọi hàm này để cập nhật trọng số kẹt xe.
        """
        target_edges = self.segment_index.get(segment_id, [])
        if not target_edges:
            return

        # Bật khóa chặn: Đợi update xong thì A* mới được đọc
        with self.write_lock:
            for u, v, k in target_edges:
                base_time = self.G[u][v][k].get('base_time', 10.0)
                self.G[u][v][k]['current_weight'] = base_time * penalty_factor

                # Hiệu ứng tràn (Spillover) vào hẻm
                spillover_penalty = 1 + (penalty_factor - 1) * spillover_alpha
                
                for node in (u, v):
                    for neighbor in self.G.successors(node):
                        if neighbor in (u, v): 
                            continue
                            
                        for neighbor_k in self.G[node][neighbor]:
                            edge_data = self.G[node][neighbor][neighbor_k]
                            
                            if not edge_data.get('is_bus_route', False):
                                neighbor_base = edge_data.get('base_time', 10.0)
                                edge_data['current_weight'] = neighbor_base * spillover_penalty

    def reset_traffic(self):
        """Reset toàn bộ về base_time"""
        with self.write_lock:
            for u, v, k, data in self.G.edges(keys=True, data=True):
                data['current_weight'] = data.get('base_time', 10.0)