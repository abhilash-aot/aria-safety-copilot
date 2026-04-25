"""Golden join helper for Track 2 — Food Security Delivery Operations.

Lifted from cell 5 of tracks/food-security-delivery/notebooks/00_quickstart.ipynb.
Join semantics are preserved exactly: left joins from route_stops outward through
delivery_requests, clients, routes, drivers, and a grouped item count.
"""

from __future__ import annotations

import pandas as pd


def build_stops_enriched(tables: dict) -> pd.DataFrame:
    """Build the stops_enriched DataFrame from the 9-table dict returned by load_track2.

    Reproduces the golden join from notebook cell 5 verbatim. Uses the loader's
    key names (stops, requests, clients, routes, drivers, request_items) which map
    1-to-1 to the notebook's variable names.

    Args:
        tables: dict[str, pd.DataFrame] as returned by shared.src.loaders.load_track2.

    Returns:
        stops_enriched DataFrame with stop-level rows and enriched columns from
        all joined tables plus items_delivered_count.
    """
    stops = tables["stops"]
    requests = tables["requests"]
    clients = tables["clients"]
    routes = tables["routes"]
    drivers = tables["drivers"]
    request_items = tables["request_items"]

    items_per_request = (
        request_items.groupby("request_id")["quantity"].sum().rename("items_delivered_count")
    )

    stops_enriched = (
        stops
        .merge(requests, on="request_id", how="left", suffixes=("", "_req"))
        .merge(clients, on="client_id", how="left", suffixes=("", "_client"))
        .merge(routes, on="route_id", how="left", suffixes=("", "_route"))
        .merge(drivers, on="driver_id", how="left", suffixes=("", "_driver"))
        .merge(items_per_request, on="request_id", how="left")
    )

    return stops_enriched
