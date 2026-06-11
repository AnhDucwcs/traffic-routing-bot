import osmnx as ox
import networkx as nx
import json
import pathlib
import pickle
from tqdm import tqdm
import concurrent.futures
import os
from pyproj import Transformer

WORKER_G = None

def _init_worker(graph_path_str):
    global WORKER_G
    try:
        with open(graph_path_str, 'rb') as f:
            WORKER_G = pickle.load(f)
    except Exception as e:
        print(f"\n[WORKER ERROR] Không thể load đồ thị: {e}")
        WORKER_G = None

def _process_segment(item):
    key, data = item
    coords = data.get('path_coords', [])
    if not coords:
        return key, []

    if WORKER_G is None:
        raise RuntimeError("Đồ thị WORKER_G chưa được nạp vào RAM của tiến trình con!")

    transformer = Transformer.from_crs("EPSG:4326", WORKER_G.graph['crs'], always_xy=True)
    
    lngs = [pt[1] for pt in coords]
    lats = [pt[0] for pt in coords]
    
    X, Y = transformer.transform(lngs, lats)

    raw_nodes = ox.distance.nearest_nodes(WORKER_G, X, Y)

    # 1. Khử trùng lặp các node Map Matching thô liền kề
    clean_nodes = []
    for node in raw_nodes:
        native_node = int(node) 
        if not clean_nodes or native_node != clean_nodes[-1]:
            clean_nodes.append(native_node)
            
    # 2. BẬT KHỐI NỘI SUY: Trám các giao lộ bị thiếu giữa các tọa độ GPS
    interpolated_nodes = []
    for i in range(len(clean_nodes) - 1):
        u = clean_nodes[i]
        v = clean_nodes[i + 1]
        
        try:
            # Thử tìm đường đi xuôi chiều nối trực tiếp u -> v
            path = nx.shortest_path(WORKER_G, source=u, target=v, weight='length')
            # Thêm chuỗi đường đi vào mảng (bỏ phần tử cuối để tránh trùng lặp với cặp tiếp theo)
            interpolated_nodes.extend(path[:-1])
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            try:
                # FALLBACK: Nếu dính đường một chiều bị ngược trên bản đồ OSM, thử tìm đường ngược v -> u
                path = nx.shortest_path(WORKER_G, source=v, target=u, weight='length')
                # Đảo ngược chuỗi kết quả lại để giữ đúng hướng di chuyển của tuyến xe
                interpolated_nodes.extend(path[::-1][:-1])
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                # Nếu bế tắc hoàn toàn (lỗi đồ thị cô lập), giữ nguyên node u để bảo toàn dữ liệu gốc
                interpolated_nodes.append(u)
                
    # Đừng quên đóng dấu nút cuối cùng của hành trình
    if clean_nodes:
        interpolated_nodes.append(clean_nodes[-1])

    # 3. Lọc lại trùng lặp liền kề một lần cuối để đảm bảo sợi xích node sạch 100%
    final_nodes = []
    for node in interpolated_nodes:
        if not final_nodes or node != final_nodes[-1]:
            final_nodes.append(node)

    return key, final_nodes

def map_segments_to_graph():
    src_dir = pathlib.Path(__file__).parent.parent
    graph_file = src_dir / "data" / "hcmc_routing_brain_v1.pkl"
    segments_file = src_dir / "data" / "segment_lengths_v1.json"
    output_file = src_dir / "data" / "segment_lengths_v2.json"

    with open(segments_file, "r", encoding="utf-8") as f:
        segments = json.load(f)

    print("Bắt đầu Map Matching (Ánh xạ tọa độ GPS xuống Đồ thị)...\n")
    items = list(segments.items())

    max_workers = min(8, os.cpu_count() or 1) 

    # Khởi chạy đa luồng
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers, initializer=_init_worker, initargs=(str(graph_file),)) as executor:
        futures = {executor.submit(_process_segment, item): item[0] for item in items}
        
        for fut in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Mapping segments"):
            key = futures[fut]
            try:
                _, nodes = fut.result()
                segments[key]['osmnx_nodes'] = nodes
            except Exception as e:
                print(f"\n[LỖI MAPPING] Segment {key} thất bại: {e}")
                segments[key]['osmnx_nodes'] = []

    print(f"\nĐang lưu tại {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
        
    print("Hoàn tất! Cấu trúc dữ liệu đã sẵn sàng để đẩy lên RAM.")

if __name__ == "__main__":
    map_segments_to_graph()