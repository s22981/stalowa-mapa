import os
import warnings
warnings.filterwarnings('ignore')

import geopandas as gpd
import pandas as pd
import pulp
from shapely.geometry import Point

# =====================================================================
# 1. KONFIGURACJA I POPRAWNE CENTRUM MIASTA (ZGODNE Z GOOGLE MAPS)
# =====================================================================
SHP_DIR = r"C:\Users\karol\Downloads\1818_SHP"

# ZWERYFIKOWANE: Środek Stalowej Woli (okolice MDK) w układzie EPSG:2180
centrum_sw = Point(716212.0, 304725.0)
ZASIEG_MIASTA_METRY = 4500  # Promień wycinający obszar funkcjonalny miasta
strefa_miasta = centrum_sw.buffer(ZASIEG_MIASTA_METRY)

# NOWOŚĆ: Minimalna wielkość budynku, w którym może powstać kasyno (w m2)
MIN_POW_KASYNO = 250

def znajdz_plik_bdot(folder, przyrostek):
    for plik in os.listdir(folder):
        if plik.endswith(f"{przyrostek}.shp"):
            return os.path.join(folder, plik)
    raise FileNotFoundError(f"Brak warstwy: *{przyrostek}.shp")

print("="*60)
print("1. PRZESZUKIWANIE KATALOGU BDOT10k")
print("="*60)
PATH_BUBD = znajdz_plik_bdot(SHP_DIR, "OT_BUBD_A")
PATH_PTZB = znajdz_plik_bdot(SHP_DIR, "OT_PTZB_A")
PATH_KUPG = znajdz_plik_bdot(SHP_DIR, "OT_KUPG_A")
PATH_KUOS = znajdz_plik_bdot(SHP_DIR, "OT_KUOS_A")

try:
    PATH_PTGN = znajdz_plik_bdot(SHP_DIR, "OT_PTGN_A")
    PATH_PTNZ = znajdz_plik_bdot(SHP_DIR, "OT_PTNZ_A")
    PATH_PTTR = znajdz_plik_bdot(SHP_DIR, "OT_PTTR_A")
    HAS_GRUNTY = True
    print("-> Znaleziono warstwy gruntów nieużytkowanych (PTGN, PTNZ, PTTR)")
except FileNotFoundError as e:
    print(f"-> [INFO] Brak niektórych warstw gruntów: {e}")
    HAS_GRUNTY = False

# =====================================================================
# 2. WCZYTYWANIE I PRZYCINANIE DO GEOMETRII MIASTA (CLIP)
# =====================================================================
print("\n" + "="*60)
print("2. WCZYTYWANIE I OGRANICZANIE DO STALOWEJ WOLI")
print("="*60)

gdf_budynki_all = gpd.read_file(PATH_BUBD).to_crs(epsg=2180).clip(strefa_miasta)
gdf_ptzb        = gpd.read_file(PATH_PTZB).to_crs(epsg=2180).clip(strefa_miasta)
gdf_kupg        = gpd.read_file(PATH_KUPG).to_crs(epsg=2180).clip(strefa_miasta)
gdf_kuos        = gpd.read_file(PATH_KUOS).to_crs(epsg=2180).clip(strefa_miasta)

gdf_grunty_nieuzyt = gpd.GeoDataFrame()
if HAS_GRUNTY:
    frames = []
    for path, kat in [(PATH_PTGN, "PTGN"), (PATH_PTNZ, "PTNZ"), (PATH_PTTR, "PTTR")]:
        try:
            gdf_tmp = gpd.read_file(path).to_crs(epsg=2180).clip(strefa_miasta)
            gdf_tmp["kategoria_grunty"] = kat
            frames.append(gdf_tmp)
        except Exception:
            pass
    if frames:
        gdf_grunty_nieuzyt = pd.concat(frames, ignore_index=True)
        gdf_grunty_nieuzyt = gpd.GeoDataFrame(gdf_grunty_nieuzyt, geometry="geometry", crs=2180)

print(f"-> Obiekty w granicach Stalowej Woli: Budynki={len(gdf_budynki_all)}, Poligony gruntów={len(gdf_grunty_nieuzyt)}")

# =====================================================================
# 3. FUNKCJA FILTRUJĄCA
# =====================================================================
def filtruj_warstwe(gdf, kody_std, slowa_kluczowe):
    if gdf.empty: return gdf.copy()
    mask = pd.Series(False, index=gdf.index)
    for col in gdf.columns:
        if col != 'geometry' and gdf[col].dtype == 'object':
            clean = gdf[col].astype(str).str.strip()
            mask |= clean.str.upper().isin([str(k).upper() for k in kody_std])
            for slowo in slowa_kluczowe:
                mask |= clean.str.contains(slowo, case=False, na=False)
    return gdf[mask].copy()

# =====================================================================
# 4. FILTROWANIE HYBRYDOWE (KODY BDOT + SŁOWA KLUCZOWE)
# =====================================================================
przemysl_budynki   = filtruj_warstwe(gdf_budynki_all, ['BUBD11', '1251', '1252'], ['przemyslowy', 'przemysłowy', 'produkcyjny', 'magazyn'])
przemysl_strefy    = filtruj_warstwe(gdf_ptzb, ['PTZB03', 'PTNZ02'], ['przemyslowa', 'przemysłowa', 'składowa', 'magazyn'])
przemysl_kompleksy = filtruj_warstwe(gdf_kupg, [], ['KUPG', 'elektrownia', 'huta', 'fabryka', 'zaklad', 'zakład'])
szkoly_budynki     = filtruj_warstwe(gdf_budynki_all, ['BUBD15', '1263'], ['szkoła', 'szkola', 'przedszkole', 'żłobek', 'zlobek'])
szkoly_kompleksy   = filtruj_warstwe(gdf_kuos, ['KUOS02', 'KUOS03', 'KUOS04'], ['szkoła', 'szkola', 'przedszkole', 'żłobek', 'zlobek', 'oświat'])

kody_kandydatow = ['BUBD07', 'BUBD08', 'BUBD09', 'BUBD12', 'BUBD13', 'BUBD17', 'BUBD21', '1220', '1230', '1240', '1260', '1270', '1290']
slowa_kandydatow = ['biurowy', 'biuro', 'handlowy', 'usługowy', 'uslugowy', 'niemieszkalny', 'magazyn', 'kulturalny', 'sportowy', 'techniczny', 'administracyjny']
df_kandydaci_bud = filtruj_warstwe(gdf_budynki_all, kody_kandydatow, slowa_kandydatow)

# =====================================================================
# 5. BUDOWA BAZY KANDYDATÓW (BUDYNKI ORAZ DZIAŁKI)
# =====================================================================
gdfs_przemysl = [g for g in [przemysl_budynki, przemysl_strefy, przemysl_kompleksy] if not g.empty]
strefa_przemyslowa = pd.concat([g.geometry for g in gdfs_przemysl]).unary_union if gdfs_przemysl else None

gdfs_szkoly = [g for g in [szkoly_budynki, szkoly_kompleksy] if not g.empty]
strefa_szkolna = pd.concat([g.geometry for g in gdfs_szkoly]).unary_union if gdfs_szkoly else None

def buduj_kandydatow(gdf, typ):
    df = gdf[['geometry']].copy()
    df['typ_kandydata'] = typ
    df['centroid']      = df.geometry.centroid
    df['dist_center']   = df['centroid'].distance(centrum_sw)
    df['dist_ind']      = df['centroid'].distance(strefa_przemyslowa) if strefa_przemyslowa else 999999.0
    df['dist_school']   = df['centroid'].distance(strefa_szkolna) if strefa_szkolna else 999999.0
    df['powierzchnia']  = df.geometry.area
    return df

frames_kandydaci = []
if len(df_kandydaci_bud) > 0:
    frames_kandydaci.append(buduj_kandydatow(df_kandydaci_bud, 'budynek'))

if len(gdf_grunty_nieuzyt) > 0:
    gdf_grunty_sens = gdf_grunty_nieuzyt[(gdf_grunty_nieuzyt.geometry.area >= 500) & (gdf_grunty_nieuzyt.geometry.area <= 50000)].copy()

    MAX_DIST_GRUNTY = 4000
    if len(gdf_grunty_sens) > 0:
        centr_tmp = gdf_grunty_sens.geometry.centroid
        dist_tmp  = centr_tmp.distance(centrum_sw)
        gdf_grunty_sens = gdf_grunty_sens[dist_tmp <= MAX_DIST_GRUNTY].copy()

    MAX_GRUNTY = 200
    if len(gdf_grunty_sens) > MAX_GRUNTY:
        centr_tmp = gdf_grunty_sens.geometry.centroid
        dist_tmp  = centr_tmp.distance(centrum_sw)
        score_tmp = -dist_tmp + gdf_grunty_sens.geometry.area * 0.01
        idx_top   = score_tmp.nlargest(MAX_GRUNTY).index
        gdf_grunty_sens = gdf_grunty_sens.loc[idx_top].copy()

    if len(gdf_grunty_sens) > 0:
        frames_kandydaci.append(buduj_kandydatow(gdf_grunty_sens, 'grunt'))

df_kandydaci = pd.concat(frames_kandydaci, ignore_index=True)
df_kandydaci['model_id'] = range(1, len(df_kandydaci) + 1)
df_kandydaci = gpd.GeoDataFrame(df_kandydaci, geometry='geometry', crs=2180)
df_kandydaci = df_kandydaci.drop(columns=['centroid'], errors='ignore')

# =====================================================================
# 6. MODEL OPTYMALIZACYJNY PuLP
# =====================================================================
FUNKCJE = ['apartamenty', 'zlobki', 'gastro', 'kasyno']
budynki_ids = df_kandydaci[df_kandydaci['typ_kandydata'] == 'budynek']['model_id'].tolist()
grunty_ids  = df_kandydaci[df_kandydaci['typ_kandydata'] == 'grunt']['model_id'].tolist()
wszystkie_ids = df_kandydaci['model_id'].tolist()

dist_to_ind    = dict(zip(df_kandydaci['model_id'], df_kandydaci['dist_ind']))
dist_to_center = dict(zip(df_kandydaci['model_id'], df_kandydaci['dist_center']))
dist_to_school = dict(zip(df_kandydaci['model_id'], df_kandydaci['dist_school']))
powierzchnia   = dict(zip(df_kandydaci['model_id'], df_kandydaci['powierzchnia']))

def oblicz_atrakcyjnosc(i, typ):
    a = {f: 0 for f in FUNKCJE}
    dc  = dist_to_center[i]
    di  = dist_to_ind[i]
    ds  = dist_to_school[i]
    pow_m2 = powierzchnia[i]
    bonus_pow = min(30, pow_m2 / 300) if typ == 'grunt' else 0

    if di >= 1000:
        a['apartamenty'] = max(0, 200 - dc * 0.05) + bonus_pow
    if 1000 <= di <= 4000:
        a['zlobki'] = 150 + bonus_pow
    if dc <= 1500 or di <= 1000:
        a['gastro'] = 200 + bonus_pow
    if dc <= 3000 and ds >= 400:
        a['kasyno'] = max(0, 250 - dc * 0.04)
    return a

atrakcyjnosc = {row['model_id']: oblicz_atrakcyjnosc(row['model_id'], row['typ_kandydata']) for _, row in df_kandydaci.iterrows()}

model = pulp.LpProblem("Optymalizacja_Stalowa_Wola_Light", pulp.LpMaximize)
x = {(i, j): pulp.LpVariable(f"x_{i}_{j}", cat='Binary') for i in wszystkie_ids for j in FUNKCJE}

model += pulp.lpSum(atrakcyjnosc[i][j] * x[i, j] for i in wszystkie_ids for j in FUNKCJE)

for i in wszystkie_ids:
    model += pulp.lpSum(x[i, j] for j in FUNKCJE) <= 1
    if dist_to_school[i] < 400:
        model += x[i, 'zlobki'] == 0
        model += x[i, 'kasyno'] == 0

    # NOWOŚĆ: Twardy warunek minimalnej powierzchni dla funkcji kasyna
    if powierzchnia[i] < MIN_POW_KASYNO:
        model += x[i, 'kasyno'] == 0

for i in grunty_ids:
    if dist_to_ind[i] < 300:
        for j in FUNKCJE: model += x[i, j] == 0

max_budynki = {'apartamenty': 10, 'zlobki': 4, 'gastro': 8, 'kasyno': 1}
max_grunty  = {'apartamenty':  5, 'zlobki': 2, 'gastro':  3, 'kasyno': 0}

for j in FUNKCJE:
    model += pulp.lpSum(x[i, j] for i in budynki_ids) <= max_budynki[j]
    model += pulp.lpSum(x[i, j] for i in grunty_ids)  <= max_grunty[j]

model += pulp.lpSum(x[i, j] for i in wszystkie_ids for j in FUNKCJE) >= 8

# Ograniczenia kolizji przestrzennych (Spatial Constraints)
df_centr_all = gpd.GeoDataFrame(df_kandydaci[['model_id']], geometry=df_kandydaci.geometry.centroid, crs=2180)
df_buf_300 = gpd.GeoDataFrame(df_kandydaci[['model_id']].rename(columns={'model_id': 'model_id_right'}), geometry=df_kandydaci.geometry.centroid.buffer(300), crs=2180)
joined_g = gpd.sjoin(df_centr_all, df_buf_300, how='inner', predicate='within')
for _, row in joined_g[joined_g['model_id'] < joined_g['model_id_right']].iterrows():
    model += x[int(row['model_id']), 'gastro'] + x[int(row['model_id_right']), 'gastro'] <= 1

df_buf_400 = gpd.GeoDataFrame(df_kandydaci[['model_id']].rename(columns={'model_id': 'model_id_right'}), geometry=df_kandydaci.geometry.centroid.buffer(400), crs=2180)
joined_ap = gpd.sjoin(df_centr_all, df_buf_400, how='inner', predicate='within')
for _, row in joined_ap[joined_ap['model_id'] < joined_ap['model_id_right']].iterrows():
    model += x[int(row['model_id']), 'apartamenty'] + x[int(row['model_id_right']), 'apartamenty'] <= 1

print("Uruchamianie solvera CBC...")
solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=60, gapRel=0.03)
status = model.solve(solver)

# =====================================================================
# 7. MAPA WYSOKIEGO KONTRASTU (AUTOMATYCZNY ZOOM + LEGENDA NA ZEWNĄTRZ)
# =====================================================================
df_kandydaci['nowy_cel'] = 'brak zmian'
if pulp.LpStatus[status] in ("Optimal", "Not Solved"):
    total_score = 0
    for i in wszystkie_ids:
        for j in FUNKCJE:
            if pulp.value(x[i, j]) is not None and pulp.value(x[i, j]) > 0.5:
                df_kandydaci.loc[df_kandydaci['model_id'] == i, 'nowy_cel'] = j
                total_score += atrakcyjnosc[i][j]

    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.patches import Circle

        STYL = {
            'apartamenty': dict(kolor_bud='#0D47A1', kolor_grunt='#64B5F6', promien=400, alpha_okrag=0.14, kolor_okrag='#1565C0'),
            'zlobki':       dict(kolor_bud='#B71C1C', kolor_grunt='#EF9A9A', promien=600, alpha_okrag=0.12, kolor_okrag='#C62828'),
            'gastro':       dict(kolor_bud='#1B5E20', kolor_grunt='#81C784', promien=300, alpha_okrag=0.15, kolor_okrag='#2E7D32'),
            'kasyno':       dict(kolor_bud='#4A148C', kolor_grunt=None,      promien=800, alpha_okrag=0.15, kolor_okrag='#6A1B9A'),
        }

        fig, ax = plt.subplots(figsize=(18, 14))
        fig.patch.set_facecolor('#FFFFFF')
        ax.set_facecolor('#F9FBFD')

        if not gdf_budynki_all.empty:
            gdf_budynki_all.plot(ax=ax, color='#C6C6C6', edgecolor='#B5B5B5', linewidth=0.2, zorder=1)

        if not przemysl_budynki.empty:
            przemysl_budynki.plot(ax=ax, color='#CFD8DC', edgecolor='#90A4AE', linewidth=0.4, zorder=2)
        if not szkoly_budynki.empty:
            szkoly_budynki.plot(ax=ax, color='#FFF59D', edgecolor='#FBC02D', linewidth=0.4, zorder=2)
        if len(gdf_grunty_nieuzyt) > 0:
            gdf_grunty_nieuzyt.plot(ax=ax, color='#F5EBE6', edgecolor='#BCAAA4', linewidth=0.3, alpha=0.9, zorder=2)

        uslugi_budynki    = filtruj_warstwe(gdf_budynki_all,
    ['BUBD07', 'BUBD08', 'BUBD09', 'BUBD12', 'BUBD13', 'BUBD17', 'BUBD21'],
    ['biurowy', 'biuro', 'handlowy', 'usługowy', 'uslugowy', 'administracyjny', 'kulturalny'])
        uslugi_budynki.plot(ax=ax, color='#B39DDB', edgecolor='#7E57C2', linewidth=0.4, zorder=3)
        print("Rysowanie stref wpływu...")
        for funk, styl in STYL.items():
            sub_all = df_kandydaci[df_kandydaci['nowy_cel'] == funk]
            if sub_all.empty: continue
            for pt in sub_all.geometry.centroid:
                ax.add_patch(Circle((pt.x, pt.y), radius=styl['promien'], color=styl['kolor_okrag'], fill=True, alpha=styl['alpha_okrag'], zorder=3))
                ax.add_patch(Circle((pt.x, pt.y), radius=styl['promien'], color=styl['kolor_okrag'], fill=False, alpha=0.6, linewidth=1.2, linestyle='--', zorder=4))

        for funk, styl in STYL.items():
            sub_bud = df_kandydaci[(df_kandydaci['nowy_cel'] == funk) & (df_kandydaci['typ_kandydata'] == 'budynek')]
            if not sub_bud.empty:
                sub_bud.plot(ax=ax, color=styl['kolor_bud'], edgecolor='#FFFFFF', linewidth=1.5, zorder=7)

            if styl['kolor_grunt']:
                sub_gr = df_kandydaci[(df_kandydaci['nowy_cel'] == funk) & (df_kandydaci['typ_kandydata'] == 'grunt')]
                if not sub_gr.empty:
                    sub_gr.plot(ax=ax, color=styl['kolor_grunt'], edgecolor='#FFFFFF', linewidth=1.2, linestyle='-', zorder=6)

        # ax.plot(centrum_sw.x, centrum_sw.y, marker='*', color='#FF6F00', markeredgecolor='#000000', markeredgewidth=1.2, markersize=16, zorder=10)
        # ax.annotate('CENTRUM MIASTA (MDK)', xy=(centrum_sw.x, centrum_sw.y), xytext=(centrum_sw.x + 120, centrum_sw.y + 120),
                    # color='#D84315', fontsize=10, fontweight='bold', zorder=10, bbox=dict(facecolor='white', alpha=0.8, edgecolor='none', pad=1))

        legenda = [
            mpatches.Patch(facecolor='#C6C6C6', edgecolor='#B5B5B5', label='Istniejąca zabudowa tła'),
            mpatches.Patch(facecolor='#CFD8DC', edgecolor='#90A4AE', label='Strefy przemysłowo-magazynowe'),
            mpatches.Patch(facecolor='#B39DDB', edgecolor='#7E57C2', label='Budynki usługowe / handlowe / biura'),
            mpatches.Patch(facecolor='#FFF59D', edgecolor='#FBC02D', label='Obiekty oświatowe / szkoły'),
            mpatches.Patch(facecolor='#F5EBE6', edgecolor='#BCAAA4', label='Nieużytki i wolne tereny'),
            # plt.Line2D([0],[0], marker='*', color='#FF6F00', markeredgecolor='black', markersize=11, linestyle='None', label='Środek geometryczny (Google Maps)'),
            mpatches.Patch(facecolor='none', edgecolor='none', label=''),
            mpatches.Patch(facecolor='#0D47A1', edgecolor='white', label='BUDYNEK → Apartamenty'),
            mpatches.Patch(facecolor='#B71C1C', edgecolor='white', label='BUDYNEK → Żłobek miejski'),
            mpatches.Patch(facecolor='#1B5E20', edgecolor='white', label='BUDYNEK → Gastronomia'),
            mpatches.Patch(facecolor='#4A148C', edgecolor='white', label='BUDYNEK → Kasyno'),
            mpatches.Patch(facecolor='#64B5F6', edgecolor='white', label='TEREN → Projektowane Apartamenty'),
            mpatches.Patch(facecolor='#EF9A9A', edgecolor='white', label='TEREN → Projektowany Żłobek'),
            mpatches.Patch(facecolor='#81C784', edgecolor='white', label='TEREN → Projektowana Gastronomia'),
        ]

        ax.legend(handles=legenda, loc='upper left', bbox_to_anchor=(1.02, 1), fontsize=10, frameon=True, facecolor='#FFFFFF', edgecolor='#424242', labelcolor='#000000')

        n_bud = ((df_kandydaci['nowy_cel'] != 'brak zmian') & (df_kandydaci['typ_kandydata'] == 'budynek')).sum()
        n_gr  = ((df_kandydaci['nowy_cel'] != 'brak zmian') & (df_kandydaci['typ_kandydata'] == 'grunt')).sum()
        stat_text = f"Obszar: Stalowa Wola\nPrzekwalifikowane: {n_bud} budynków · {n_gr} działek\nSuma punktów celu: {total_score:.0f} pkt"
        ax.text(0.01, 0.01, stat_text, transform=ax.transAxes, fontsize=10, color='#000000', fontweight='bold', va='bottom',
                bbox=dict(facecolor='#FFFFFF', alpha=0.9, edgecolor='#000000', boxstyle='round,pad=0.5'))

        plt.title("Optymalizacja Przestrzenna Funkcji Miejskich", fontsize=14, fontweight='bold', color='#000000', pad=12)
        ax.tick_params(colors='#000000', labelsize=9.5)
        ax.spines[:].set_edgecolor('#000000')
        plt.xlabel("Współrzędne X [m] — Układ 2180", color='#000000', fontsize=10)
        plt.ylabel("Współrzędne Y [m] — Układ 2180", color='#000000', fontsize=10)
        plt.grid(True, linestyle=':', alpha=0.5, color='#757575')

        # =====================================================================
        # NOWOŚĆ: DYNAMICZNY ZOOM (ZWIĘKSZANIE SKALI MAPY)
        # =====================================================================
        df_wybrane = df_kandydaci[df_kandydaci['nowy_cel'] != 'brak zmian']
        if not df_wybrane.empty:
            # Pobieramy ekstremalne punkty przypisanych celów (Xmin, Ymin, Xmax, Ymax)
            bounds = df_wybrane.geometry.total_bounds
            # Dodajemy bufor bezpieczeństwa (np. 500 metrów), by strefy nie opierały się o krawędź okna
            margines = 500
            ax.set_xlim(bounds[0] - margines, bounds[2] + margines)
            ax.set_ylim(bounds[1] - margines, bounds[3] + margines)
            print(f"-> Skala dopasowana automatycznie do obszaru inwestycji.")
        else:
            # W razie braku wyników, cofnij do widoku ogólnego
            ax.set_xlim(centrum_sw.x - ZASIEG_MIASTA_METRY, centrum_sw.x + ZASIEG_MIASTA_METRY)
            ax.set_ylim(centrum_sw.y - ZASIEG_MIASTA_METRY, centrum_sw.y + ZASIEG_MIASTA_METRY)

        plt.tight_layout()
        plt.savefig(os.path.join(SHP_DIR, "mapa_stalowa_wola_kontrast.png"), dpi=220, bbox_inches='tight')
        plt.show()

    except Exception as e:
        print(f"Błąd wizualizacji: {e}")
else:
    print(f"Solver nie znalazł rozwiązania: {pulp.LpStatus[status]}")