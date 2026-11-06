"""地铁通（metroman.cn）查询工具包。

典型用法::

    from metroman import MetroMan

    mm = MetroMan()
    city = mm.city("北京")
    stations = mm.stations(city.key)
    routes = mm.plan(city.key, "tian-anmenxi", "3-hao-hangzhanlou-terminal-3")
"""

from .api import MetroMan
from .client import MetroManClient, MetroManError, NotFoundError
from .models import (
    City,
    Line,
    Route,
    RouteLeg,
    RouteStop,
    Station,
    StationInfo,
    TimetableEntry,
)

__version__ = "1.0.0"

__all__ = [
    "MetroMan",
    "MetroManClient",
    "MetroManError",
    "NotFoundError",
    "City",
    "Line",
    "Route",
    "RouteLeg",
    "RouteStop",
    "Station",
    "StationInfo",
    "TimetableEntry",
    "__version__",
]
