import requests
import datetime as dt
from pytz import timezone
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
import re
import json
from cachetools import cached, TTLCache

cache = TTLCache(maxsize=100, ttl=60)

history_filename = "history.json"
global tonkka_occurred


def check_history():
    global tonkka_occurred
    try:
        with open(history_filename, "r") as json_file:
            history = json.load(json_file)
            if str(dt.datetime.now().year) in history:
                tonkka_occurred = history[str(dt.datetime.now().year)]
            else:
                tonkka_occurred = False
    except FileNotFoundError:
        # Create history file if it doesn't exist
        with open(history_filename, "w") as json_file:
            json.dump({}, json_file)
        tonkka_occurred = False


check_history()


def check_tonkka_occurrence():
    return tonkka_occurred


def get_param_names(url):
    """Get parameters metadata"""
    req = requests.get(url)
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


def get_params(tree):
    """Get parameters from response xml tree"""

    retParams = []
    for el in tree.iter(tag="{http://www.opengis.net/om/2.0}observedProperty"):
        url = el.get("{http://www.w3.org/1999/xlink}href")
        params = re.findall(r"(?<=param=).*,.*(?=&)", url)[0].split(",")

        param_names = get_param_names(url)
        for p in params:
            retParams.append("{} ({})".format(param_names[p], p))

    return retParams


def get_positions(tree):
    """
    Function to get times and coordinates from multipointcoverage answer
    """
    positions = []
    for el in tree.iter(tag="{http://www.opengis.net/gmlcov/1.0}positions"):
        pos = el.text.split()
        i = 0
        while len(pos) > 0:
            lat = float(pos.pop(0))
            lon = float(pos.pop(0))
            timestamp = int(pos.pop(0))
            positions.append([lat, lon, timestamp])
    return np.array(positions)


def record_possible_tonkka(df, threshold=20.0):
    tonks = df.loc[df["temp"] >= threshold, :].reset_index(drop=True)
    if len(tonks) == 0:
        return
    record_happened = tonks.loc[0, "time"] < dt.datetime.now(
        tz=timezone("Europe/Helsinki")
    )
    if record_happened & (tonkka_occurred is False):
        with open(history_filename, "r+") as json_file:
            history = json.load(json_file)
            history[str(dt.datetime.now().year)] = {
                "temperature": tonks.loc[0, "temp"],
                "time": str(tonks.loc[0, "time"]),
            }
            json_file.seek(0)
            json.dump(history, json_file)
        check_history()
    else:
        return


@cached(cache)
def fetch_data(hourdelta=None):
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
    except Exception as e:
        print(f"Unexpected error in fetch_data: {e}")
        return pd.DataFrame(columns=["lon", "lat", "time", "temp"])


def temperature():
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
