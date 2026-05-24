# Passenger flow map generator in Stalowa Wola public transit system

Made for Spaceshield Hack 2026

## Usage

`fetch_exact_stops.py`
Use to Fetch all the Bus Stops in the city, and check them against names used in public data sheet.

`flow_map_real.py`
Use to fetch the routes and generate the map with the stops, and flow on routes between them.

# City change predition
`no_change.py` - aktualny stan tkanki miejskiej na podstawie warst w QGIS
`city_changer.py` - predykcja na podstawie modelu programowania liniowego, dane wejścowe - warstwy QGIS
