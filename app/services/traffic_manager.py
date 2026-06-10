import json
import threading
from pathlib import Path
from app.core.logger import logger

class TrafficManager:
    def __init__(self, routing_graph):
        self.G = routing_graph
        self.segment_index = {}
        # Khóa chặn ghi để chống đụng độ RAM giữa thao tác Read (A*) và Write (Crawler)
        self.write_lock = threading.Lock()

    def build_index(self, segment_lengths):
        """
        Hàm này biến đổi segment_lengths (được build từ build_offline_graph.py) 
        thành một từ điển để tăng tốc độ tra cứu.
        """
        
        logger.info(f"Building Traffic Index...")

        for segment_id, data in segment_lengths.items():
            nodes = data.get('osmnx_nodes', [])
            edges_list = []
            
            for i in range(len(nodes) - 1):
                u = nodes[i]
                v = nodes[i + 1]
                
                #Tương tự, ở đây tôi cũng sẽ kiểm tra 2 chiều để tránh bị bỏ sót khi cập nhật trọng số
                # Cạnh xuôi
                if self.G.has_edge(u, v):
                    for k in self.G[u][v]:
                        if self.G[u][v][k].get('is_bus_route', False):
                            edges_list.append((u, v, k))
                # Cạnh ngược
                elif self.G.has_edge(v, u):
                    for k in self.G[v][u]:
                        if self.G[v][u][k].get('is_bus_route', False):
                            edges_list.append((v, u, k))

            self.segment_index[segment_id] = edges_list

                
        logger.info(f"Traffic Index được xây dựng với {len(self.segment_index)} bus segments.")

    def apply_traffic_penalty(self, segment_id: str, penalty_factor: float, spillover_alpha: float = 0.15):
        """
        Crawler gọi hàm này để cập nhật trọng số kẹt xe.
        """
        target_edges = self.segment_index.get(segment_id, [])
        if not target_edges:
            logger.warning(f"[TrafficManager] Không tìm thấy Cạnh nào khớp với segment_id: {segment_id}")
            return

        # Bật khóa chặn: Đợi update xong thì A* mới được đọc
        with self.write_lock:
            logger.info(f"Applying traffic penalty: Segment {segment_id}, Penalty Factor: {penalty_factor}, Affected Edges: {len(target_edges)}")
            for u, v, k in target_edges:
                base_time = self.G[u][v][k].get('base_time', 10.0)
                self.G[u][v][k]['current_weight'] = base_time * penalty_factor

                # Hiệu ứng tràn (Spillover) vào hẻm
                if penalty_factor > 1.0:
                    spillover_penalty = 1 + (penalty_factor - 1) * spillover_alpha
                else:
                    spillover_penalty = 1.0
                
                for node in (u, v):
                    for neighbor in self.G.successors(node):
                        if neighbor in (u, v): 
                            continue
                            
                        for neighbor_k in self.G[node][neighbor]:
                            edge_data = self.G[node][neighbor][neighbor_k]
                            
                            if not edge_data.get('is_bus_route', False):
                                neighbor_base = edge_data.get('base_time', 10.0)
                                new_weight = neighbor_base * spillover_penalty
                                
                                # Chỉ cập nhật nếu trọng số tràn lớn hơn trọng số hiện tại của hẻm đó
                                if edge_data.get('current_weight', neighbor_base) < new_weight:
                                    edge_data['current_weight'] = new_weight

    def reset_traffic(self):
        """Reset toàn bộ về base_time"""
        with self.write_lock:
            for u, v, k, data in self.G.edges(keys=True, data=True):
                data['current_weight'] = data.get('base_time', 10.0)