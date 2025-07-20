import dash
from dash import html, dcc, Input, Output, State, dash_table
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from collections import defaultdict

app = dash.Dash(__name__)
server = app.server

def fetch_mrc_roles():
    # (… ta fonction identique …)
    ...

def parse_xml_to_df(xml_bytes):
    # (… ta fonction identique …)
    ...

df_mrc = fetch_mrc_roles()

app.layout = html.Div(style={'maxWidth': '1200px', 'margin': 'auto', 'padding': '30px'}, children=[
    html.H1("📊 Analyse des rôles d’évaluation foncière du Québec par codes CUBF",
             style={'textAlign': 'center', 'marginBottom': '20px'}),
    html.Div([
        html.Label("📍 Choisissez une MRC :", style={'fontWeight': '600'}),
        dcc.Dropdown(
            id='mrc-dropdown',
            options=[{'label': row['MRC'], 'value': row['URL']} for _, row in df_mrc.iterrows()],
            placeholder="Sélectionner une MRC",
            style={'marginBottom': '20px'}
        ),
        html.Button("🚀 Charger et analyser le fichier XML", id='load-button', n_clicks=0,
                    style={'backgroundColor': '#0d6efd', 'color': 'white',
                           'padding': '10px 20px', 'border': 'none', 'borderRadius': '4px'}),
        html.Div(id='load-status', style={'marginTop': '15px'})
    ], style={'boxShadow': '0 0 10px rgba(0,0,0,0.05)', 'padding': '20px', 'borderRadius': '6px'}),
    html.Div(id='cubf-section', style={'marginTop': '30px'}),
    html.Div(id='resultats', style={'marginTop': '40px', 'marginBottom': '40px'})
])

@app.callback(
    [Output('load-status', 'children'),
     Output('cubf-section', 'children')],
    Input('load-button', 'n_clicks'),
    State('mrc-dropdown', 'value'),
    prevent_initial_call=True
)
def load_xml(nc, url):
    if not url:
        return html.Div("⚠️ Veuillez sélectionner une MRC.", style={'color': 'orange'}), None
    try:
        df_xml = parse_xml_to_df(requests.get(url).content)
    except Exception as e:
        return html.Div(f"❌ Erreur : {e}", style={'color': 'red'}), None
    if df_xml.empty:
        return html.Div("⚠️ Aucun enregistrement trouvé.", style={'color': 'orange'}), None

    app.server.df_xml = df_xml
    grouped = defaultdict(list)
    for code in sorted(df_xml["RL0105A"].unique()):
        mill = int(code)//1000*1000 if code.isdigit() else "Inconnu"
        grouped[mill].append(code)

    sections = []
    for mill, codes in sorted(grouped.items()):
        sections.append(html.Div([
            html.Label(f"Codes {mill}–{mill+999}" if mill != "Inconnu" else "Codes inconnus",
                       style={'fontWeight': '600', 'marginBottom': '8px'}),
            html.Div(style={
                'display': 'grid',
                'gridTemplateColumns': 'repeat(auto-fill, minmax(100px, 1fr))',
                'gap': '10px'
            }, children=[
                dcc.Checklist(
                    options=[{'label': code, 'value': code} for code in codes],
                    id={'type': 'cubf-checklist', 'index': str(mill)}
                )
            ])
        ], style={'padding': '15px', 'marginBottom': '15px',
                  'boxShadow': '0 0 8px rgba(0,0,0,0.03)', 'borderRadius': '5px'}))

    return html.Div("✅ Fichier XML chargé", style={'color': 'green'}), html.Div(sections)

@app.callback(
    Output('resultats', 'children'),
    Input({'type': 'cubf-checklist', 'index': dash.ALL}, 'value'),
    prevent_initial_call=True
)
def update_resultats(groups):
    df_xml = getattr(app.server, 'df_xml', pd.DataFrame())
    if df_xml.empty:
        return html.Div("⚠️ Aucune donnée XML chargée.", style={'color': 'orange'})
    codes = [c for g in groups for c in g]
    if not codes:
        return html.Div("ℹ️ Sélectionnez au moins un code.", style={'color': 'blue'})

    df_filtre = df_xml[df_xml["RL0105A"].isin(codes)]
    df_resume = df_filtre.groupby("RL0105A").agg(
        nb_batiments=("RL0105A", "count"),
        nb_logements=("RL0311A", "sum")
    ).reset_index().rename(columns={"RL0105A": "Code CUBF"})

    return html.Div([
        html.H2("📑 Résultats", style={'marginBottom': '15px'}),
        dash_table.DataTable(
            data=df_resume.to_dict('records'),
            columns=[{'name': c, 'id': c} for c in df_resume.columns],
            style_table={'overflowX': 'auto'},
            style_cell={'textAlign': 'center', 'padding': '8px'},
            style_header={'backgroundColor': '#f8f9fa', 'fontWeight': '600'}
        )
    ])

if __name__ == '__main__':
    app.run(debug=True, port=8050)
