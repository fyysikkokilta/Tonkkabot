"""
Data processing module for Tonkkabot.

This module handles fetching and processing weather data from the Finnish
Meteorological Institute (FMI) API, including temperature history and forecasts.
"""

import datetime as dt
import json
import re
import xml.etree.ElementTree as ET
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import requests
from cachetools import cached, TTLCache
from pytz import timezone

cache = TTLCache(maxsize=100, ttl=60)

HISTORY_FILENAME = "history.json"


def check_history() -> None:
    """Check and load the history of tönkkä occurrences from JSON file."""
    try:
        with open(HISTORY_FILENAME, "r", encoding="utf-8") as json_file:
            history = json.load(json_file)
            if str(dt.datetime.now().year) in history:
                return history[str(dt.datetime.now().year)]
            return False
    except FileNotFoundError:
        # Create history file if it doesn't exist
        with open(HISTORY_FILENAME, "w", encoding="utf-8") as json_file:
            json.dump({}, json_file)
        return False


def check_tonkka_occurrence() -> Optional[dict]:
    """Check if tönkkä has occurred this year.

    Returns:
        dict or None: Tönkkä occurrence data if it happened, None otherwise
    """
    return check_history()


def get_param_names(url: str) -> dict:
    """Get parameters metadata from FMI API.

    Args:
        url: URL to fetch parameter metadata from

    Returns:
        dict: Dictionary mapping parameter IDs to names
    """
    req = requests.get(url, timeout=30)
    params = {}

    if req.status_code == 200:
        xmlstring = req.content
        tree = ET.ElementTree(ET.fromstring(xmlstring))
        for p in tree.iter(
            tag="{http://inspire.ec.europa.eu/schemas/omop/2.9}ObservableProperty"
        ):
            params[p.get("{http://www.opengis.net/gml/3.2}id")] = p.find(
                "{http://inspire.ec.europa.eu/schemas/omop/2.9}label"
            ).text
    return params


def get_params(tree: ET.ElementTree) -> list:
    """Get parameters from response XML tree.

    Args:
        tree: XML tree to parse

    Returns:
        list: List of parameter names with IDs
    """
    ret_params = []
    for el in tree.iter(tag="{http://www.opengis.net/om/2.0}observedProperty"):
        url = el.get("{http://www.w3.org/1999/xlink}href")
        params = re.findall(r"(?<=param=).*,.*(?=&)", url)[0].split(",")

        param_names = get_param_names(url)
        for p in params:
            ret_params.append(f"{param_names[p]} ({p})")

    return ret_params


def get_positions(tree: ET.ElementTree) -> np.ndarray:
    """Get times and coordinates from multipointcoverage answer.

    Args:
        tree: XML tree to parse

    Returns:
        np.ndarray: Array of positions with lat, lon, timestamp
    """
    positions = []
    for el in tree.iter(tag="{http://www.opengis.net/gmlcov/1.0}positions"):
        pos = el.text.split()
        while len(pos) > 0:
            lat = float(pos.pop(0))
            lon = float(pos.pop(0))
            timestamp = int(pos.pop(0))
            positions.append([lat, lon, timestamp])
    return np.array(positions)


def record_possible_tonkka(df: pd.DataFrame, threshold: float = 20.0) -> None:
    """Record tönkkä occurrence if temperature reaches threshold.

    Args:
        df: DataFrame with temperature data
        threshold: Temperature threshold for tönkkä (default: 20.0)
    """
    tonks = df.loc[df["temp"] >= threshold, :].reset_index(drop=True)
    if len(tonks) == 0:
        return
    record_happened = tonks.loc[0, "time"] < dt.datetime.now(
        tz=timezone("Europe/Helsinki")
    )
    if record_happened & (check_history() is False):
        with open(HISTORY_FILENAME, "r+", encoding="utf-8") as json_file:
            history = json.load(json_file)
            history[str(dt.datetime.now().year)] = {
                "temperature": tonks.loc[0, "temp"],
                "time": str(tonks.loc[0, "time"]),
            }
            json_file.seek(0)
            json.dump(history, json_file)
        check_history()


@cached(cache)
def fetch_data(hourdelta: Optional[int] = None) -> pd.DataFrame:
    """Fetch weather data from FMI data API.

    Provides forecast data if hourdelta is None and
    history data if hourdelta is specified.

    Args:
        hourdelta: amount of hours of history (default: None)

    Returns:
        pandas.DataFrame: DataFrame with temperature data
    """
    try:
        if hourdelta:
            start = dt.datetime.now(tz=timezone("Europe/Helsinki")) - dt.timedelta(
                hours=hourdelta
            )
            start_str = start.strftime("%Y-%m-%dT%H:%M:00Z")
            payload = {
                "request": "getFeature",
                "storedquery_id": "fmi::observations::weather::multipointcoverage",
                "starttime": start_str,
                "place": "vantaa",
                "timestep": "10",
                "parameters": "t2m",
            }
        else:
            payload = {
                "request": "getFeature",
                "storedquery_id": "fmi::forecast::harmonie::surface::point::multipointcoverage",
                "place": "vantaa",
                "parameters": "temperature",
            }

        r = requests.get("http://opendata.fmi.fi/wfs", params=payload, timeout=30)
        r.raise_for_status()

        # Construct XML tree
        tree = ET.ElementTree(ET.fromstring(r.content))

        # Get geospatial and temporal positions of data elements
        positions = get_positions(tree)

        # Extract data from XML tree
        d = []
        for el in tree.iter(
            tag="{http://www.opengis.net/gml/3.2}doubleOrNilReasonTupleList"
        ):
            for pos in el.text.strip().split("\n"):
                d.append(pos.strip().split(" "))

        # Assign data values to positions
        data_array = np.append(positions, np.array(d), axis=1)

        df = pd.DataFrame(data_array, columns=["lon", "lat", "time", "temp"])
        df["temp"] = df["temp"].astype(float)
        df["time"] = pd.to_datetime(
            df["time"], unit="s", origin="unix", utc=True
        ).dt.tz_convert("Europe/Helsinki")

        record_possible_tonkka(df, 20.0)
        return df

    except requests.RequestException as e:
        print(f"Error fetching data from FMI API: {e}")
        # Return empty DataFrame with correct structure
        return pd.DataFrame(columns=["lon", "lat", "time", "temp"])
    except ET.ParseError as e:
        print(f"Error parsing XML response: {e}")
        return pd.DataFrame(columns=["lon", "lat", "time", "temp"])
    except (ValueError, KeyError, IndexError) as e:
        print(f"Error processing data: {e}")
        return pd.DataFrame(columns=["lon", "lat", "time", "temp"])


def temperature() -> Tuple[Optional[float], Optional[dt.datetime]]:
    """Get current temperature from the last 6 hours of data.

    Returns:
        tuple: (temperature, timestamp) or (None, None) if no data available
    """
    df = fetch_data(6)
    if df.empty:
        return None, None

    df = df.dropna(subset=["temp"])
    if df.empty:
        return None, None

    df = df.iloc[-1:, 2:]
    return df.temp.to_numpy()[0], df.time.to_numpy()[0]
