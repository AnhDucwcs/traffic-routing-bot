import networkx as nx
import json
import pathlib
import pickle
from tqdm import tqdm

def bake_graph_brain():
    src_dir = pathlib.Path(__file__).parent.parent
    graph_file = src_dir / "data" / "hcmc_routing_brain_v1.pkl"
    segments_file = src_dir / "data" / "segment_lengths_v2.json"
    output_file = src_dir / "data" / "hcmc_routing_brain_v2.pkl"
    
    print("1. Nạp đồ thị thô vào RAM...")
    with open(graph_file, 'rb') as f:
        G = pickle.load(f)

    print("2. Quét đồ thị: Tiêm giá trị phạt vào các cạnh...")
    for u, v, key, data in tqdm(G.edges(keys=True, data=True), desc="Baking edges"):
        data['is_bus_route'] = False

        hw = data.get('highway', 'unclassified')
        if isinstance(hw, list): 
            hw = hw[0]

        maxspeed = data.get('maxspeed', None)
        if isinstance(maxspeed, list):
            maxspeed = maxspeed[0]
            
        try:
            # Ép kiểu an toàn (OSM đôi khi lưu chuỗi như '50', '60')
            speed_kmh = float(maxspeed)
        except (TypeError, ValueError):
            # 2. Fallback: Nếu không có maxspeed, tự nội suy từ loại đường
            if hw in ['trunk', 'trunk_link', 'primary', 'primary_link']:
                speed_kmh = 45.0
            elif hw in ['secondary', 'secondary_link']:
                speed_kmh = 40.0
            elif hw in ['tertiary', 'tertiary_link']:
                speed_kmh = 35.0
            elif hw in ['residential', 'living_street']:
                speed_kmh = 30.0
            else:
                speed_kmh = 20.0

        # Lấy chiều dài (mét)
        length = data.get('length', 0.0)
        if isinstance(length, list): 
            length = length[0]
        
        try:
            length = float(length)
        except Exception:
            length = 10.0

        speed_ms = speed_kmh * 1000 / 3600
        base_time = length / speed_ms

        # Tiêm các thông số mới vào Edge
        data['base_time'] = round(base_time, 2)
        data['current_weight'] = round(base_time, 2) # Biến này sẽ bị Crawler thay đổi liên tục
        data['speed_kmh'] = speed_kmh

    print("3. Nạp dữ liệu lộ trình xe buýt (V2)...")
    with open(segments_file, "r", encoding="utf-8") as f:
        segments = json.load(f)

    print("4. Đóng dấu Ưu tiên (Whitelist) cho các trục đường xe buýt...")
    bus_edges_count = 0
    for segment_key, route_data in tqdm(segments.items(), desc="Tagging Bus Routes"):
        nodes = route_data.get('osmnx_nodes', [])
        
        # Cần ít nhất 2 Node để tạo thành 1 Cạnh (Edge)
        if len(nodes) < 2:
            continue

        # Lặp qua từng cặp Node liền kề (u -> v)
        for i in range(len(nodes) - 1):
            u = nodes[i]
            v = nodes[i + 1]

            # Kiểm tra xem cạnh này có tồn tại xuôi chiều không
            # Giả sử con đường đó là 2 chiều, có thể dữ liệu OSM chỉ lưu 1 chiều
            # Tôi sẽ coi như cả 2 chiều đều là đường xe buýt nếu một trong hai chiều có tồn tại trong đồ thị
            if G.has_edge(u, v):
                for k in G[u][v]:
                    if not G[u][v][k].get('is_bus_route', False):
                        G[u][v][k]['is_bus_route'] = True
                        bus_edges_count += 1
            # FALLBACK: Nếu không có xuôi chiều, kiểm tra ngược chiều
            elif G.has_edge(v, u):
                for k in G[v][u]:
                    if not G[v][u][k].get('is_bus_route', False):
                        G[v][u][k]['is_bus_route'] = True
                        bus_edges_count += 1

    print(f"Đã đánh dấu {bus_edges_count} đoạn đường thuộc mạng lưới xe buýt.")

    print(f"\n5. Nấu xong! Đang lưu bộ não mới ra {output_file}...")
    with open(output_file, 'wb') as f:
        pickle.dump(G, f)

    print("Hoàn tất! Đồ thị V2 đã sẵn sàng tích hợp với Crawler.")

if __name__ == "__main__":
    bake_graph_brain()