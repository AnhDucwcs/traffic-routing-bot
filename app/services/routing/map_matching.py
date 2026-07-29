import osmnx as ox
from shapely.geometry import LineString, Point

class MapMatcher:
    def __init__(self, strtree, edge_ids, geom_dict):
        self.strtree = strtree
        self.edge_ids = edge_ids
        self.geom_dict = geom_dict

    def snap_to_edge(self, x: float, y: float, max_dist_m: float = 50.0):
        """
        Input: Tọa độ gốc
        Output: (u, v, k, projected_lat, projected_lng, distance_to_edge)
        """
        point = Point(x, y)
        nearest_idx = self.strtree.nearest(point)
        if nearest_idx is None:
            raise ValueError("Bản đồ trống, không có dữ liệu đường bộ.")
        
        # Lấy cạnh gần nhất
        u, v, key = self.edge_ids[nearest_idx]
        line = self.geom_dict.get((u, v, key))
        
        # Tính toán điểm được chiếu lên cạnh
        distance_m = point.distance(line)
        if distance_m > max_dist_m:
            raise ValueError(f"Khoảng cách tới đường bộ quá xa ({distance_m:.1f}m > {max_dist_m}m). Không thể tìm đường!")
        
        projected_point = line.interpolate(line.project(point))
        return (u, v, key, projected_point.x, projected_point.y, distance_m)