import json
import pickle
import pytz
from pathlib import Path
from datetime import datetime
from app.core.logger import logger

# ponytail: Night mode 21:30-05:30, A* fallback về base_time
NIGHT_START_SLOT = 86   # 21*4 + 30//15
NIGHT_END_SLOT = 22     # 5*4 + 30//15

class TrafficManager:
    def __init__(self, routing_graph, turn_penalties):
        self.G = routing_graph
        self.turn_penalties = turn_penalties
        self.segment_index = {}
        
        # Base weights (bất biến, dùng làm fallback)
        self._base_weights = {
            (u, v, k): data.get('base_time', 10.0)
            for u, v, k, data in self.G.edges(keys=True, data=True)
        }
        self.bg_weights = self._base_weights.copy()

        # Load historical baseline cho T15/T30/T45
        self._edge_baseline = {}
        self._load_historical_baseline()

        # Cache slot để tránh rebuild khi chưa đổi khung 15 phút
        self._cached_slot = -1
        self._future_dicts = (self._base_weights.copy(), self._base_weights.copy(), self._base_weights.copy())

        # time_weights: (T0, T15, T30, T45) - Atomic swap via GIL
        self.time_weights = (self._base_weights.copy(), *self._future_dicts)

    @property
    def active_weights(self):
        """Backward compat: trả về T0 cho code cũ chưa migrate."""
        return self.time_weights[0]

    def _load_historical_baseline(self):
        baseline_path = Path(__file__).parent.parent.parent / "data" / "edge_historical_baseline.pkl"
        if baseline_path.exists():
            with open(baseline_path, 'rb') as f:
                self._edge_baseline = pickle.load(f)
            logger.info(f"Loaded {len(self._edge_baseline):,} historical baseline records.")
        else:
            logger.warning("Historical baseline not found. Future predictions disabled.")

    def _get_day_type(self, weekday):
        if weekday in (0, 1, 2, 3): return 1
        if weekday == 4: return 2
        return 3

    def _build_future_dict(self, day_type, time_slot):
        """Xây 1 flat dict trọng số tương lai từ historical baseline."""
        # Night mode -> trả về base_time, không cần tính toán
        if time_slot >= NIGHT_START_SLOT or time_slot < NIGHT_END_SLOT:
            return self._base_weights.copy()

        result = self._base_weights.copy()
        for (u, v, k), base_time in result.items():
            speed = self._edge_baseline.get((u, v, day_type, time_slot))
            if speed and speed > 0:
                length_m = self.G[u][v][k].get('length', 0.0)
                if isinstance(length_m, list):
                    length_m = length_m[0]
                try:
                    length_m = float(length_m)
                except Exception:
                    continue
                # ponytail: speed km/h -> travel time seconds, one-liner
                result[(u, v, k)] = length_m / (speed / 3.6) + (
                    15.0 if self.G.nodes[v].get('traffic_signals', False) else 0.0
                )
        return result

    def refresh_future_weights(self):
        """Rebuild T15/T30/T45 nếu time_slot thay đổi. Gọi bởi Crawler sau batch update."""
        vn_now = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
        current_slot = vn_now.hour * 4 + vn_now.minute // 15

        if current_slot == self._cached_slot:
            return  # Chưa đổi khung 15 phút, bỏ qua

        self._cached_slot = current_slot
        dow = vn_now.weekday()

        future_dicts = []
        for offset in (1, 2, 3):  # +15, +30, +45 phút
            future_slot = (current_slot + offset) % 96
            future_dow = dow if (current_slot + offset) < 96 else (dow + 1) % 7
            day_type = self._get_day_type(future_dow)
            future_dicts.append(self._build_future_dict(day_type, future_slot))

        self._future_dicts = tuple(future_dicts)
        logger.info(f"Refreshed future weights for slot {current_slot}")

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
        Crawler ghi vào bg_weights, sau đó swap tuple sang time_weights.
        A* đọc time_weights mà không cần lock.
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

        # Atomic tuple swap: GIL đảm bảo an toàn
        self.refresh_future_weights()
        self.time_weights = (self.bg_weights.copy(), *self._future_dicts)

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
        self.refresh_future_weights()
        self.time_weights = (self.bg_weights.copy(), *self._future_dicts)

    def reset_traffic(self):
        """Reset toàn bộ về base_time"""
        self.bg_weights = {
            (u, v, k): data.get('base_time', 10.0)
            for u, v, k, data in self.G.edges(keys=True, data=True)
        }
        bw = self._base_weights
        self._future_dicts = (bw.copy(), bw.copy(), bw.copy())
        self.time_weights = (self.bg_weights.copy(), *self._future_dicts)