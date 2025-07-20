import dash
from dash import html, dcc, Input, Output, State, dash_table
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from collections import defaultdict
import base64

# ✅ Ajouter Bootstrap pour le style
app = dash.Dash(__name__, external_stylesheets=[
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
])
server = app.server


def fetch_mrc_roles():
    resource_id = "d2db6102-9215-4abc-9b5b-2c37f2e12618"
    base_url = "https://www.donneesquebec.ca/recherche/api/3/action/datastore_search"
    records = []
    offset = 0
    limit = 100

    while True:
        url = f"{base_url}?resource_id={resource_id}&limit={limit}&offset={offset}"
        response = requests.get(url)
        if response.status_code != 200:
            return pd.DataFrame()
        data = response.json()["result"]

        if "records" not in data or len(data["records"]) == 0:
            return pd.DataFrame()

        records.extend(data["records"])
        if len(data["records"]) < limit:
            break
        offset += limit

    df = pd.DataFrame(records)
    df.columns = df.columns.str.strip().str.lower()
    if "nom du territoire" not in df.columns or "lien" not in df.columns:
        return pd.DataFrame()
    return df[["nom du territoire", "lien"]].rename(columns={"nom du territoire": "MRC", "lien": "URL"}).sort_values("MRC")


def parse_xml_to_df(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as e:
        print(f"Erreur XML : {e}")
        return pd.DataFrame()

    rows = []
    for ue in root.findall(".//RLUEx"):
        code_cubf = ue.findtext("RL0105A")
        logements_str = ue.findtext("RL0311A")

        try:
            logements = int(logements_str) if logements_str else 0
        except:
            logements = 0

        rows.append({
            "RL0105A": code_cubf.strip() if code_cubf else "Inconnu",
            "RL0311A": logements
        })

    return pd.DataFrame(rows)


df_mrc = fetch_mrc_roles()

# ✅ Layout moderne et responsive
app.layout = html.Div(className="container py-5", children=[
    html.Div(className="text-center mb-5", children=[
        html.H1("📊 Analyse des rôles d’évaluation foncière du Québec", className="fw-bold text-primary"),
        html.P("Sélectionnez une MRC et analysez les codes CUBF avec un design moderne.", className="lead text-muted")
    ]),

    html.Div(className="card p-4 shadow-sm mb-4", children=[
        html.Label("📍 Choisissez une MRC :", className="form-label fw-semibold"),
        dcc.Dropdown(
            id='mrc-dropdown',
            options=[{'label': row['MRC'], 'value': row['URL']} for _, row in df_mrc.iterrows()],
            placeholder="Sélectionner une MRC",
            className="form-select mb-3"
        ),
        html.A(id='xml-download-link', href="#", target="_blank",
               children="⬇️ Télécharger le fichier XML brut",
               className="btn btn-outline-secondary mb-3 w-100"),
        html.Button("🚀 Charger et analyser le fichier XML", id='load-button', n_clicks=0, className="btn btn-primary w-100"),
        html.Div(id='load-status', className="alert alert-info mt-3", role="alert")
    ]),

    html.Div(id='cubf-section', className="my-4"),
    html.Div(id='resultats', className="my-5")
])


@app.callback(
    [Output('xml-download-link', 'href'),
     Output('load-status', 'children'),
     Output('cubf-section', 'children')],
    Input('load-button', 'n_clicks'),
    State('mrc-dropdown', 'value'),
    prevent_initial_call=True
)
def load_xml(n_clicks, selected_url):
    if not selected_url:
        return "#", "⚠️ Veuillez sélectionner une MRC.", None

    try:
        response = requests.get(selected_url)
        response.raise_for_status()
        df_xml = parse_xml_to_df(response.content)
    except Exception as e:
        return "#", f"❌ Erreur : {e}", None

    if df_xml.empty:
        return "#", "⚠️ Aucun enregistrement trouvé.", None

    app.server.df_xml = df_xml

    codes_cubf = sorted(df_xml["RL0105A"].dropna().unique())
    grouped = defaultdict(list)
    for code in codes_cubf:
        try:
            code_int = int(code)
            millier = (code_int // 1000) * 1000
        except:
            millier = "Inconnu"
        grouped[millier].append(code)

    checklist_groups = []
    for millier in sorted(grouped.keys()):
        checklist_groups.append(html.Div(className="card p-3 mb-3", children=[
            html.H5(f"Codes {millier}–{millier + 999}" if isinstance(millier, int) else "Codes inconnus", className="fw-semibold mb-2"),
            html.Div(className="row g-2", children=[
                html.Div(className="col", children=[
                    dcc.Checklist(
                        options=[{'label': code, 'value': code} for code in sorted(grouped[millier])],
                        id={'type': 'cubf-checklist', 'index': str(millier)},
                        inline=False,  # ✅ Chaque code sur une ligne
                        className="form-check"
                    )
                ])
            ])
        ]))

    return selected_url, "✅ Fichier XML chargé avec succès.", html.Div([
        html.H4("Sélection des codes CUBF", className="fw-bold mb-3"),
        *checklist_groups
    ])


@app.callback(
    Output('resultats', 'children'),
    Input({'type': 'cubf-checklist', 'index': dash.ALL}, 'value'),
    prevent_initial_call=True
)
def update_resultats(selected_codes_groups):
    df_xml = getattr(app.server, 'df_xml', pd.DataFrame())
    if df_xml.empty:
        return html.Div("⚠️ Aucune donnée XML chargée.", className="alert alert-warning")

    selected_codes = []
    for group in selected_codes_groups:
        if group:
            selected_codes.extend(group)

    if not selected_codes:
        return html.Div("ℹ️ Veuillez sélectionner au moins un code CUBF.", className="alert alert-info")

    df_filtre = df_xml[df_xml["RL0105A"].isin(selected_codes)]
    total_batiments = len(df_filtre)
    total_logements = df_filtre["RL0311A"].sum()

    csv_string = df_filtre.to_csv(index=False, encoding='utf-8')
    b64_csv = base64.b64encode(csv_string.encode()).decode()
    csv_href = f"data:text/csv;base64,{b64_csv}"

    df_resume = (
        df_filtre.groupby("RL0105A")
        .agg(nb_batiments=("RL0105A", "count"), nb_logements=("RL0311A", "sum"))
        .reset_index()
        .rename(columns={"RL0105A": "Code CUBF"})
    )

    return html.Div(className="card p-4 shadow-sm", children=[
        html.H4("📊 Résultats", className="fw-bold text-success mb-3"),
        html.Ul([
            html.Li(f"Nombre total d’unités sélectionnées : {total_batiments}", className="mb-1"),
            html.Li(f"Nombre total de logements : {total_logements}")
        ], className="list-unstyled text-muted"),
        dash_table.DataTable(
            data=df_resume.to_dict('records'),
            columns=[{'name': col, 'id': col} for col in df_resume.columns],
            style_table={'overflowX': 'auto'},
            style_cell={'textAlign': 'center'},
            className="table table-striped table-hover"
        ),
        html.A("⬇️ Télécharger les résultats filtrés (CSV)", href=csv_href, download="resultats_filtrés.csv",
               className="btn btn-outline-primary mt-3 w-100")
    ])


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050)
