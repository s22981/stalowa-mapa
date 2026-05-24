import os
import warnings
warnings.filterwarnings('ignore')

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# =====================================================================
# 1. KONFIGURACJA I WCZYTYWANIE
# =====================================================================
SHP_DIR = r"C:\Users\karol\Downloads\1818_SHP"
centrum_sw = Point(716212.0, 304725.0)
ZASIEG_MIASTA_METRY = 4500
strefa_miasta = centrum_sw.buffer(ZASIEG_MIASTA_METRY)

def znajdz_plik_bdot(folder, przyrostek):
    for plik in os.listdir(folder):
        if plik.endswith(f"{przyrostek}.shp"):
            return os.path.join(folder, plik)
    return None

# Wczytywanie danych
gdf_budynki_all = gpd.read_file(znajdz_plik_bdot(SHP_DIR, "OT_BUBD_A")).to_crs(epsg=2180).clip(strefa_miasta)

# Wczytywanie gruntów (PTGN, PTNZ, PTTR)
frames = []
for kat in ["OT_PTGN_A", "OT_PTNZ_A", "OT_PTTR_A"]:
    path = znajdz_plik_bdot(SHP_DIR, kat)
    if path:
        frames.append(gpd.read_file(path).to_crs(epsg=2180).clip(strefa_miasta))
gdf_grunty_nieuzyt = pd.concat(frames, ignore_index=True) if frames else gpd.GeoDataFrame()

# =====================================================================
# 2. FILTROWANIE (ROZSZERZONE O USŁUGI)
# =====================================================================
def filtruj_warstwe(gdf, kody_std, slowa_kluczowe):
    if gdf.empty: return gdf
    mask = pd.Series(False, index=gdf.index)
    for col in gdf.columns:
        if col != 'geometry' and gdf[col].dtype == 'object':
            clean = gdf[col].astype(str).str.strip()
            mask |= clean.str.upper().isin([str(k).upper() for k in kody_std])
            for slowo in slowa_kluczowe:
                mask |= clean.str.contains(slowo, case=False, na=False)
    return gdf[mask].copy()

przemysl_budynki = filtruj_warstwe(gdf_budynki_all, ['BUBD11', '1251', '1252'], ['przemyslowy', 'magazyn'])
szkoly_budynki    = filtruj_warstwe(gdf_budynki_all, ['BUBD15', '1263'], ['szkoła', 'przedszkole'])
uslugi_budynki    = filtruj_warstwe(gdf_budynki_all,
    ['BUBD07', 'BUBD08', 'BUBD09', 'BUBD12', 'BUBD13', 'BUBD17', 'BUBD21'],
    ['biurowy', 'biuro', 'handlowy', 'usługowy', 'uslugowy', 'administracyjny', 'kulturalny'])

# =====================================================================
# 3. WIZUALIZACJA
# =====================================================================
fig, ax = plt.subplots(figsize=(18, 14))
fig.patch.set_facecolor('#FFFFFF')
ax.set_facecolor('#F9FBFD')

# Rysowanie tła
gdf_budynki_all.plot(ax=ax, color='#C6C6C6', edgecolor='#B5B5B5', linewidth=0.2, zorder=1)
if not gdf_grunty_nieuzyt.empty:
    gdf_grunty_nieuzyt.plot(ax=ax, color='#F5EBE6', edgecolor='#BCAAA4', linewidth=0.3, alpha=0.9, zorder=2)

# Wyróżnienia (zorder > 2)
przemysl_budynki.plot(ax=ax, color='#CFD8DC', edgecolor='#90A4AE', linewidth=0.4, zorder=3)
szkoly_budynki.plot(ax=ax, color='#FFF59D', edgecolor='#FBC02D', linewidth=0.4, zorder=3)
uslugi_budynki.plot(ax=ax, color='#B39DDB', edgecolor='#7E57C2', linewidth=0.4, zorder=3) # Kolor fioletowy dla usług

# Legenda
legenda = [
    mpatches.Patch(facecolor='#C6C6C6', edgecolor='#B5B5B5', label='Istniejąca zabudowa tła'),
    mpatches.Patch(facecolor='#CFD8DC', edgecolor='#90A4AE', label='Strefy przemysłowo-magazynowe'),
    mpatches.Patch(facecolor='#FFF59D', edgecolor='#FBC02D', label='Obiekty oświatowe / szkoły'),
    mpatches.Patch(facecolor='#B39DDB', edgecolor='#7E57C2', label='Budynki usługowe / handlowe / biura'),
    mpatches.Patch(facecolor='#F5EBE6', edgecolor='#BCAAA4', label='Nieużytki i wolne tereny')
]

ax.legend(handles=legenda, loc='upper left', bbox_to_anchor=(1.02, 1), fontsize=10, frameon=True)

# Ustawienia widoku
ax.set_xlim(centrum_sw.x - ZASIEG_MIASTA_METRY, centrum_sw.x + ZASIEG_MIASTA_METRY)
ax.set_ylim(centrum_sw.y - ZASIEG_MIASTA_METRY, centrum_sw.y + ZASIEG_MIASTA_METRY)
plt.title("Stan pierwotny obszaru — Stalowa Wola (BDOT10k)", fontsize=14, fontweight='bold', pad=12)
plt.grid(True, linestyle=':', alpha=0.5, color='#757575')

plt.tight_layout()
plt.show()