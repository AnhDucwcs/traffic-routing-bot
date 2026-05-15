import time
import pickle
from pathlib import Path
from app.core.logger import logger

def load_routing_graph():
    logger.info("Loading routing graph from disk...")
    start_time = time.perf_counter()
    
    curent_dir = Path(__file__).resolve().parent
    src_dir = curent_dir.parent.parent.parent
    graph_path = src_dir / "data" / "hcmc_routing_brain.pkl"
    
    if not graph_path.exists():
        raise FileNotFoundError(f"Routing graph file not found at {graph_path}. Please run the build_offline_graph.py script first.")
    
    with open(graph_path, "rb") as f:
        routing_graph = pickle.load(f)
        logger.info(f"Routing graph loaded with {len(routing_graph.nodes)} nodes and {len(routing_graph.edges)} edges.")
    
    end_time = time.perf_counter()
    logger.info(f"Routing graph loaded in {end_time - start_time:.2f} seconds.")
    return routing_graph