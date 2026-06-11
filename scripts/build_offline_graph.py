import os
import gc
import pickle
from collections import defaultdict

import geopandas as gpd
import osmium
import osmnx as ox
from shapely.geometry import LineString

PBF_INPUT = "./data/hcmc_routing_clean.osm.pbf"
OUTPUT_BRAIN = "./data/hcmc_routing_brain_v1.pkl"
OUTPUT_GEOMETRY = "./data/hcmc_geometry_store.feather"


def _is_driving_highway(highway):
    allowed = {
        "motorway",
        "trunk",
        "primary",
        "secondary",
        "tertiary",
        "unclassified",
        "residential",
        "service",
        "living_street",
        "motorway_link",
        "trunk_link",
        "primary_link",
        "secondary_link",
        "tertiary_link",
    }
    return highway in allowed


def _is_oneway(tags, highway):
    oneway = (tags.get("oneway") or "").lower()
    if oneway in {"yes", "true", "1"}:
        return True
    if oneway in {"no", "false", "0"}:
        return False
    return highway in {"motorway", "motorway_link"}


class OSMNetworkHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.nodes = {}
        self.ways = []

    def node(self, n):
        if not n.location.valid():
            return
        self.nodes[n.id] = (n.location.lon, n.location.lat)

    def way(self, w):
        highway = w.tags.get("highway")
        if not highway or not _is_driving_highway(highway):
            return
        node_ids = [n.ref for n in w.nodes]
        if len(node_ids) < 2:
            return
        self.ways.append({"id": w.id, "node_ids": node_ids, "tags": dict(w.tags)})


def main():
    if not os.path.exists(PBF_INPUT):
        print(f"Error: File not found {PBF_INPUT}. Please run osmium filter first!")
        return

    try:
        print("Loading OSM data and building graph...")
        handler = OSMNetworkHandler()
        handler.apply_file(PBF_INPUT, locations=True)

        node_rows = []
        for node_id, (lon, lat) in handler.nodes.items():
            node_rows.append({"osmid": node_id, "x": lon, "y": lat})

        nodes_gdf = gpd.GeoDataFrame(
            node_rows,
            geometry=gpd.points_from_xy(
                [row["x"] for row in node_rows],
                [row["y"] for row in node_rows],
            ),
            crs="EPSG:4326",
        ).set_index("osmid")

        edge_rows = []
        key_counter = defaultdict(int)

        for way in handler.ways:
            tags = way["tags"]
            highway = tags.get("highway")
            oneway = _is_oneway(tags, highway)
            for u, v in zip(way["node_ids"][:-1], way["node_ids"][1:]):
                if u not in handler.nodes or v not in handler.nodes:
                    continue
                u_lon, u_lat = handler.nodes[u]
                v_lon, v_lat = handler.nodes[v]
                length = ox.distance.great_circle(u_lat, u_lon, v_lat, v_lon)
                geometry = LineString([(u_lon, u_lat), (v_lon, v_lat)])

                key = key_counter[(u, v)]
                key_counter[(u, v)] += 1
                edge_rows.append(
                    {
                        "u": u,
                        "v": v,
                        "key": key,
                        "osmid": way["id"],
                        "length": length,
                        "oneway": oneway,
                        "highway": highway,
                        "name": tags.get("name"),
                        "maxspeed": tags.get("maxspeed"),
                        "access": tags.get("access"),
                        "geometry": geometry,
                    }
                )

                if not oneway:
                    key = key_counter[(v, u)]
                    key_counter[(v, u)] += 1
                    edge_rows.append(
                        {
                            "u": v,
                            "v": u,
                            "key": key,
                            "osmid": way["id"],
                            "length": length,
                            "oneway": oneway,
                            "highway": highway,
                            "name": tags.get("name"),
                            "maxspeed": tags.get("maxspeed"),
                            "access": tags.get("access"),
                            "geometry": geometry,
                        }
                    )

        edges_gdf = gpd.GeoDataFrame(edge_rows, geometry="geometry", crs="EPSG:4326")
        edges_gdf = edges_gdf.set_index(["u", "v", "key"])
        final_G = ox.graph_from_gdfs(nodes_gdf, edges_gdf, graph_attrs={"crs": "EPSG:4326"})
        
        print(f"Origin graph has {len(final_G.nodes)} nodes and {len(final_G.edges)} edges.")
        final_G = ox.truncate.largest_component(final_G, strongly=False)
        print(f"Final graph has {len(final_G.nodes)} nodes and {len(final_G.edges)} edges after keeping largest component.")
        # Project graph to UTM zone for accurate distance calculations (important for routing)
        final_G = ox.projection.project_graph(final_G)  
        
        del handler, node_rows, edge_rows, nodes_gdf, edges_gdf
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