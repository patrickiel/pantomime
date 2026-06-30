"""Actuation: one content-agnostic driver operating on a screen rectangle."""

from pantomime.driver.base import Driver, OutOfRegionError
from pantomime.driver.region import RegionDriver
from pantomime.driver.region_select import (
    RegionError,
    find_window_region,
    foreground_window_region,
    resolve_region,
    select_region,
    whole_screen,
)

__all__ = [
    "Driver",
    "OutOfRegionError",
    "RegionDriver",
    "RegionError",
    "find_window_region",
    "foreground_window_region",
    "resolve_region",
    "select_region",
    "whole_screen",
]
