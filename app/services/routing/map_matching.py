import osmnx as ox
from shapely.geometry import LineString, Point

class MapMatcher:
    def __init__(self, strtree, edge_ids, geom_dict, valid_edges=None):
        self.strtree = strtree
        self.edge_ids = edge_ids
        self.geom_dict = geom_dict
        self.valid_edges = valid_edges

    def snap_to_edge(self, x: float, y: float, max_dist_m: float = 50.0):
        """
        Input: Tọa độ gốc
        Output: (u, v, k, projected_lat, projected_lng, distance_to_edge)
        """
        point = Point(x, y)
        
        # Lấy tất cả cạnh trong bán kính max_dist_m
        buffered = point.buffer(max_dist_m)
        indices_in_buffer = self.strtree.query(buffered)
        
        if len(indices_in_buffer) == 0:
            raise ValueError(f"Không có đường bộ nào trong bán kính {max_dist_m}m xung quanh điểm này.")
            
        distances = []
        for idx in indices_in_buffer:
            u, v, key = self.edge_ids[idx]
            line = self.geom_dict.get((u, v, key))
            dist = point.distance(line)
            distances.append((dist, idx, u, v, key, line))
            
        distances.sort(key=lambda item: item[0])
        
        best_match = None
        for dist, idx, u, v, key, line in distances:
            if self.valid_edges is not None:
                # Nếu cạnh không nằm trong main component, bỏ qua
                if (u, v) not in self.valid_edges:
                    continue
            best_match = (dist, idx, u, v, key, line)
            break
            
        if best_match is None:
            raise ValueError(f"Có đường bộ trong bán kính {max_dist_m}m nhưng tất cả đều bị cô lập (đảo / hẻm cụt).")
            
        dist, idx, u, v, key, line = best_match
        projected_point = line.interpolate(line.project(point))
        
        return (u, v, key, projected_point.x, projected_point.y, dist)