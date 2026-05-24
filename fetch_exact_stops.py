import osmnx as ox
import pandas as pd
from thefuzz import process, fuzz
import re
import warnings

warnings.filterwarnings("ignore")


CENTER_POINT = (50.5828, 22.0533)
DIST_METERS = 18000 # 18 km

INPUT_FILE = "Statystyki_przystankow.csv" 
OUTPUT_FILE = "wspolrzedne_pelne.csv"

print(f"Pobieram przystanki w promieniu {DIST_METERS/1000} km od centrum...")
tags = {'public_transport': 'platform', 'highway': 'bus_stop'}
stops = ox.features_from_point(CENTER_POINT, tags=tags, dist=DIST_METERS)

stops['geometry'] = stops.geometry.centroid

stops['Latitude'] = stops.geometry.representative_point().y
stops['Longitude'] = stops.geometry.representative_point().x

stops_osm = stops[['name', 'Latitude', 'Longitude']].dropna(subset=['name'])
osm_names = stops_osm['name'].tolist()
print(f"Sukces! Pobrano {len(stops_osm)} punktów przystankowych z bazy OSM.\n")

df_input = pd.read_csv(INPUT_FILE, sep=";")
output_data = []

def czysc_nazwe(nazwa):
    czysta = re.sub(r'-\d+$', '', nazwa)
    czysta = czysta.replace('-', ' ')
    return czysta.strip()

print("Rozpoczynam inteligentne dopasowywanie (offline)...")

for index, row in df_input.iterrows():
    stop_name = row['StopName']
    clean_name = czysc_nazwe(stop_name)
    
    match, score = process.extractOne(clean_name, osm_names, scorer=fuzz.token_set_ratio)
    
    if score > 70:
        coord = stops_osm[stops_osm['name'] == match].iloc[0]
        output_data.append({
            'StopName': stop_name,
            'Boarded': row['Boarded'],
            'Alighted': row['Alighted'],
            'TotalFlow': row['TotalFlow'],
            'Latitude': coord['Latitude'],
            'Longitude': coord['Longitude']
        })
    else:
        print(f"Brak pewnego dopasowania dla: '{stop_name}' (najlepsze co znalazłem to '{match}' na {score}%)")

df_results = pd.DataFrame(output_data)
df_results.to_csv(OUTPUT_FILE, index=False, sep=";")

print(f"\nGotowe! Dopasowano {len(df_results)} z {len(df_input)} przystanków.")
print(f"Plik zapisany jako: {OUTPUT_FILE}")