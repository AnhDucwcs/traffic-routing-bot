import pandas as pd
import numpy as np
import networkx as nx
import pickle
import json
import os
from datetime import datetime
from tqdm import tqdm

def create_edge_mapping_and_adjacency(subgraph_path):
    print(f"Loading subgraph from {subgraph_path}...")
    with open(subgraph_path, 'rb') as f:
        G = pickle.load(f)
    
    # 1. Map each edge (u, v, k) to an integer ID (0 to E-1)
    edge_to_id = {}
    id_to_edge = {}
    
    for i, (u, v, k) in enumerate(G.edges(keys=True)):
        edge_to_id[(u, v, k)] = i
        id_to_edge[i] = (u, v, k)
        
    num_edges = len(edge_to_id)
    print(f"Total Edges (STGCN Nodes): {num_edges:,}")
    
    # 2. Build Adjacency for Line Graph
    # Edge e1=(u,v) is connected to Edge e2=(v,w)
    print("Building Line Graph Adjacency...")
    src_list = []
    dst_list = []
    
    for u, v, k in tqdm(G.edges(keys=True), desc="Adjacency"):
        e1_id = edge_to_id[(u, v, k)]
        # Tìm các cạnh kề (v, w)
        for w in G.successors(v):
            for k2 in G[v][w]:
                e2_id = edge_to_id[(v, w, k2)]
                src_list.append(e1_id)
                dst_list.append(e2_id)
                
    edge_index = np.array([src_list, dst_list], dtype=np.int32)
    print(f"Line Graph edges: {edge_index.shape[1]:,}")
    
    return edge_to_id, id_to_edge, edge_index, num_edges

def load_segment_mapping(segment_file, G, edge_to_id):
    with open(segment_file, 'r', encoding='utf-8') as f:
        segment_lengths = json.load(f)
        
    segment_to_edge_ids = {}
    for seg_id, data in segment_lengths.items():
        nodes = data.get('osmnx_nodes', [])
        edge_ids = []
        for i in range(len(nodes) - 1):
            u = nodes[i]
            v = nodes[i + 1]
            if G.has_edge(u, v):
                for k in G[u][v]:
                    if G[u][v][k].get('is_bus_route', False) and (u, v, k) in edge_to_id:
                        edge_ids.append(edge_to_id[(u, v, k)])
        segment_to_edge_ids[seg_id] = edge_ids
    return segment_to_edge_ids

def process_parquet(parquet_file, start_date, end_date, edge_to_id, id_to_edge, segment_to_edge_ids, baseline_dict, num_edges):
    print(f"\nProcessing {parquet_file}...")
    df = pd.read_parquet(parquet_file)
    
    # Lọc nhiễu (0-60 km/h)
    df = df[(df['instant_speed_kmh'] > 0) & (df['instant_speed_kmh'] <= 60)]
    
    # Tạo chuỗi thời gian 15 phút
    time_index = pd.date_range(start=start_date, end=end_date, freq='15min')
    num_steps = len(time_index)
    print(f"Time steps ({start_date} to {end_date}): {num_steps}")
    
    # Ánh xạ datetime -> step_index
    # Giảm timestamp về đầu khung 15 phút
    df['dt'] = df['timestamp'].dt.floor('15min')
    
    # Map 'dt' to index
    time_to_step = {dt: i for i, dt in enumerate(time_index)}
    df['step'] = df['dt'].map(time_to_step)
    df = df.dropna(subset=['step'])
    df['step'] = df['step'].astype(int)
    
    # Tạo cột segment_id
    df['segment_id'] = df['to_current_stop_id'].astype(str) + "_" + df['to_next_stop_id'].astype(str)
    
    # Khởi tạo ma trận X = (T, N, 1) chứa toàn NaN
    X = np.full((num_steps, num_edges, 1), np.nan, dtype=np.float32)
    
    # Nhúng tốc độ vào ma trận
    print("Mapping to OSM Edges...")
    grouped = df.groupby(['step', 'segment_id'])['instant_speed_kmh'].mean().reset_index()
    
    for row in tqdm(grouped.itertuples(index=False), total=len(grouped)):
        step = row.step
        seg_id = row.segment_id
        speed = row.instant_speed_kmh
        
        edge_ids = segment_to_edge_ids.get(seg_id, [])
        for e_id in edge_ids:
            # Nếu có nhiều segment đè lên 1 edge, ta dùng np.nanmean để trung bình sau. 
            # Nhưng để đơn giản đuôi, cứ gán thẳng, thằng nào tới sau ghi đè (không đáng kể vì chung route).
            X[step, e_id, 0] = speed
            
    # Imputation (Điền khuyết)
    print("Imputing missing values...")
    # Bước 1: Linear Interpolation theo thời gian (T)
    # Tuyến tính hoá giúp mượt mà dữ liệu giữa 2 điểm đo được, tránh hiện tượng giật cục (staircase effect) của ffill
    X_2d = X.reshape(num_steps, num_edges)
    df_X = pd.DataFrame(X_2d)
    df_X = df_X.interpolate(method='linear', limit_direction='forward')
    
    # Bước 2: Numpy Vectorized Imputation
    print("Vectorized Baseline Imputation...")
    X_mat = df_X.values # shape (T, N)
    
    dow = time_index.weekday
    day_types = np.where(dow < 4, 1, np.where(dow == 4, 2, 3))
    time_slots = time_index.hour * 4 + time_index.minute // 15
    
    B = np.full((num_steps, num_edges), 25.0, dtype=np.float32)
    for e_id in tqdm(range(num_edges), desc="Building Baseline Matrix"):
        if not np.isnan(X_mat[:, e_id]).any():
            continue
        u, v, k = id_to_edge[e_id]
        for dt in [1, 2, 3]:
            for slot in range(96):
                val = baseline_dict.get((u, v, dt, slot), 25.0)
                if val != 25.0:
                    mask = (day_types == dt) & (time_slots == slot)
                    B[mask, e_id] = val
                    
    nan_mask = np.isnan(X_mat)
    X_mat[nan_mask] = B[nan_mask]
    
    X = X_mat.reshape(num_steps, num_edges, 1)
    
    # Kiểm tra NaNs cuối cùng
    nans = np.isnan(X).sum()
    print(f"Remaining NaNs: {nans}")
    return X

def main():
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    subgraph_path = os.path.join(data_dir, 'hcmc_routing_brain_v2_subgraph.pkl')
    segment_file = os.path.join(data_dir, 'segment_lengths_v2.json')
    baseline_file = os.path.join(data_dir, 'edge_historical_baseline.pkl')
    
    # 1. Map Edges & Adjacency
    edge_to_id, id_to_edge, edge_index, num_edges = create_edge_mapping_and_adjacency(subgraph_path)
    
    # 2. Segment Mapping
    with open(subgraph_path, 'rb') as f:
        G = pickle.load(f)
    segment_to_edge_ids = load_segment_mapping(segment_file, G, edge_to_id)
    
    # 3. Baseline for imputation
    with open(baseline_file, 'rb') as f:
        baseline_dict = pickle.load(f)
        
    # 4. Train Data (June 2026)
    # Tháng 6 có 30 ngày (từ 01/06 đến 30/06)
    train_x = process_parquet(
        os.path.join(data_dir, 'traffic_2026-06.parquet'),
        '2026-06-01 00:00:00', '2026-06-30 23:45:00',
        edge_to_id, id_to_edge, segment_to_edge_ids, baseline_dict, num_edges
    )
    
    # 5. Val Data (July 2026 - first 15 days)
    # Dataset traffic_2026-07.parquet có dung lượng nhỏ hơn (17MB), chắc chỉ chạy đến giữa tháng
    val_x = process_parquet(
        os.path.join(data_dir, 'traffic_2026-07.parquet'),
        '2026-07-01 00:00:00', '2026-07-15 23:45:00',
        edge_to_id, id_to_edge, segment_to_edge_ids, baseline_dict, num_edges
    )
    
    # 6. Save Numpy Arrays
    out_path = os.path.join(data_dir, 'stgcn_dataset.npz')
    
    np.savez_compressed(
        out_path,
        edge_index=edge_index,
        train_x=train_x,
        val_x=val_x,
        edge_to_id=edge_to_id,
        id_to_edge=id_to_edge
    )
    
    print(f"\nSuccessfully saved Numpy dataset to {out_path} ({os.path.getsize(out_path)/1024/1024:.2f} MB)")

if __name__ == "__main__":
    main()
