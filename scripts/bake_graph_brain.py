import math

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
        speed_kmh = 15.0
        if isinstance(hw, list): 
            hw = hw[0]
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

def calc_turn_penalty(graph, prev_node, current_node, next_node):
    if prev_node is None or next_node is None:
        return 0.0
        
    # 1. BỘ LỌC NGÃ TƯ: Bỏ qua các "khúc cua" (Shape Nodes)
    # out_degree <= 1 nghĩa là đến node này chỉ có 1 đường duy nhất để đi tiếp -> Không phải ngã rẽ
    if graph.out_degree(current_node) <= 1:
        return 0.0 

    # 2. XÁC ĐỊNH ĐỊA HÌNH: Đang ở hẻm hay đại lộ?
    try: 
        # Lấy loại đường của mép rẽ tiếp theo
        edge_data = graph[current_node][next_node]
        first_key = list(edge_data.keys())[0]
        hw = edge_data[first_key].get('highway', 'unclassified')
        if isinstance(hw, list): 
            hw = hw[0]
    except Exception:
        hw = 'unclassified'

    # Nhận diện hẻm
    # Tôi tính trọng số phạt cho hẻm nhẹ hơn để khuyến khích A* chọn đường hẻm nếu có thể
    is_alley = hw in ['residential', 'living_street', 'service', 'tertiary', 'tertiary_link']

    # 3. TÍNH TOÁN LƯỢNG GIÁC
    try: 
        u_x, u_y = graph.nodes[prev_node]['x'], graph.nodes[prev_node]['y']
        v_x, v_y = graph.nodes[current_node]['x'], graph.nodes[current_node]['y']
        w_x, w_y = graph.nodes[next_node]['x'], graph.nodes[next_node]['y']
    except KeyError:
        return 0.0
    
    v1_x, v1_y = v_x - u_x, v_y - u_y
    v2_x, v2_y = w_x - v_x, w_y - v_y
    
    cross_prod = v1_x * v2_y - v1_y * v2_x
    dot_prod = v1_x * v2_x + v1_y * v2_y
    
    angle_rad = math.atan2(cross_prod, dot_prod)
    angle_deg = math.degrees(angle_rad)

    if abs(angle_deg) > 150:
        return 15.0 if is_alley else 45.0  
        
    elif 20 < angle_deg <= 150:
        return 5.0 if is_alley else 25.0  
        
    elif -150 <= angle_deg < -20:
        return 0.0 if is_alley else 5.0   
        
    else:
        return 0.0   # Đi thẳng
    
def bake_turn_penalties():
    src_dir = pathlib.Path(__file__).parent.parent
    graph_file = src_dir / "data" / "hcmc_routing_brain_v2.pkl"
    output_file = src_dir / "data" / "turn_penalties.pkl"
    turn_penalties = {}
    
    print("1. Nạp đồ thị dã được xử lý vào RAM...")
    with open(graph_file, 'rb') as f:
        G = pickle.load(f)
    
    # Quét toàn bộ node trong đồ thị
    for u in tqdm(G.nodes, desc="Baking Turn Penalties"):
        for prev_u in G.predecessors(u):
            for v in G.successors(u):
                if prev_u == v: # Bỏ qua trường hợp quay đầu đi ngược lại đúng cạnh cũ
                    continue
                penalty = calc_turn_penalty(G, prev_u, u, v)
                if penalty > 0.0:
                    turn_penalties[(prev_u, u, v)] = penalty
                    
    with open(output_file, 'wb') as f:
        pickle.dump(turn_penalties, f)
    print(f"Đã cooked {len(turn_penalties)} góc rẽ phạt!")

if __name__ == "__main__":
    # bake_graph_brain()
    bake_turn_penalties()  # hoặc cho bake_graph_brain() trả về G rồi sau đó truyền G vào bake_turn_penalties(G) để tránh phải load lại đồ thị một lần nữa.