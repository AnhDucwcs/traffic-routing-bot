import time
import pickle
import json
from pathlib import Path
from app.core.logger import logger

def load_routing_graph():
    logger.info("Loading routing graph from disk...")
    start_time = time.perf_counter()
    
    curent_dir = Path(__file__).resolve().parent
    src_dir = curent_dir.parent.parent.parent
    graph_path = src_dir / "data" / "hcmc_routing_brain_v2.pkl"
    
    if not graph_path.exists():
        raise FileNotFoundError(f"Routing graph file not found at {graph_path}. Please run the build_offline_graph.py script first.")
    
    with open(graph_path, "rb") as f:
        routing_graph = pickle.load(f)
        logger.info(f"Routing graph loaded with {len(routing_graph.nodes)} nodes and {len(routing_graph.edges)} edges.")
    
    end_time = time.perf_counter()
    logger.info(f"Routing graph loaded in {end_time - start_time:.2f} seconds.")
    return routing_graph

def load_segment_lengths():
    logger.info("Loading segment lengths from disk...")
    
    curent_dir = Path(__file__).resolve().parent
    src_dir = curent_dir.parent.parent.parent
    lengths_path = src_dir / "data" / "segment_lengths_v2.json"
    
    with open(lengths_path, 'r', encoding='utf-8') as f:
            segment_lengths = json.load(f)
    
    logger.info(f"Segment lengths loaded.")
    return segment_lengths

def load_route_stop_sequence():
    logger.info("Loading route stop sequence from disk...")
    
    curent_dir = Path(__file__).resolve().parent
    src_dir = curent_dir.parent.parent.parent
    sequence_path = src_dir / "data" / "route_stop_sequence.json"
    
    with open(sequence_path, 'r', encoding='utf-8') as f:
            route_stop_sequence = json.load(f)
    
    logger.info(f"Route stop sequence loaded.")
    return route_stop_sequence

def load_turn_penalties():
    logger.info("Loading turn penalties from disk...")
    
    curent_dir = Path(__file__).resolve().parent
    src_dir = curent_dir.parent.parent.parent
    penalties_path = src_dir / "data" / "turn_penalties.pkl"
    
    with open(penalties_path, 'rb') as f:
            turn_penalties = pickle.load(f)
    
    logger.info(f"Turn penalties loaded.")
    return turn_penalties

def load_feather_data(target_crs):
    logger.info("Loading feather data from disk...")
    
    curent_dir = Path(__file__).resolve().parent
    src_dir = curent_dir.parent.parent.parent
    feather_path = src_dir / "data" / "hcmc_geometry_store.feather"
    
    if not feather_path.exists():
        raise FileNotFoundError(f"Feather data file not found at {feather_path}. Please run the build_offline_graph.py script first.")
    
    import geopandas as gpd
    from shapely.strtree import STRtree
    import gc
    
    edges_gdf = gpd.read_feather(feather_path)
    edges_gdf = edges_gdf.set_crs("EPSG:4326", allow_override=True).to_crs(target_crs)  # Bịp thật, đã chuyển graph sang UTM rồi mà geometry vẫn là độ, xong nó còn gắn nhãn là UTM nữa chứ :)))
    
    # Build STRtree for spatial indexing
    geometries = edges_gdf['geometry'].tolist()
    edge_ids = edges_gdf[['u', 'v', 'key']].to_numpy()  # Kèm theo mảng ID để biết cạnh nào tương ứng với hình nào
    strtree = STRtree(geometries)
    
    # Lưu geometries và edge_ids vào một dictionary để truy xuất sau này
    geom_dict = {}
    for idx, row in edges_gdf.iterrows():
        geom_dict[(row['u'], row['v'], row['key'])] = row['geometry']
    
    del edges_gdf
    gc.collect()
    
    logger.info("STRtree built and feather data loaded.")
    return strtree, edge_ids, geom_dict