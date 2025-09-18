import streamlit as st
import pandas as pd
import datetime as dt
import json, os, unicodedata, re, calendar

# ==============================
# --- Fonctions utilitaires ---
# ==============================
def to_float(x):
    if pd.isna(x): return 0.0
    s = str(x).replace("€","").replace(" ","").replace(",",".")
    try:
        return float(s)
    except ValueError:
        return 0.0

def parse_taux(x):
    if pd.isna(x): return None
    s = str(x).replace("%","").replace(" ","").replace(",",".")
    try:
        val = float(s)
    except ValueError:
        return None
    if val > 1: val = val/100
    return round(val,3)

def normalize_text(s):
    s = str(s).strip().upper()
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def get_periode_excel(xls):
    try:
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=None, nrows=3, engine="openpyxl")
        val = df.iloc[2,0]
        if isinstance(val, (pd.Timestamp, dt.datetime, dt.date)):
            return val.month, val.year
        match = re.search(r"(\d{1,2})/(\d{4})", str(val))
        if match:
            return int(match.group(1)), int(match.group(2))
    except:
        pass
    return None, None

# ==============================
# --- Authentification ---
# ==============================
USERS = {
    "aurore": {"password": "12345", "name": "Aurore Demoulin"},
    "nicolas": {"password": "12345", "name": "Nicolas Cuisset"},
    "manana": {"password": "46789", "name": "Manana"},
    "louis": {"password": "195827", "name": "Louis le plus grand collaborateur du monde"}
}

def login(username, password):
    if username in USERS and password == USERS[username]["password"]:
        st.session_state["login"] = True
        st.session_state["username"] = username
        st.session_state["name"] = USERS[username]["name"]
        return True
    return False

if "login" not in st.session_state:
    st.session_state["login"] = False

if not st.session_state["login"]:
    st.title("🔑 Veuillez entrer vos identifiants")
    username_input = st.text_input("Identifiant")
    password_input = st.text_input("Mot de passe", type="password")
    if st.button("Connexion"):
        if login(username_input, password_input):
            st.success(f"Bienvenue {st.session_state['name']} 👋")
            st.experimental_rerun() if hasattr(st, "experimental_rerun") else st.stop()
        else:
            st.error("❌ Identifiants incorrects")
    st.stop()

st.sidebar.success(f"Bienvenue {st.session_state['name']} 👋")
if st.sidebar.button("Déconnexion"):
    st.session_state["login"] = False
    st.experimental_rerun() if hasattr(st, "experimental_rerun") else st.stop()

# ==============================
# --- Google Sheets : multi-clients ---
# ==============================
import gspread
from oauth2client.service_account import ServiceAccountCredentials

def auth_gsheets(json_keyfile):
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(json_keyfile, scope)
    client = gspread.authorize(creds)
    return client

def get_clients(gclient, sheet_name):
    sh = gclient.open(sheet_name)
    return [ws.title for ws in sh.worksheets()]

def load_client_params(gclient, sheet_name, client_name):
    sh = gclient.open(sheet_name)
    ws = sh.worksheet(client_name)
    data = ws.get_all_records()
    params = {}
    for row in data:
        if "Famille" in row:
            params.setdefault("famille_to_compte", {})[row["Famille"]] = row["Compte"]
        if "TVA" in row:
            params.setdefault("tva_to_compte", {})[float(row["TVA"])] = row["Compte"]
        if "Mode de paiement" in row:
            params.setdefault("tiroir_to_compte", {})[row["Mode de paiement"]] = row["Compte"]
        if "Point Comptable" in row:
            params["compte_point_comptable"] = row["Compte"]
    return params

# --- Auth Google Sheets ---
gclient = auth_gsheets("credentials.json")  # ton fichier JSON téléchargé
sheet_name = "Paramètres Utilisateurs"     # nom de ta Google Sheet
clients = get_clients(gclient, sheet_name)

# --- Sélection client ---
client_selected = st.sidebar.selectbox("Sélectionner le client", clients)
params = load_client_params(gclient, sheet_name, client_selected)

st.sidebar.write(f"⚙️ Paramètres chargés pour le client : **{client_selected}**")

# ==============================
# --- Upload fichier Excel ---
# ==============================
try:
    import openpyxl
except ImportError:
    st.error("⚠️ openpyxl n'est pas installé.")
    st.stop()

uploaded_file = st.file_uploader("Choisir le fichier Excel", type=["xls","xlsx"])
if not uploaded_file:
    st.stop()

try:
    xls = pd.ExcelFile(uploaded_file, engine="openpyxl")
except Exception as e:
    st.error(f"Erreur lors de la lecture du fichier Excel : {e}")
    st.stop()

# --- Lecture des feuilles ---
try:
    df_familles = pd.read_excel(xls, sheet_name="ANALYSE FAMILLES", header=2, engine="openpyxl")
    df_tva      = pd.read_excel(xls, sheet_name="ANALYSE TVA", header=2, engine="openpyxl")
    df_tiroir   = pd.read_excel(xls, sheet_name="Solde tiroir", header=2, engine="openpyxl")
    df_point    = pd.read_excel(xls, sheet_name="Point comptable", header=6, engine="openpyxl")
except Exception as e:
    st.error(f"Erreur lors de la lecture des feuilles Excel : {e}")
    st.stop()

for df in [df_familles, df_tva, df_tiroir, df_point]:
    df.columns = [str(c).strip() for c in df.columns]

# ==============================
# --- Détermination période ---
# ==============================
mois, annee = get_periode_excel(xls)
if not mois or not annee:
    today = dt.date.today()
    mois, annee = today.month, today.year

dernier_jour = calendar.monthrange(annee, mois)[1]
date_ecriture = dt.date(annee, mois, dernier_jour)
libelle = f"CA {mois:02d}-{annee}"

# ==============================
# --- Paramètres comptes dynamiques ---
# ==============================
col_fam_lib = "FAMILLE" if "FAMILLE" in df_familles.columns else df_familles.columns[0]
familles_dyn = [str(f).strip() for f in df_familles[col_fam_lib] if pd.notna(f) and "TOTAL" not in str(f).upper()]

# Comptes Familles
famille_to_compte = params.get("famille_to_compte", {})
# Comptes TVA
tva_to_compte = params.get("tva_to_compte", {})
# Comptes encaissements
tiroir_to_compte = params.get("tiroir_to_compte", {})
# Compte point comptable
compte_point_comptable = params.get("compte_point_comptable", "467700000")

# Code journal
journal_code = st.text_input("Code journal", value="CA")

# ==============================
# --- Génération des écritures ---
# ==============================
ecritures = []

# 1️⃣ CA HT par famille
col_fam_caht = "CA HT" if "CA HT" in df_familles.columns else df_familles.columns[1]
for _, row in df_familles.iterrows():
    fam = str(row[col_fam_lib])
    if "TOTAL" in fam.upper(): continue
    montant = to_float(row[col_fam_caht])
    if montant <= 0: continue
    compte = famille_to_compte.get(fam, "707000000")
    ecritures.append({
        "DATE": date_ecriture.strftime("%d/%m/%Y"),
        "CODE JOURNAL": journal_code,
        "NUMERO DE COMPTE": compte,
        "LIBELLE": libelle,
        "DEBIT": 0,
        "CREDIT": montant
    })

# 2️⃣ TVA collectée
for _, row in df_tva.iterrows():
    lib = normalize_text(row["LIBELLE TVA"])
    if "EXONERE" in lib or "TOTAL" in lib or pd.isna(row["TVA"]): continue
    montant_tva = to_float(row["TVA"])
    if montant_tva <= 0: continue
    taux = parse_taux(row["Taux"])
    compte = tva_to_compte.get(taux)
    if compte:
        ecritures.append({
            "DATE": date_ecriture.strftime("%d/%m/%Y"),
            "CODE JOURNAL": journal_code,
            "NUMERO DE COMPTE": compte,
            "LIBELLE": libelle,
            "DEBIT": 0,
            "CREDIT": montant_tva
        })

# 3️⃣ Encaissements tiroir
for _, row in df_tiroir.iterrows():
    lib = normalize_text(row["Paiement"])
    if "TOTAL" in lib or lib == "": continue
    montant = to_float(row["Montant en euro"])
    if montant <= 0: continue
    if "ESPECE" in lib:
        compte = tiroir_to_compte["ESPECES"]
    elif "CB" in lib or "CARTE" in lib:
        compte = tiroir_to_compte["CB"]
    elif "CHEQUE" in lib:
        compte = tiroir_to_compte["CHEQUE"]
    elif "VIREMENT" in lib:
        compte = tiroir_to_compte["VIREMENT"]
    else:
        compte = "411100000"
    ecritures.append({
        "DATE": date_ecriture.strftime("%d/%m/%Y"),
        "CODE JOURNAL": journal_code,
        "NUMERO DE COMPTE": compte,
        "LIBELLE": libelle,
        "DEBIT": montant,
        "CREDIT": 0
    })

# 4️⃣ Sorties point comptable
for _, row in df_point.iterrows():
    lib = row["Libellé"]
    if pd.isna(lib) or str(lib).strip() == "": continue
    if "TOTAL" in str(lib).upper(): continue
    montant = to_float(row["Montant en euro"])
    if montant == 0: continue
    ecritures.append({
        "DATE": date_ecriture.strftime("%d/%m/%Y"),
        "CODE JOURNAL": journal_code,
        "NUMERO DE COMPTE": compte_point_comptable,
        "LIBELLE": libelle,
        "DEBIT": abs(montant),
        "CREDIT": 0
    })

# ==============================
# Vérification équilibre
# ==============================
df_ecritures = pd.DataFrame(ecritures)
total_debit  = df_ecritures["DEBIT"].sum()
total_credit = df_ecritures["CREDIT"].sum()
st.write("Total DEBIT :", total_debit)
st.write("Total CREDIT:", total_credit)
if round(total_debit,2) != round(total_credit,2):
    st.warning("⚠️ Les écritures ne sont pas équilibrées ! Écart : "
               f"{round(total_debit - total_credit,2)} €")
else:
    st.success("✅ Les écritures sont équilibrées.")

st.subheader("👀 Aperçu des écritures générées")
st.dataframe(df_ecritures)

# Export Excel
output_file = "ECRITURES_COMPTABLES.xlsx"
df_ecritures.to_excel(output_file, index=False)
st.download_button("📥 Télécharger le fichier généré",
                   data=open(output_file,"rb"),
                   file_name=output_file)

# ==============================
# --- Mention auteur ---
# ==============================
st.markdown("<hr><p style='text-align:center; font-size:12px;'>⚡ Application créée par Nicolas Cuisset</p>", unsafe_allow_html=True)
