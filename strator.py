import streamlit as st
import pandas as pd
import datetime as dt
import json, os
import gspread
from google.oauth2.service_account import Credentials

# ==============================
# --- Config Google Sheets ---
# ==============================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = "service_account.json"  # ton fichier JSON
SPREADSHEET_CLIENTS = "Clients_Tabac"          # nom de la Google Sheet

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)
try:
    sheet_clients = gc.open(SPREADSHEET_CLIENTS).sheet1
except gspread.SpreadsheetNotFound:
    sheet_clients = gc.create(SPREADSHEET_CLIENTS).sheet1
    sheet_clients.append_row(["username", "client_name", "email"])

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

PARAM_FILE = "parametres_comptes.json"

def charger_parametres():
    if os.path.exists(PARAM_FILE):
        with open(PARAM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def sauvegarder_parametres(params):
    with open(PARAM_FILE, "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False, indent=2)

def ajouter_client(username, client_name, email):
    sheet_clients.append_row([username, client_name, email])

def get_clients(username):
    all_clients = sheet_clients.get_all_records()
    return [c for c in all_clients if c["username"] == username]

# ==============================
# --- Authentification ---
# ==============================
def login(username, password):
    users = {
        "aurore": {"password": "12345", "name": "Aurore Demoulin"},
        "nicolas": {"password": "12345", "name": "Nicolas Cuisset"}
    }
    if username in users and password == users[username]["password"]:
        st.session_state["login"] = True
        st.session_state["username"] = username
        st.session_state["name"] = users[username]["name"]
        return True
    return False

if "login" not in st.session_state:
    st.session_state["login"] = False

# Bloquer l'interface tant que non connecté
if not st.session_state["login"]:
    st.title("🔑 Veuillez entrer vos identifiants")
    username_input = st.text_input("Identifiant")
    password_input = st.text_input("Mot de passe", type="password")
    if st.button("Connexion"):
        if login(username_input, password_input):
            st.success(f"Bienvenue {st.session_state['name']} 👋")
            st.stop()
        else:
            st.error("❌ Identifiants incorrects")
    st.stop()

# Si connecté
st.sidebar.success(f"Bienvenue {st.session_state['name']} 👋")
if st.sidebar.button("Déconnexion"):
    st.session_state["login"] = False
    st.experimental_rerun()

# ==============================
# --- Gestion multi-clients ---
# ==============================
st.sidebar.header("👥 Clients")
clients_user = get_clients(st.session_state["username"])
client_names = [c["client_name"] for c in clients_user]

selected_client = st.sidebar.selectbox("Sélectionner un client", client_names)

with st.sidebar.expander("➕ Ajouter un client"):
    new_client_name = st.text_input("Nom du client")
    new_client_email = st.text_input("Email")
    if st.button("Ajouter le client"):
        if new_client_name.strip() != "":
            ajouter_client(st.session_state["username"], new_client_name, new_client_email)
            st.success("Client ajouté ✅")
            st.experimental_rerun()

# ==============================
# --- Paramètres comptes ---
# ==============================
params = charger_parametres()
st.sidebar.header("⚙️ Paramètres des comptes")

# ==============================
# --- Upload fichier Excel ---
# ==============================
uploaded_file = st.file_uploader("Choisir le fichier Excel", type=["xls","xlsx"])
if not uploaded_file:
    st.stop()

xls = pd.ExcelFile(uploaded_file)

# Lire familles pour lister dynamiquement
df_familles = pd.read_excel(xls, sheet_name="ANALYSE FAMILLES", header=2)
df_familles.columns = [str(c).strip() for c in df_familles.columns]
col_fam_lib = "FAMILLE" if "FAMILLE" in df_familles.columns else df_familles.columns[0]

familles_dyn = []
for f in df_familles[col_fam_lib]:
    if pd.isna(f): continue
    f = str(f).strip()
    if f and "TOTAL" not in f.upper():
        familles_dyn.append(f)

# --- Comptes familles dynamiques
st.sidebar.subheader("Comptes Familles")
famille_to_compte = {}
for fam in familles_dyn:
    default = params.get("famille_to_compte", {}).get(fam, "707000000")
    famille_to_compte[fam] = st.sidebar.text_input(f"Compte pour {fam}", value=default)

# --- Comptes TVA
st.sidebar.subheader("Comptes TVA")
default_tva = {0.055: "445710060", 0.10: "445710090", 0.20: "445710080"}
tva_to_compte = {}
for taux, def_cpt in default_tva.items():
    default = params.get("tva_to_compte", {}).get(str(taux), def_cpt)
    tva_to_compte[taux] = st.sidebar.text_input(f"Compte TVA {int(taux*100)}%", value=default)

# --- Comptes encaissements
st.sidebar.subheader("Comptes Encaissements")
default_tiroir = {"ESPECES": "530000000", "CB": "411100003", "CHEQUE": "411100004", "VIREMENT": "411100005"}
tiroir_to_compte = {}
for mode, def_cpt in default_tiroir.items():
    default = params.get("tiroir_to_compte", {}).get(mode, def_cpt)
    tiroir_to_compte[mode] = st.sidebar.text_input(f"Compte pour {mode}", value=default)

# --- Compte point comptable
default_point = params.get("compte_point_comptable", "65800000")
compte_point_comptable = st.sidebar.text_input("Compte Point Comptable", value=default_point)

# Bouton de sauvegarde
if st.sidebar.button("💾 Sauvegarder paramètres"):
    params_new = {
        "famille_to_compte": famille_to_compte,
        "tva_to_compte": {str(k): v for k, v in tva_to_compte.items()},
        "tiroir_to_compte": tiroir_to_compte,
        "compte_point_comptable": compte_point_comptable
    }
    sauvegarder_parametres(params_new)
    st.sidebar.success("Paramètres sauvegardés ✅")

# ==============================
# Paramètres écriture
# ==============================
date_ecriture = st.date_input("Date d'écriture", value=dt.date.today())
libelle = st.text_input("Libellé d'écriture", value=f"CA {date_ecriture.strftime('%m-%Y')}")
journal_code = st.text_input("Code journal", value="VE")

# ==============================
# Lecture autres feuilles
# ==============================
df_tva      = pd.read_excel(xls, sheet_name="ANALYSE TVA", header=2)
df_tiroir   = pd.read_excel(xls, sheet_name="Solde tiroir", header=2)
df_point    = pd.read_excel(xls, sheet_name="Point comptable", header=6)

for df in [df_tva, df_tiroir, df_point]:
    df.columns = [str(c).strip() for c in df.columns]

# ==============================
# Génération des écritures
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
        "LIBELLE": f"{libelle} - {fam}",
        "DEBIT": 0,
        "CREDIT": montant
    })

# 2️⃣ TVA collectée
for _, row in df_tva.iterrows():
    lib = str(row["LIBELLE TVA"]).upper()
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
            "LIBELLE": f"TVA {int(taux*100)}%",
            "DEBIT": 0,
            "CREDIT": montant_tva
        })

# 3️⃣ Encaissements tiroir
for _, row in df_tiroir.iterrows():
    lib = str(row["Paiement"]).strip().upper()
    if "TOTAL" in lib or lib == "": continue
    montant = to_float(row["Montant en euro"])
    if montant <= 0: continue
    compte = None
    for key in tiroir_to_compte:
        if key in lib:
            compte = tiroir_to_compte[key]
            break
    if not compte: compte = "411100000"
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
    lib_str = str(lib).strip()
    if "TOTAL" in lib_str.upper(): continue
    montant = to_float(row["Montant en euro"])
    if montant == 0: continue
    ecritures.append({
        "DATE": date_ecriture.strftime("%d/%m/%Y"),
        "CODE JOURNAL": journal_code,
        "NUMERO DE COMPTE": compte_point_comptable,
        "LIBELLE": f"{libelle} - {lib_str}",
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