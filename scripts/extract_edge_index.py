import numpy as np
import pickle
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
    weight_list = []
    
    for u, v, k in tqdm(G.edges(keys=True), desc="Adjacency"):
        e1_id = edge_to_id[(u, v, k)]
        speed1 = G[u][v][k].get('speed_kmh', 15.0)
        
        # Tìm các cạnh kề (v, w)
        for w in G.successors(v):
            for k2 in G[v][w]:
                e2_id = edge_to_id[(v, w, k2)]
                speed2 = G[v][w][k2].get('speed_kmh', 15.0)
                
                # Trọng số lan truyền tỷ lệ theo tốc độ
                weight = speed2 / (speed1 + speed2)
                
                src_list.append(e1_id)
                dst_list.append(e2_id)
                weight_list.append(weight)
                
    edge_index = np.array([src_list, dst_list], dtype=np.int32)
    edge_weight = np.array(weight_list, dtype=np.float32)
    print(f"Line Graph edges: {edge_index.shape[1]:,}")
    print(f"Sample weights: {edge_weight[:5]}")
    
    return id_to_edge, edge_index, edge_weight

if __name__ == "__main__":
    subgraph_path = "data/hcmc_routing_brain_v2_subgraph.pkl"
    id_to_edge, edge_index, edge_weight = create_edge_mapping_and_adjacency(subgraph_path)
    np.save("data/edge_index.npy", edge_index)
    np.save("data/edge_weight.npy", edge_weight)
    with open("data/id_to_edge.pkl", "wb") as f:
        pickle.dump(id_to_edge, f)
    print("Edge index saved to data/edge_index.npy")
    print("Edge weight saved to data/edge_weight.npy")
    print("ID to edge mapping saved to data/id_to_edge.pkl")