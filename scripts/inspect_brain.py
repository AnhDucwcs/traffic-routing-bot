import pickle
import random
import pathlib

def inspect_brain():
    src_dir = pathlib.Path(__file__).parent.parent
    graph_file = src_dir / "data" / "hcmc_routing_brain_v2.pkl"

    print("Đang nạp bộ não V2 lên bàn mổ...")
    with open(graph_file, 'rb') as f:
        G = pickle.load(f)

    # 1. Thống kê tổng quan
    print("\n=== THỐNG KÊ TỔNG QUAN ===")
    print(f"- Tổng số Ngã tư (Nodes): {len(G.nodes):,}")
    print(f"- Tổng số Đoạn đường (Edges): {len(G.edges):,}")

    # 2. Phân loại đường
    bus_edges = []
    normal_edges = []
    
    for u, v, k, data in G.edges(keys=True, data=True):
        if data.get('is_bus_route', False):
            bus_edges.append(data)
        else:
            normal_edges.append(data)

    print(f"- Đoạn đường Ưu tiên (Xe buýt): {len(bus_edges):,}")
    print(f"- Đoạn đường Thường (Xe máy): {len(normal_edges):,}")

    # 3. Soi chi tiết (Khám sức khỏe dữ liệu)
    print("\n=== SOI CHI TIẾT: 1 ĐOẠN ĐƯỜNG XE BUÝT NGẪU NHIÊN ===")
    if bus_edges:
        sample_bus = random.choice(bus_edges)
        for key, value in sample_bus.items():
            print(f"  + {key}: {value}")

    print("\n=== SOI CHI TIẾT: 1 CON HẺM NGẪU NHIÊN ===")
    if normal_edges:
        # Cố tình tìm 1 con hẻm (residential) để xem nó có bị phạt nặng tốc độ không
        alleys = [e for e in normal_edges if e.get('highway') in ['residential', 'living_street']]
        sample_alley = random.choice(alleys) if alleys else random.choice(normal_edges)
        for key, value in sample_alley.items():
            print(f"  + {key}: {value}")

if __name__ == "__main__":
    inspect_brain()