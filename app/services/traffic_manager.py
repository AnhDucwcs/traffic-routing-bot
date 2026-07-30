from collections import deque
import pytz
import numpy as np
from datetime import datetime
from app.core.logger import logger
from pyproj import Transformer

# ponytail: Night mode 21:30-05:30, A* fallback về base_time
NIGHT_START_SLOT = 86   # 21*4 + 30//15
NIGHT_END_SLOT = 22     # 5*4 + 30//15

class TrafficManager:
    def __init__(self, routing_graph, turn_penalties, edge_historical_baseline, id_to_edge, model):
        self.G = routing_graph
        self.turn_penalties = turn_penalties
        self.segment_index = {}

        # load ai engine
        self.ai_engine = model
        self.history_buffer = deque(maxlen=4)
        self.id_to_edge = id_to_edge
        
        # Base weights (bất biến, dùng làm fallback)
        self._base_weights = {
            (u, v, k): data.get('base_time', 10.0)
            for u, v, k, data in self.G.edges(keys=True, data=True)
        }
        self.bg_weights = self._base_weights.copy()
        
        self._base_speeds = {
            (u, v, k): data.get('speed_kmh', 15.0)
            for u, v, k, data in self.G.edges(keys=True, data=True)
        }
        self.bg_speeds = self._base_speeds.copy()

        # Load historical baseline cho T15/T30/T45
        self.edge_baseline = edge_historical_baseline

        # Cache slot để tránh rebuild khi chưa đổi khung 15 phút
        self._cached_slot = -1
        self._future_dicts = (self._base_weights.copy(), self._base_weights.copy(), self._base_weights.copy())

        # time_weights: (T0, T15, T30, T45) - Atomic swap via GIL
        self.time_weights = (self._base_weights.copy(), *self._future_dicts)

        #
        self.to_graph, self.to_wgs84 = self._get_transformers()

    def _get_transformers(self):
        graph_crs = self.G.graph.get('crs')
        if not graph_crs or str(graph_crs).upper() == 'EPSG:4326':
            return None, None
        to_graph = Transformer.from_crs('EPSG:4326', graph_crs, always_xy=True)
        to_wgs84 = Transformer.from_crs(graph_crs, 'EPSG:4326', always_xy=True)
        return to_graph, to_wgs84

    @property
    def active_weights(self):
        """Backward compat: trả về T0 cho code cũ chưa migrate."""
        return self.time_weights[0]

    def _get_day_type(self, weekday):
        if weekday in (0, 1, 2, 3): return 1
        if weekday == 4: return 2
        return 3
    
    def _get_length(self,u, v, k):
        length_m = self.G[u][v][k].get('length', 0.0)
        if isinstance(length_m, list):
            length_m = length_m[0]
        try:
            return float(length_m)
        except Exception:
            return 0.0

    def _build_future_dict(self, day_type, time_slot):
        """Xây 1 flat dict trọng số tương lai từ historical baseline."""
        # Night mode -> trả về base_time, không cần tính toán
        if time_slot >= NIGHT_START_SLOT or time_slot < NIGHT_END_SLOT:
            return self._base_weights.copy()

        result = self._base_weights.copy()
        for (u, v, k), base_time in result.items():
            speed = self.edge_baseline.get((u, v, day_type, time_slot))
            if speed and speed > 0:
                length_m = self._get_length(u, v, k)
                result[(u, v, k)] = length_m / (speed / 3.6) + (
                    15.0 if self.G.nodes[v].get('traffic_signals', False) else 0.0
                )
        return result
    
    def _extract_current_speeds_to_buffer(self, current_slot):
        N = len(self.id_to_edge)
        current_speeds = np.zeros(N, dtype=np.float32)
        for i in range(N):
            u, v, k = self.id_to_edge[i]
            speed_kmh = self.bg_speeds.get((u, v, k), self._base_speeds.get((u, v, k), 15.0))
            current_speeds[i] = speed_kmh
        
        self.history_buffer.append((current_slot, current_speeds))

    def _predict_future_weights(self):
        if len(self.history_buffer) < 4:
            logger.warning("Not enough historical data for prediction. Using base weights.")
            return None
            
        slots = [item[0] for item in self.history_buffer]
        valid = True
        for i in range(1, 4):
            expected = (slots[i-1] + 1) % 96
            if slots[i] != expected:
                valid = False
                break
                
        if not valid:
            logger.warning(f"Temporal gap detected in history buffer: slots {slots}. Clearing buffer.")
            self.history_buffer.clear()
            return None
        
        stacked_input = np.stack([item[1] for item in self.history_buffer], axis=-1)[None, :, None, :]
        
        predicted_output = self.ai_engine.predict(stacked_input)  # (1, N, horizon)
        
        return predicted_output

    def refresh_future_weights(self):
        """Rebuild T15/T30/T45 nếu time_slot thay đổi. Gọi bởi Crawler sau batch update."""
        vn_now = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
        current_slot = vn_now.hour * 4 + vn_now.minute // 15

        if current_slot == self._cached_slot:
            return  # Chưa đổi khung 15 phút, bỏ qua

        self._cached_slot = current_slot
        self._extract_current_speeds_to_buffer(current_slot)
        future_predictions = self._predict_future_weights()
        dow = vn_now.weekday()

        future_dicts = []
        if future_predictions is not None:
            N = len(self.id_to_edge)
            dict_15 = self._base_weights.copy()
            dict_30 = self._base_weights.copy()
            dict_45 = self._base_weights.copy()
            for i in range(N):
                u, v, k = self.id_to_edge[i]
                for speed, target_dict in zip((future_predictions[0, i]), (dict_15, dict_30, dict_45)):
                    if speed > 0:
                        length_m = self._get_length(u, v, k)
                        travel_time = length_m / (speed / 3.6) + (
                            15.0 if self.G.nodes[v].get('traffic_signals', False) else 0.0
                        )
                        target_dict[(u, v, k)] = travel_time
            future_dicts = [dict_15, dict_30, dict_45]
        else:
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

    def batch_apply_traffic_penalty(self, traffic_data: list, spillover_alpha: float = 0.15):
        """
        Ghi toàn bộ penalty vào bg_weights, swap pointer MỘT LẦN ở cuối.
        Tránh copy dict N lần khi có N segments.
        """
        for item in traffic_data:
            segment_id = item.get('segment_id')
            crawler_speed_kmh = item.get('speed_kmh')
            if not segment_id or crawler_speed_kmh is None:
                continue
            
            # Validate input
            crawler_speed_kmh = max(float(crawler_speed_kmh), 1.0)

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
                self.bg_speeds[(u, v, k)] = crawler_speed_kmh

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
                                    
                                neighbor_speed = neighbor_edge.get('speed_kmh', 15.0)
                                new_speed = neighbor_speed / spillover_penalty
                                current_speed = self.bg_speeds.get((node, neighbor, neighbor_k), neighbor_speed)
                                if new_speed < current_speed:
                                    self.bg_speeds[(node, neighbor, neighbor_k)] = new_speed

        # Swap MỘT LẦN duy nhất
        self.refresh_future_weights()
        self.time_weights = (self.bg_weights.copy(), *self._future_dicts)

    def reset_traffic(self):
        """Reset toàn bộ về historical_baseline của slot hiện tại, fallback về free-flow"""
        vn_now = datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
        current_slot = vn_now.hour * 4 + vn_now.minute // 15
        dow = vn_now.weekday()
        day_type = self._get_day_type(dow)
        
        self.bg_speeds = self._base_speeds.copy()
        self.bg_weights = self._base_weights.copy()
        
        # Nếu đang không phải ban đêm, nạp lịch sử làm fallback
        if current_slot < NIGHT_START_SLOT and current_slot >= NIGHT_END_SLOT:
            for (u, v, k), base_speed in self._base_speeds.items():
                hist_speed = self.edge_baseline.get((u, v, day_type, current_slot))
                if hist_speed and hist_speed > 0:
                    self.bg_speeds[(u, v, k)] = hist_speed
                    length_m = self._get_length(u, v, k)
                    self.bg_weights[(u, v, k)] = length_m / (hist_speed / 3.6) + (
                        15.0 if self.G.nodes[v].get('traffic_signals', False) else 0.0
                    )
        
        bw = self.bg_weights
        self._future_dicts = (bw.copy(), bw.copy(), bw.copy())
        self.time_weights = (self.bg_weights.copy(), *self._future_dicts)

    def apply_crowdsourced_overrides(self, reports: list, spillover_alpha: float = 0.15):
        """
        Nhận danh sách các điểm kẹt xe do người dùng báo cáo và áp dụng vào bg_weights.
        Tự động lan truyền sang các cạnh lân cận giống logic của xe buýt.
        """
        if not reports:
            return
            
        for report in reports:
            u = report.get('u')
            v = report.get('v')
            k = report.get('k')
            crawler_speed_kmh = report.get('speed_kmh')
            
            if u is None or v is None or k is None or crawler_speed_kmh is None:
                continue
            
            # Validate input
            crawler_speed_kmh = max(float(crawler_speed_kmh), 1.0)
                
            if not self.G.has_edge(u, v, k):
                continue
                
            edge_data = self.G[u][v][k]
            base_time = edge_data.get('base_time', 10.0)
            base_speed_kmh = edge_data.get('speed_kmh', 25.0)
            
            if crawler_speed_kmh <= base_speed_kmh:
                penalty_factor = base_speed_kmh / crawler_speed_kmh
            else:
                penalty_factor = 1.0
                
            penalty_factor = min(penalty_factor, 10.0)
            self.bg_weights[(u, v, k)] = base_time * penalty_factor
            self.bg_speeds[(u, v, k)] = crawler_speed_kmh
            
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
                                
                            neighbor_speed = neighbor_edge.get('speed_kmh', 15.0)
                            new_speed = neighbor_speed / spillover_penalty
                            current_speed = self.bg_speeds.get((node, neighbor, neighbor_k), neighbor_speed)
                            if new_speed < current_speed:
                                self.bg_speeds[(node, neighbor, neighbor_k)] = new_speed

        self.refresh_future_weights()
        self.time_weights = (self.bg_weights.copy(), *self._future_dicts)

    def sync_morning_baseline(self, seven_day_reports: list):
        """
        Khôi phục baseline từ ổ cứng để xóa rác RAM, sau đó đè báo cáo 7 ngày lên (Phase 1: đè 100%).
        """
        import pickle
        from pathlib import Path
        
        # 1. Nạp lại baseline gốc từ đĩa
        # Vì script này chạy trong app FastAPI, thư mục gốc thường là thư mục chứa app/
        baseline_path = Path("data/edge_historical_baseline.pkl")
        if baseline_path.exists():
            try:
                with open(baseline_path, 'rb') as f:
                    self.edge_baseline = pickle.load(f)
                logger.info("[Baseline Sync] Đã nạp lại baseline gốc từ ổ cứng.")
            except Exception as e:
                logger.error(f"[Baseline Sync] Lỗi nạp file baseline: {e}")
        else:
            logger.warning(f"[Baseline Sync] Không tìm thấy file {baseline_path}, giữ nguyên baseline hiện tại.")
            
        # 2. Đè 100% các báo cáo 7 ngày
        if seven_day_reports:
            count = 0
            for rep in seven_day_reports:
                u = rep.get('u')
                v = rep.get('v')
                day_type = rep.get('day_type')
                time_slot = rep.get('time_slot')
                speed = rep.get('speed_kmh')
                if None not in (u, v, day_type, time_slot, speed):
                    self.edge_baseline[(u, v, day_type, time_slot)] = speed
                    count += 1
            logger.info(f"[Baseline Sync] Đã ghi đè {count} reports 7 ngày lên RAM.")
            
        # 3. Áp dụng ngay vào routing hiện tại
        self.reset_traffic()