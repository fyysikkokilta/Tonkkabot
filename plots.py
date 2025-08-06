"""
Plotting module for Tonkkabot.

This module handles creating temperature plots for historical data and forecasts
using matplotlib and seaborn for visualization.
"""

import io
from typing import BinaryIO

from cachetools import cached, TTLCache
from matplotlib import pyplot as plt
from matplotlib.dates import DateFormatter
from pytz import timezone
import seaborn as sns

import data

sns.set_theme(style="whitegrid")

cache_history = TTLCache(maxsize=100, ttl=60)
cache_forecast = TTLCache(maxsize=100, ttl=60)


def temperature_plot(df, title: str) -> BinaryIO:
    """Create a temperature plot with the given data and title.

    Args:
        df: DataFrame containing temperature data
        title: Title for the plot

    Returns:
        BinaryIO: BytesIO object containing the plot image
    """
    # Set style for better looking plots
    plt.style.use("seaborn-v0_8")

    fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
    ax.plot(
        df["time"], df["temp"], color="red", linewidth=2, label="Helsinki-Vantaa, EFHK"
    )
    ax.axhline(20, ls="--", color="black", linewidth=1.5, label="Pääpäivä (20°C)")
    ax.set(xlabel="Aika", ylabel="Lämpötila " + "\N{DEGREE SIGN}" + "C", title=title)
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Format x-axis dates
    date_form = DateFormatter("%H:%M \n %d.%m.", tz=timezone("Europe/Helsinki"))
    ax.xaxis.set_major_formatter(date_form)

    # Rotate x-axis labels for better readability
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    bio = io.BytesIO()
    bio.name = f"{title}.png"
    fig.savefig(bio, format="png", bbox_inches="tight", dpi=300)
    plt.close(fig)
    return bio


@cached(cache_history)
def history(hours: int = 24) -> BinaryIO:
    """Create a temperature history plot for the specified number of hours.

    Args:
        hours: Number of hours to plot (default: 24)

    Returns:
        BinaryIO: BytesIO object containing the plot image
    """
    df = data.fetch_data(hourdelta=hours + 2)
    if df.empty:
        # Return a placeholder plot with error message
        fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
        ax.text(
            0.5,
            0.5,
            "Ei tietoja saatavilla",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=16,
        )
        ax.set_title(f"Edellinen {hours}h")
        bio = io.BytesIO()
        bio.name = f"history_{hours}h.png"
        fig.savefig(bio, format="png", bbox_inches="tight", dpi=300)
        plt.close(fig)
        return bio
    return temperature_plot(df, f"Edellinen {hours}h")


@cached(cache_forecast)
def forecast(hours: int = 48) -> BinaryIO:
    """Create a temperature forecast plot for the specified number of hours.

    Args:
        hours: Number of hours to plot (default: 48)

    Returns:
        BinaryIO: BytesIO object containing the plot image
    """
    df = data.fetch_data()
    if df.empty:
        # Return a placeholder plot with error message
        fig, ax = plt.subplots(figsize=(8, 5), dpi=300)
        ax.text(
            0.5,
            0.5,
            "Ei tietoja saatavilla",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=16,
        )
        ax.set_title(f"{hours}h Ennuste")
        bio = io.BytesIO()
        bio.name = f"forecast_{hours}h.png"
        fig.savefig(bio, format="png", bbox_inches="tight", dpi=300)
        plt.close(fig)
        return bio

    df = df.iloc[0 : hours + 1, :]
    return temperature_plot(df, f"{hours}h Ennuste")
