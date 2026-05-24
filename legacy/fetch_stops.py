import pandas as pd
from geopy.geocoders import ArcGIS 
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

df = pd.read_csv("Statystyki_przystankow.csv", sep=";")

geolocator = ArcGIS(ssl_context=ctx)

def pobierz_wspolrzedne(stop_name):
    ulica = stop_name.split('-')[0].strip()
    query = f"{ulica}, Stalowa Wola, Polska"
    
    try:
        location = geolocator.geocode(query, timeout=10)
        if location:
            return pd.Series([location.latitude, location.longitude])
    except Exception as e:
        print(f"Błąd dla {stop_name}: {e}")
    
    return pd.Series([None, None])

print("Rozpoczynam pobieranie współrzędnych przez ArcGIS...")

df[['Latitude', 'Longitude']] = df['StopName'].apply(pobierz_wspolrzedne)

nieznalezione = df['Latitude'].isna().sum()
print(f"Zakończono. Nie udało się znaleźć współrzędnych dla {nieznalezione} przystanków.")

df.to_csv("wspolrzedne_pelne.csv", index=False, sep=";")
print("Plik wspolrzedne_pelne.csv został zapisany!")