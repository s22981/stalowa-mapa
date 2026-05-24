import pandas as pd
import numpy as np
import re
import folium
from thefuzz import process, fuzz
import osmnx as ox
import networkx as nx
import warnings

warnings.filterwarnings("ignore")

FILE_COORDS = "wspolrzedne_pelne.csv"
FILE_BRAMKI = "Bramki Kwiecień 2026.csv"
FILE_EXCEL_RJ = "RJ - od 01.04.2026 r..xlsx"
CENTER_POINT = (50.5828, 22.0533)
DIST_METERS = 18000 # 18 km

# 1 - OG 2 - Symulacja ze zwiększonym ruchem
SIMULATION = 2

SEGMENT_OVERRIDES = {
    tuple(sorted(["SOLIDARNOŚCI - PKP", "OFIAR KATYNIA - SUPER MARKET"])): 260,
    tuple(sorted(["OFIAR KATYNIA - CMENTARZ", "OKULICKIEGO - WIADUKT"])): 260,
}

print("1. Wczytuję precyzyjne współrzędne przystanków...")
coords_df = pd.read_csv(FILE_COORDS, sep=";")
stop_coords = dict(zip(coords_df['StopName'], zip(coords_df['Latitude'], coords_df['Longitude'])))
known_stops = list(stop_coords.keys())

def znajdz_najblizszy_przystanek(raw_name):
    raw_name = str(raw_name).strip()
    if raw_name in stop_coords:
        return raw_name
    match, score = process.extractOne(raw_name, known_stops, scorer=fuzz.token_set_ratio)
    if score > 75:
        return match
    return None

print(f"2. Analizuję plik {FILE_BRAMKI}...")
stop_line_loads = {}
current_stop = None
with open(FILE_BRAMKI, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        parts = line.strip().split(";")
        if not parts or len(parts) == 0:
            continue
        if re.match(r'^\s*\d{2}\.\d{2}\.\d{4}', parts[0]):
            if current_stop and len(parts) > 7:
                linia = parts[3].strip()
                w_pojezdzie_raw = parts[7].strip()
                try:
                    w_pojezdzie = int(w_pojezdzie_raw)
                    key = (current_stop, linia)
                    if key not in stop_line_loads:
                        stop_line_loads[key] = []
                    stop_line_loads[key].append(w_pojezdzie)
                except ValueError:
                    pass
        elif len(parts) > 7 and "/" in parts[7]:
            best_stop = znajdz_najblizszy_przystanek(parts[0].strip())
            if best_stop:
                current_stop = best_stop

stop_line_avg_load = {key: np.mean(loads) for key, loads in stop_line_loads.items()}

print(f"3. Czytam zakładki z pliku {FILE_EXCEL_RJ}...")
segments = {}
try:
    xls = pd.read_excel(FILE_EXCEL_RJ, sheet_name=None, header=None)
except Exception as e:
    print(f"Błąd Excela: {e}")
    exit()

for sheet_name, df_sheet in xls.items():
    if df_sheet.empty: continue
    first_cell = str(df_sheet.iloc[0, 0])
    line_match = re.search(r'LINIA\s*([A-Z0-9]+)', first_cell, re.IGNORECASE)
    if not line_match: continue
    linia_name = line_match.group(1).strip()
        
    stops_sequence = []
    for row_val in df_sheet.iloc[2:, 0]:
        if pd.isna(row_val): continue
        stop_raw = str(row_val).strip()
        if not stop_raw or stop_raw.startswith("-") or "kursuje" in stop_raw.lower(): continue
        best_stop = znajdz_najblizszy_przystanek(stop_raw)
        if best_stop and (not stops_sequence or stops_sequence[-1] != best_stop):
            stops_sequence.append(best_stop)
            
    for i in range(len(stops_sequence) - 1):
        stopA, stopB = stops_sequence[i], stops_sequence[i+1]
        load = stop_line_avg_load.get((stopA, linia_name), 0)
        seg_key = tuple(sorted([stopA, stopB]))
        if seg_key not in segments: segments[seg_key] = 0
        segments[seg_key] += load

if SIMULATION == 2:
    print("Stosuję nadpisania dla symulacji 2...")
    for seg_key, extra_load in SEGMENT_OVERRIDES.items():
        segments[seg_key] = segments.get(seg_key, 0) + extra_load

OUTPUT_FILE = "mapa_potokow_rzeczywista.html" if SIMULATION == 1 else f"mapa_potokow_symulacja{SIMULATION}.html"

print("\n4. Pobieram układ ulic do wytyczenia rzeczywistych tras autobusów...")

G = ox.graph_from_point(CENTER_POINT, dist=DIST_METERS, network_type='drive')

print("Generuję interaktywną mapę w folium...")
stalowa_wola_map = folium.Map(location=[50.5828, 22.0533], zoom_start=13, tiles="CartoDB positron")

max_load = max(segments.values()) if segments else 1

print("Wytyczam przebiegi odcinków po ulicach...")
for (stopA, stopB), total_load in segments.items():
    if total_load < 1: continue
        
    coordA, coordB = stop_coords[stopA], stop_coords[stopB]
    weight = 2 + (total_load / max_load) * 12
    
    node_a = ox.distance.nearest_nodes(G, X=coordA[1], Y=coordA[0])
    node_b = ox.distance.nearest_nodes(G, X=coordB[1], Y=coordB[0])
    
    try:
        route = nx.shortest_path(G, node_a, node_b, weight='length')
       
        route_coords = []
        for u, v in zip(route[:-1], route[1:]):
            edge_data = G.get_edge_data(u, v)[0]
            if 'geometry' in edge_data:
                xs, ys = edge_data['geometry'].xy
                route_coords.extend(zip(ys, xs))
            else:
                route_coords.append((G.nodes[u]['y'], G.nodes[u]['x']))
        
        route_coords.append((G.nodes[route[-1]]['y'], G.nodes[route[-1]]['x']))
        
        folium.PolyLine(
            locations=route_coords,
            weight=weight + 3,
            color="#2c3e50",
            opacity=0.6,
        ).add_to(stalowa_wola_map)
        folium.PolyLine(
            locations=route_coords,
            weight=weight,
            color="#e74c3c",  
            opacity=0.8,
            tooltip=f"<b>Trasa:</b> {stopA} ↔ {stopB}<br><b>Skumulowany ruch:</b> {total_load:.1f} pasażerów"
        ).add_to(stalowa_wola_map)
        
    except nx.NetworkXNoPath:
        folium.PolyLine(
            locations=[coordA, coordB],
            weight=weight + 3,
            color="#2c3e50", opacity=0.6, dash_array="5, 5",
        ).add_to(stalowa_wola_map)
        folium.PolyLine(
            locations=[coordA, coordB],
            weight=weight,
            color="#e74c3c", opacity=0.8, dash_array="5, 5",
            tooltip=f"{stopA} ↔ {stopB} (linia prosta - brak drogi)"
        ).add_to(stalowa_wola_map)

print("Nakładam przystanki...")
for stop_name, (lat, lon) in stop_coords.items():
    if any(stop_name in seg for seg in segments.keys()):
        folium.CircleMarker(
            location=[lat, lon],
            radius=4,
            color="#2c3e50", weight=1.5, fill=True, fill_color="#ffffff", fill_opacity=1.0,
            tooltip=stop_name
        ).add_to(stalowa_wola_map)

stalowa_wola_map.save(OUTPUT_FILE)
print(f"\nSukces! Wygenerowano plik: {OUTPUT_FILE}")