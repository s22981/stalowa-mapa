import pandas as pd
import folium
from folium import plugins
import re
import random

# 1. Wczytanie współrzędnych i statystyk przystanków (z TotalFlow)
mapa_dane = pd.read_csv("wspolrzedne_pelne.csv", sep=";")
mapa_dane = mapa_dane.dropna(subset=['Latitude', 'Longitude'])

# Słownik do wyszukiwania współrzędnych tras
wspolrzedne_dict = mapa_dane.set_index('StopName')[['Latitude', 'Longitude']].to_dict('index')

# 2. Inicjalizacja mapy (jasny, czytelny styl)
stalowa_wola_map = folium.Map(
    location=[50.5828, 22.0533], 
    zoom_start=13, 
    tiles="CartoDB positron"
)

# Słownik kolorów dla poszczególnych linii
kolory_linii = {}

def pobierz_kolor(linia):
    if linia not in kolory_linii:
        # Generowanie losowych, ciemniejszych kolorów, żeby ładnie kontrastowały z jasną mapą
        r = lambda: random.randint(0, 180)
        kolory_linii[linia] = '#%02X%02X%02X' % (r(), r(), r())
    return kolory_linii[linia]

print("Wczytuję plik Excel (to może potrwać kilka sekund)...")

# 3. Wczytanie pliku Excel z rozkładami
nazwa_pliku_excel = "RJ - od 01.04.2026 r..xlsx"
rozklady = pd.read_excel(nazwa_pliku_excel, sheet_name=None, header=None, skiprows=2)

print("Rysowanie animowanych tras...")

# 4. Dodawanie ANIMOWANYCH tras z pliku Excel
for nazwa_arkusza, df_rozklad in rozklady.items():
    match = re.search(r'(Linia\s+[A-Z0-9]+)', nazwa_arkusza, re.IGNORECASE)
    numer_linii = match.group(1).title() if match else "Nieznana Linia"
    
    try:
        przystanki_na_trasie = df_rozklad[0].dropna().tolist()
        przystanki_na_trasie = [str(p).strip() for p in przystanki_na_trasie if len(str(p).strip()) > 2]
        
        punkty_trasy = []
        for p in przystanki_na_trasie:
            if p in wspolrzedne_dict:
                punkty_trasy.append([wspolrzedne_dict[p]['Latitude'], wspolrzedne_dict[p]['Longitude']])
        
        if len(punkty_trasy) >= 2:
            # Używamy AntPath zamiast PolyLine dla efektu animacji
            plugins.AntPath(
                locations=punkty_trasy,
                color=pobierz_kolor(numer_linii),
                weight=4,                # Grubość linii
                opacity=0.6,             # Przezroczystość
                delay=1000,              # Prędkość animacji (im wyższa wartość, tym wolniej)
                dash_array=[15, 30],     # Rozmiar i odstępy "mrówek"
                tooltip=f"<b>{numer_linii}</b> (Arkusz: {nazwa_arkusza})"
            ).add_to(stalowa_wola_map)
            
    except Exception as e:
        print(f"Pominięto arkusz {nazwa_arkusza} ze względu na błąd: {e}")

print("Nakładanie statystyk ruchu na przystankach...")

# 5. Dodawanie kółek z natężeniem ruchu na WIERZCH mapy
for index, row in mapa_dane.iterrows():
    # Zabezpieczenie przed błędem, upewniamy się, że TotalFlow to liczba
    if pd.notna(row.get('TotalFlow')):
        promien = max(row['TotalFlow'] / 1000, 1)
        
        folium.CircleMarker(
            location=[row['Latitude'], row['Longitude']],
            radius=promien,
            popup=f"<b>{row['StopName']}</b><br>Ruch całkowity: {int(row['TotalFlow'])} pasażerów",
            color="crimson",         # Obramowanie
            fill=True,
            fill_color="crimson",    # Wypełnienie
            fill_opacity=0.75        # Nieco ciemniejsze, by wyróżniały się na tle linii
        ).add_to(stalowa_wola_map)

# Zapis ostatecznej mapy
stalowa_wola_map.save("mapa_kompleksowa_animowana.html")
print("Gotowe! Wygenerowano plik: mapa_kompleksowa_animowana.html")