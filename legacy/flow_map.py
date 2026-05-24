import pandas as pd
import numpy as np
import re
import folium
from thefuzz import process, fuzz

# Wymagane biblioteki: pip install pandas folium numpy thefuzz geopandas openpyxl

# --- USTAWIENIA NAZW PLIKÓW ---
FILE_COORDS = "wspolrzedne_pelne.csv"
FILE_BRAMKI = "Bramki Kwiecień 2026.csv"
FILE_EXCEL_RJ = "RJ - od 01.04.2026 r..xlsx" # Twój główny plik Excela

# 1. Wczytanie dokładnych współrzędnych przystanków z OSM
print("Wczytuję precyzyjne współrzędne przystanków...")
coords_df = pd.read_csv(FILE_COORDS, sep=";")
stop_coords = dict(zip(coords_df['StopName'], zip(coords_df['Latitude'], coords_df['Longitude'])))
known_stops = list(stop_coords.keys())

def znajdz_najblizszy_przystanek(raw_name):
    """Dopasowuje nazwy przystanków z rozkładów jazdy do bazy OSM"""
    raw_name = str(raw_name).strip()
    if raw_name in stop_coords:
        return raw_name
    match, score = process.extractOne(raw_name, known_stops, scorer=fuzz.token_set_ratio)
    if score > 75:
        return match
    return None

# 2. Parsowanie pliku z bramkami licznikowymi (Obciążenie "W pojeździe")
print(f"Analizuję plik {FILE_BRAMKI} (to może chwilę potrwać)...")
stop_line_loads = {}

current_stop = None
with open(FILE_BRAMKI, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        parts = line.strip().split(";")
        if not parts or len(parts) == 0:
            continue
            
        # Sprawdzamy czy to wiersz z danymi (zaczyna się od daty DD.MM.YYYY)
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
        # Sprawdzamy czy to nagłówek nowego przystanku (zawiera statystykę wejść/wyjść np. "186 / 0")
        elif len(parts) > 7 and "/" in parts[7]:
            raw_stop = parts[0].strip()
            best_stop = znajdz_najblizszy_przystanek(raw_stop)
            if best_stop:
                current_stop = best_stop

# Obliczamy średnią liczbę pasażerów w autobusie dla danej linii na danym przystanku
stop_line_avg_load = {key: np.mean(loads) for key, loads in stop_line_loads.items()}

# 3. Analiza sekwencji przystanków z pliku EXCEL (.xlsx)
print(f"Czytam zakładki z pliku {FILE_EXCEL_RJ}...")
segments = {} # (stopA, stopB) -> skumulowana liczba pasażerów ze wszystkich linii

# Wczytujemy plik Excel - sheet_name=None wczytuje wszystkie arkusze jako słownik DataFramów
try:
    xls = pd.read_excel(FILE_EXCEL_RJ, sheet_name=None, header=None)
except Exception as e:
    print(f"Błąd podczas wczytywania pliku Excel: {e}")
    print("Upewnij się, że plik nie jest aktualnie otwarty w programie Excel i masz zainstalowane 'openpyxl'.")
    exit()

# Iterujemy po każdym arkuszu (każda zakładka to inna linia/kierunek)
for sheet_name, df_sheet in xls.items():
    if df_sheet.empty:
        continue
        
    # Wyciągamy pierwszą komórkę (A1), tam zazwyczaj jest np. "LINIA 10" albo "LINIA C3"
    first_cell = str(df_sheet.iloc[0, 0])
    line_match = re.search(r'LINIA\s*([A-Z0-9]+)', first_cell, re.IGNORECASE)
    
    if line_match:
        linia_name = line_match.group(1).strip()
    else:
        # Jeśli nie znaleziono nagłówka linii, pomijamy ten arkusz
        continue
        
    stops_sequence = []
    
    # Przystanki zazwyczaj zaczynają się od wiersza 3 (indeks 2), szukamy w kolumnie A (indeks 0)
    for idx, row_val in enumerate(df_sheet.iloc[2:, 0]):
        if pd.isna(row_val):
            continue
            
        stop_raw = str(row_val).strip()
        if not stop_raw or stop_raw.startswith("-") or "kursuje" in stop_raw.lower():
            continue
            
        best_stop = znajdz_najblizszy_przystanek(stop_raw)
        
        # Jeśli znaleziono dopasowanie i nie jest to ten sam przystanek co poprzedni (omijanie duplikatów)
        if best_stop and (not stops_sequence or stops_sequence[-1] != best_stop):
            stops_sequence.append(best_stop)
            
    # Budujemy odcinki (korytarze) na podstawie sekwencji z tej zakładki
    for i in range(len(stops_sequence) - 1):
        stopA = stops_sequence[i]
        stopB = stops_sequence[i+1]
        
        # Pobieramy obciążenie na przystanku początkowym dla tej linii z pliku "Bramki"
        load = stop_line_avg_load.get((stopA, linia_name), 0)
        
        # Sortujemy klucz odcinka alfabetycznie (A->B i B->A sumuje się w jedną kreskę na mapie)
        seg_key = tuple(sorted([stopA, stopB]))
        if seg_key not in segments:
            segments[seg_key] = 0
        segments[seg_key] += load

# 4. Generowanie interaktywnej mapy potoków
print("Generuję interaktywną mapę w folium...")
stalowa_wola_map = folium.Map(location=[50.5828, 22.0533], zoom_start=13, tiles="CartoDB positron")

# Opcjonalnie: Nakładamy szary szkielet sieci z pliku GPKG (jako tło)
try:
    import geopandas as gpd
    gdf = gpd.read_file("linie_autobusowe.gpkg")
    folium.GeoJson(
        gdf,
        style_function=lambda feature: {'color': '#bdc3c7', 'weight': 1.5, 'opacity': 0.3},
        name="Szkielet dróg"
    ).add_to(stalowa_wola_map)
except Exception:
    pass # Ignorujemy błąd, jeśli nie uda się wczytać gpkg

# Rysowanie korytarzy (czerwone arterie proporcjonalne do ruchu)
max_load = max(segments.values()) if segments else 1

for (stopA, stopB), total_load in segments.items():
    if total_load < 1:  # Pomijamy mikroskopijny ruch
        continue
        
    coordA = stop_coords[stopA]
    coordB = stop_coords[stopB]
    
    # Skalowanie grubości linii (minimalnie 2px, maksymalnie 14px)
    weight = 2 + (total_load / max_load) * 12
    
    folium.PolyLine(
        locations=[coordA, coordB],
        weight=weight,
        color="#e74c3c",  
        opacity=0.8,
        tooltip=f"<b>Trasa:</b> {stopA} ↔ {stopB}<br><b>Skumulowany ruch:</b> {total_load:.1f} pasażerów w pojazdach"
    ).add_to(stalowa_wola_map)

# Nałożenie eleganckich punktów przystankowych na samą górę
for stop_name, (lat, lon) in stop_coords.items():
    if any(stop_name in seg for seg in segments.keys()):
        folium.CircleMarker(
            location=[lat, lon],
            radius=4,
            color="#2c3e50",
            weight=1.5,
            fill=True,
            fill_color="#ffffff",
            fill_opacity=1.0,
            tooltip=stop_name
        ).add_to(stalowa_wola_map)

stalowa_wola_map.save("mapa_potokow_pasazerskich.html")
print("\nSukces! Wygenerowano plik: mapa_potokow_pasazerskich.html")