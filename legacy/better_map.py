import geopandas as gpd
import folium
import pandas as pd

# 1. Wczytanie sieci tras z pliku GPKG
print("Wczytuję plik .gpkg (sieć tras)...")
gdf = gpd.read_file("linie_autobusowe.gpkg")

# 2. Wczytanie danych o przystankach
mapa_dane = pd.read_csv("wspolrzedne_pelne.csv", sep=";")
mapa_dane = mapa_dane.dropna(subset=['Latitude', 'Longitude'])

# 3. Inicjalizacja mapy
# Wybieramy bardziej stonowany styl mapy, żeby szare linie były dobrze widoczne
stalowa_wola_map = folium.Map(
    location=[50.5828, 22.0533], 
    zoom_start=13, 
    tiles="CartoDB positron"
)

# 4. Dodanie sieci tras (tło)
# Rysujemy wszystkie linie w tym samym, neutralnym kolorze
print("Rysuję sieć tras...")
folium.GeoJson(
    gdf,
    style_function=lambda feature: {
        'color': '#7f8c8d',  # Szary kolor sieci
        'weight': 2.5,       # Delikatna grubość linii
        'opacity': 0.5       # Półprzezroczystość
    },
    name="Sieć autobusowa"
).add_to(stalowa_wola_map)

# 5. Nałożenie kółek z natężeniem ruchu (dane)
print("Nakładam dane o ruchu na przystankach...")
for index, row in mapa_dane.iterrows():
    # Ustawiamy promień w zależności od ruchu (min 3, żeby były widoczne)
    # Możesz dostosować dzielnik 1000, jeśli kółka są za duże
    promien = max(row['TotalFlow'] / 500, 3) 
    
    folium.CircleMarker(
        location=[row['Latitude'], row['Longitude']],
        radius=promien,
        popup=f"<b>{row['StopName']}</b><br>Ruch: {int(row['TotalFlow'])} pasażerów",
        color="crimson",
        fill=True,
        fill_color="crimson",
        fill_opacity=0.7
    ).add_to(stalowa_wola_map)

# 6. Zapisanie mapy
stalowa_wola_map.save("mapa_sieci_komunikacyjnej.html")
print("Gotowe! Wygenerowano: mapa_sieci_komunikacyjnej.html")