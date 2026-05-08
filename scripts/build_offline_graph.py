import os
import gc
import pickle
import pandas as pd
import networkx as nx
import osmnx as ox
from pyrosm import OSM

pd.options.mode.copy_on_write = False

PBF_INPUT = "./data/hcmc_routing_clean.osm.pbf"
OUTPUT_BRAIN = "./data/hcmc_routing_brain.pkl"
OUTPUT_GEOMETRY = "./data/hcmc_geometry_store.feather"


def main():
    if not os.path.exists(PBF_INPUT):
        print(f"Error: File not found {PBF_INPUT}. Please run osmium filter first!")
        return

    try:
        print("Loading OSM data and building graph...")
        osm = OSM(PBF_INPUT)
        nodes, edges = osm.get_network(network_type="driving+service", nodes=True)
        final_G = osm.to_graph(nodes, edges, graph_type="networkx", osmnx_compatible=True)
        
        print(f"Origin graph has {len(final_G.nodes)} nodes and {len(final_G.edges)} edges.")
        final_G = ox.truncate.largest_component(final_G, strongly=False)
        print(f"Final graph has {len(final_G.nodes)} nodes and {len(final_G.edges)} edges after keeping largest component.")
        # Project graph to UTM zone for accurate distance calculations (important for routing)
        final_G = ox.projection.project_graph(final_G)  
        
        del nodes, edges, osm
        gc.collect()

        # 3. Geometry
        print("Saving geometry for routing...")
        # Transform graph to GeoDataFrames to extract geometry for routing
        _, edges_df = ox.convert.graph_to_gdfs(final_G)
        
        # Only keep geometry for routing, reset index to have 'u', 'v', 'key' as columns
        geo_store = edges_df[['geometry']].reset_index()
        geo_store.to_feather(OUTPUT_GEOMETRY)
        print(f"Saved geometry at: {OUTPUT_GEOMETRY}")
        
        del edges_df, geo_store
        gc.collect()

        # 4. Routing
        print("Stripping graph for routing (removing geometry and OSM metadata)...")
        keep_attrs = {'osmid', 'length', 'oneway', 'highway', 'name', 'maxspeed', 'access'}
        
        # Filter edges to keep only necessary attributes for routing, remove geometry and other metadata
        for u, v, k, data in final_G.edges(keys=True, data=True):
            # Delete unwanted attributes, keep only those necessary for routing
            unwanted = set(data) - keep_attrs
            for attr in unwanted:
                del data[attr]

        print(f"--- Saved routing brain ({len(final_G.nodes)} nodes) ---")
        with open(OUTPUT_BRAIN, 'wb') as f:
            pickle.dump(final_G, f, protocol=pickle.HIGHEST_PROTOCOL)
        
        print(f"Saved routing brain at: {OUTPUT_BRAIN}")
        print("\nSuccessfully built offline graph for HCM City!")

    except Exception as e:
        print(f"Failed to build offline graph: {str(e)}")

if __name__ == "__main__":
    main()