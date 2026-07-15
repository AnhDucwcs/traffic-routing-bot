import json
from pathlib import Path
from app.core.logger import logger

class TrafficManager:
    def __init__(self, routing_graph, turn_penalties):
        self.G = routing_graph
        self.turn_penalties = turn_penalties
        self.segment_index = {}
        
        # Double Buffering: A* đọc active_weights, Crawler ghi bg_weights
        # Python GIL đảm bảo pointer swap là atomic → không cần Lock
        self.active_weights = {
            (u, v, k): data.get('base_time', 10.0)
            for u, v, k, data in self.G.edges(keys=True, data=True)
        }
        self.bg_weights = self.active_weights.copy()

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

    def apply_traffic_penalty(self, segment_id: str, crawler_speed_kmh: float, spillover_alpha: float = 0.15):
        """
        Crawler ghi vào bg_weights, sau đó swap pointer sang active_weights.
        A* đọc active_weights mà không cần lock.
        """
        target_edges = self.segment_index.get(segment_id, [])
        if not target_edges:
            logger.warning(f"[TrafficManager] Không tìm thấy Cạnh nào khớp với segment_id: {segment_id}")
            return

        for u, v, k in target_edges:
            edge_data = self.G[u][v][k]
            base_time = edge_data.get('base_time', 10.0)
            base_speed_kmh = edge_data.get('speed_kmh', 25.0)
            if crawler_speed_kmh <= base_speed_kmh:
                penalty_factor = base_speed_kmh / crawler_speed_kmh
            else:
                penalty_factor = 1.0
            penalty_factor = min(penalty_factor, 10.0)
            self.bg_weights[(u, v, k)] = base_time * penalty_factor

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
                        neighbor_edge = self.G[node][neighbor][neighbor_k]
                        if not neighbor_edge.get('is_bus_route', False):
                            neighbor_base = neighbor_edge.get('base_time', 10.0)
                            new_weight = neighbor_base * spillover_penalty
                            current = self.bg_weights.get((node, neighbor, neighbor_k), neighbor_base)
                            if current < new_weight:
                                self.bg_weights[(node, neighbor, neighbor_k)] = new_weight

        # Atomic pointer swap: GIL đảm bảo an toàn
        self.active_weights = self.bg_weights.copy()

    def batch_apply_traffic_penalty(self, traffic_data: list, spillover_alpha: float = 0.15):
        """
        Ghi toàn bộ penalty vào bg_weights, swap pointer MỘT LẦN ở cuối.
        Tránh copy dict N lần khi có N segments.
        """
        for item in traffic_data:
            segment_id = item.get('segment_id')
            crawler_speed_kmh = item.get('speed_kmh')
            if not segment_id or not crawler_speed_kmh:
                continue

            target_edges = self.segment_index.get(segment_id, [])
            if not target_edges:
                continue

            for u, v, k in target_edges:
                edge_data = self.G[u][v][k]
                base_time = edge_data.get('base_time', 10.0)
                base_speed_kmh = edge_data.get('speed_kmh', 25.0)
                if crawler_speed_kmh <= base_speed_kmh:
                    penalty_factor = base_speed_kmh / crawler_speed_kmh
                else:
                    penalty_factor = 1.0
                penalty_factor = min(penalty_factor, 10.0)
                self.bg_weights[(u, v, k)] = base_time * penalty_factor

                if penalty_factor > 1.0:
                    spillover_penalty = 1 + (penalty_factor - 1) * spillover_alpha
                else:
                    spillover_penalty = 1.0

                for node in (u, v):
                    for neighbor in self.G.successors(node):
                        if neighbor in (u, v):
                            continue
                        for neighbor_k in self.G[node][neighbor]:
                            neighbor_edge = self.G[node][neighbor][neighbor_k]
                            if not neighbor_edge.get('is_bus_route', False):
                                neighbor_base = neighbor_edge.get('base_time', 10.0)
                                new_weight = neighbor_base * spillover_penalty
                                current = self.bg_weights.get((node, neighbor, neighbor_k), neighbor_base)
                                if current < new_weight:
                                    self.bg_weights[(node, neighbor, neighbor_k)] = new_weight

        # Swap MỘT LẦN duy nhất
        self.active_weights = self.bg_weights.copy()

    def reset_traffic(self):
        """Reset toàn bộ về base_time"""
        self.bg_weights = {
            (u, v, k): data.get('base_time', 10.0)
            for u, v, k, data in self.G.edges(keys=True, data=True)
        }
        self.active_weights = self.bg_weights.copy()