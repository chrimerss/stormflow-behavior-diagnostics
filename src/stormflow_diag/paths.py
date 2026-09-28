"""Filesystem locations. Override the data root with STORMFLOW_DATA."""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("STORMFLOW_DATA", REPO / "data"))
FIGSHARE = DATA / "figshare"
ZENODO_2024 = DATA / "zenodo_14253670"
UPSTREAM = REPO / "upstream"
RESULTS = REPO / "results"

GAUGED_ATTRS = FIGSHARE / "Gauged_Catchments_Metadata_and_Attributes.csv"
GAUGED_PHENOLOGY = FIGSHARE / "Gauged_Catchments_Growing_Dormancy_Probability.csv"
UNGAUGED_PHENOLOGY = FIGSHARE / "Ungauged_Catchments_Growing_Dormancy_Probability.csv"
GAUGED_BOUNDARIES = FIGSHARE / "Gauged_Catchments_Boundaries.gpkg"
UNGAUGED_BOUNDARIES = FIGSHARE / "63434619_Ungauged_Catchments_Boundaries.gpkg"
EVENT_INPUTS_ZIP = FIGSHARE / "Event_Inputs.zip"
EVENTS = {
    "dormant": FIGSHARE / "Identified_Rainfall_Runoff_Events_Dormant.csv",
    "growing": FIGSHARE / "Identified_Rainfall_Runoff_Events_Growing.csv",
}
