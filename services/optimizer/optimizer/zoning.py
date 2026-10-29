"""Facility and Taluk graph zoning using QAOA Max-Cut and Coordinate K-Means."""

import logging
from typing import Any, Dict, List, Optional, Tuple
import networkx as nx
import numpy as np
from scipy.cluster.vq import kmeans2

from optimizer.qaoa.base import MaxCutResult
from optimizer.qaoa.chain import solve_maxcut_chain
from optimizer.qaoa.circuit import evaluate_cut_value

logger = logging.getLogger(__name__)


def build_facility_graph(snapshot: Dict[str, Any]) -> nx.Graph:
    """Build NetworkX graph for facilities with edge weights proportional to transit cost.
    
    Far nodes have heavier weights so Max-Cut naturally separates distant clusters into
    different zones to minimize intra-zone travel distance.
    """
    G = nx.Graph()
    facilities = snapshot.get("facilities", [])
    routes = snapshot.get("routes", [])

    for f in facilities:
        fid = f["id"]
        G.add_node(
            fid,
            name=f.get("name", fid),
            latitude=float(f.get("latitude", 12.97)),
            longitude=float(f.get("longitude", 77.59)),
            tier=f.get("tier", "PHC"),
            taluk=f.get("taluk", "Bengaluru Central"),
        )

    # Collect max transit hours to normalize weights to [0.1, 1.0]
    max_transit = 1.0
    for r in routes:
        max_transit = max(max_transit, float(r.get("transit_hours", 1.0)))

    for r in routes:
        u = r["source_facility_id"]
        v = r["destination_facility_id"]
        if u != v and u in G and v in G:
            hrs = float(r.get("transit_hours", 1.0))
            dist = float(r.get("distance_km", 20.0))
            # Normalized transit weight: higher = further apart
            norm_weight = round(hrs / max_transit, 4)
            G.add_edge(u, v, weight=norm_weight, transit_hours=hrs, distance_km=dist)

    # Ensure connected graph for zoning (connect nearest neighbors if routes are sparse)
    nodes = list(G.nodes())
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            u, v = nodes[i], nodes[j]
            if not G.has_edge(u, v):
                # Fallback Euclidean distance
                lat1, lon1 = G.nodes[u]["latitude"], G.nodes[u]["longitude"]
                lat2, lon2 = G.nodes[v]["latitude"], G.nodes[v]["longitude"]
                d = ((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5 * 111.0  # Approx km
                norm_w = min(1.0, max(0.1, round(d / 40.0, 4)))
                G.add_edge(u, v, weight=norm_w, distance_km=d, transit_hours=d / 25.0)

    return G


def build_taluk_supernode_graph(snapshot: Dict[str, Any]) -> nx.Graph:
    """Build taluk super-node graph for scale mode (40 facilities grouped into 5 taluks)."""
    G = nx.Graph()
    facilities = snapshot.get("facilities", [])
    
    # Group facilities by taluk
    taluks: Dict[str, List[Dict[str, Any]]] = {}
    for f in facilities:
        t_name = f.get("taluk") or "Central"
        if t_name not in taluks:
            taluks[t_name] = []
        taluks[t_name].append(f)

    # Add super-nodes with centroid coordinates
    for t_name, fac_list in taluks.items():
        avg_lat = sum(float(f.get("latitude", 12.97)) for f in fac_list) / len(fac_list)
        avg_lon = sum(float(f.get("longitude", 77.59)) for f in fac_list) / len(fac_list)
        G.add_node(t_name, name=t_name, latitude=avg_lat, longitude=avg_lon, facilities_count=len(fac_list))

    # Add weighted edges between taluk super-nodes based on centroid distance
    t_nodes = list(G.nodes())
    for i in range(len(t_nodes)):
        for j in range(i + 1, len(t_nodes)):
            t1, t2 = t_nodes[i], t_nodes[j]
            lat1, lon1 = G.nodes[t1]["latitude"], G.nodes[t1]["longitude"]
            lat2, lon2 = G.nodes[t2]["latitude"], G.nodes[t2]["longitude"]
            dist_km = ((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) ** 0.5 * 111.0
            norm_w = min(1.0, max(0.1, round(dist_km / 50.0, 4)))
            G.add_edge(t1, t2, weight=norm_w, distance_km=round(dist_km, 2), transit_hours=round(dist_km / 30.0, 2))

    return G


def compute_kmeans_zoning(snapshot: Dict[str, Any], k: int = 2) -> Dict[str, int]:
    """Perform coordinate-based K-Means (k=2) spatial clustering on facilities."""
    facilities = snapshot.get("facilities", [])
    if not facilities:
        return {}

    node_ids = []
    coords_list = []

    for f in facilities:
        node_ids.append(f["id"])
        lat = float(f.get("latitude", 12.97))
        lon = float(f.get("longitude", 77.59))
        coords_list.append([lat, lon])

    coords = np.array(coords_list)

    if len(node_ids) <= 2:
        return {nid: idx % k for idx, nid in enumerate(node_ids)}

    try:
        _, labels = kmeans2(coords, k, minit="points")
        return {node_ids[i]: int(labels[i]) for i in range(len(node_ids))}
    except Exception as e:
        logger.debug("kmeans2 clustering fallback: %s", e)
        # Deterministic latitude split fallback
        median_lat = float(np.median(coords[:, 0]))
        return {node_ids[i]: 0 if coords[i, 0] <= median_lat else 1 for i in range(len(node_ids))}


def compute_intra_zone_cost(graph: nx.Graph, partition: Dict[str, int]) -> float:
    """Compute total internal transit weight within the partitioned zones."""
    intra_cost = 0.0
    for u, v, data in graph.edges(data=True):
        if partition.get(u, 0) == partition.get(v, 0):
            intra_cost += float(data.get("weight", 1.0))
    return round(intra_cost, 4)


def perform_zoning(
    snapshot: Dict[str, Any],
    p: int = 1,
    shots: int = 512,
    is_scale_mode: bool = False,
) -> Dict[str, Any]:
    """Execute QAOA Max-Cut graph zoning and compare against coordinate K-Means."""
    if is_scale_mode:
        super_graph = build_taluk_supernode_graph(snapshot)
        qaoa_res = solve_maxcut_chain(super_graph, p=p, shots=shots)
        taluk_part = qaoa_res.partition

        # Map taluk supernode partition to all individual facilities
        fac_partition = {}
        for f in snapshot.get("facilities", []):
            t_name = f.get("taluk") or "Central"
            fac_partition[f["id"]] = taluk_part.get(t_name, 0)

        fac_graph = build_facility_graph(snapshot)
        qaoa_cut = evaluate_cut_value(fac_graph, fac_partition)
        qaoa_intra = compute_intra_zone_cost(fac_graph, fac_partition)
    else:
        fac_graph = build_facility_graph(snapshot)
        qaoa_res = solve_maxcut_chain(fac_graph, p=p, shots=shots)
        fac_partition = qaoa_res.partition
        qaoa_cut = qaoa_res.cut_value
        qaoa_intra = compute_intra_zone_cost(fac_graph, fac_partition)

    # Coordinate K-Means (k=2) baseline
    kmeans_partition = compute_kmeans_zoning(snapshot, k=2)
    kmeans_cut = evaluate_cut_value(fac_graph, kmeans_partition)
    kmeans_intra = compute_intra_zone_cost(fac_graph, kmeans_partition)

    return {
        "qaoa": {
            "tier": qaoa_res.tier,
            "cut_value": qaoa_cut,
            "intra_zone_cost": qaoa_intra,
            "approximation_ratio": qaoa_res.approximation_ratio,
            "partition": fac_partition,
            "time_ms": qaoa_res.time_ms,
            "evidence_file": qaoa_res.evidence_file,
        },
        "kmeans": {
            "method": "coordinate_kmeans_k2",
            "cut_value": kmeans_cut,
            "intra_zone_cost": kmeans_intra,
            "partition": kmeans_partition,
        },
        "comparison": {
            "qaoa_cut_advantage": round(qaoa_cut - kmeans_cut, 4),
            "qaoa_intra_cost_reduction": round(kmeans_intra - qaoa_intra, 4),
            "summary": "QAOA Max-Cut optimizes topology & transit barriers over Euclidean line-of-sight.",
        },
        "partition": fac_partition,
    }

