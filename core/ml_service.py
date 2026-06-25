"""
=============================================================
ml_service.py — Service de prédiction des prix (meilleurs modèles)
=============================================================
Meilleurs modèles par produit :
  - Mil    : Random Forest
  - Sorgho : Random Forest
  - Maïs   : XGBoost
  - Riz    : Random Forest
=============================================================
"""
import joblib
import pandas as pd
import numpy as np
from pathlib import Path
from django.conf import settings
import logging
import datetime

logger = logging.getLogger(__name__)

# ── Cache des modèles ──────────────────────────────────────
_models  = {}
_meta    = None
_dataset = None
_enc_marche  = None
_enc_produit = None

PRODUITS_VALIDES = ['mil', 'sorgho', 'mais', 'riz']
PRODUITS_FR = {
    'mil': 'Mil', 'sorgho': 'Sorgho',
    'mais': 'Maïs', 'riz': 'Riz'
}

# Meilleur modèle par produit (issu de la comparaison XGBoost vs RF)
MEILLEURS_MODELES = {
    'mil':    'rf',
    'sorgho': 'rf',
    'mais':   'xgb',
    'riz':    'rf',
}

# Performances de référence (MAE en FCFA/kg)
MAE_REF = {
    'mil': 25.2, 'sorgho': 23.9,
    'mais': 26.8, 'riz': 58.7,
}

# Features dans le bon ordre (identique à l'entraînement)
FEATURES = [
    'mois', 'mois_sin', 'mois_cos', 'saison_enc',
    'produit_enc', 'marche_enc',
    'prix_lag1', 'prix_lag2', 'prix_lag3',
    'prix_lag6', 'prix_lag12',
    'prix_moy3', 'prix_moy6', 'variation_pct',
    'prix_ndjamena', 'prix_ndj_lag1',
    'rendement_kg_ha',
    'indice_fao', 'taux_fcfa_usd',
    'distance_ndjamena_km',
]

# Données statiques intégrées directement
INDICE_FAO = {
    2003:97.7,  2004:104.9, 2005:104.3, 2006:107.2,
    2007:119.4, 2008:152.5, 2009:125.3, 2010:140.6,
    2011:167.9, 2012:160.9, 2013:151.0, 2014:136.4,
    2015:118.2, 2016:113.6, 2017:118.1, 2018:115.6,
    2019:114.1, 2020:116.8, 2021:141.3, 2022:143.7,
    2023:138.2, 2024:135.0, 2025:133.0, 2026:131.0,
}

TAUX_FCFA_USD = {
    2003:580.7, 2004:528.3, 2005:527.5, 2006:522.4,
    2007:479.3, 2008:447.8, 2009:472.2, 2010:495.3,
    2011:471.9, 2012:510.5, 2013:494.0, 2014:494.4,
    2015:591.4, 2016:592.7, 2017:580.3, 2018:555.7,
    2019:585.9, 2020:574.3, 2021:554.5, 2022:623.8,
    2023:606.6, 2024:600.0, 2025:598.0, 2026:596.0,
}

DISTANCES_KM = {
    "n'djamena":0,   'ndjamena':0,      'mandelia':45,
    'massakory':110, 'massaguet':70,    'mondo':95,
    'bol':237,       'nokou':312,       'mao':280,
    'moussoro':280,  'bokoro':290,      'bousso':320,
    'bongor':245,    'fianga':380,      'pala':430,
    'kélo':460,      'kelo':460,        'laï':390,
    'lai':390,       'moundou':497,     'benoye':510,
    'doba':520,      'bebedja':530,     'gore':580,
    'sarh':592,      'koumra':560,      'moissala':540,
    'kyabe':620,     'maro':610,        'haraze mangueigne':580,
    'bodo':590,      'beboto':575,      'krim krim':545,
    'peni':505,      'mongo':412,       'bitkine':430,
    'melfi':480,     'mangalme':500,    'biltine':760,
    'goz beida':840, 'aboudeia':650,    'am timan':710,
    'abdi':680,      'abeche':878,      'amdam':920,
    'am-zoer':950,   'guereda':980,     'iriba':1020,
    'faya':1060,     'ati':390,         'massenya':130,
    'gueledeng':280, 'oum hadjer':530,  'oumhadjer':530,
    'ngouri':200,    'mbaïbokoum':610,  'mbaïnamar':420,
    'yao':480,       'lere':490,        'national average':400,
    'massakory':110, 'bokoro':290,
}

SAISON_MAP = {
    1:'seche',  2:'seche',  3:'soudure', 4:'soudure',
    5:'soudure',6:'pluies', 7:'pluies',  8:'pluies',
    9:'pluies', 10:'seche', 11:'seche',  12:'seche'
}
SAISON_ENC = {'seche':0, 'soudure':1, 'pluies':2}


def _charger_modeles():
    """Charge les meilleurs modèles en mémoire."""
    global _models, _meta, _enc_marche, _enc_produit
    models_dir = settings.MODELS_DIR

    try:
        _meta        = joblib.load(models_dir / 'metadata.pkl')
        _enc_marche  = joblib.load(models_dir / 'marche_encoding.pkl')
        _enc_produit = joblib.load(models_dir / 'produit_encoding.pkl')

        for prod in PRODUITS_VALIDES:
            path = models_dir / f'best_{prod}.pkl'
            if path.exists():
                _models[prod] = joblib.load(path)
                type_modele = MEILLEURS_MODELES[prod].upper()
                logger.info(f"Modèle chargé : {prod} ({type_modele})")
            else:
                logger.warning(f"Modèle manquant : best_{prod}.pkl")

        logger.info(f"{len(_models)} modèles chargés")
    except Exception as e:
        logger.error(f"Erreur chargement modèles : {e}")


def _charger_dataset():
    """Charge le dataset historique."""
    global _dataset
    try:
        _dataset = pd.read_csv(
            settings.DATASET_PATH,
            parse_dates=['date_releve']
        )
        logger.info(f"Dataset chargé : {len(_dataset):,} lignes")
    except Exception as e:
        logger.error(f"Erreur chargement dataset : {e}")


def get_dataset():
    if _dataset is None:
        _charger_dataset()
    return _dataset


def get_models():
    if not _models:
        _charger_modeles()
    return _models


def _get_enc(valeur: str, enc_df, col_nom: str, col_enc: str) -> int:
    """Retourne le code encodé d'une valeur."""
    if enc_df is None:
        _charger_modeles()
    match = enc_df[enc_df[col_nom].str.lower() == valeur.lower()]
    if match.empty:
        match = enc_df[
            enc_df[col_nom].str.lower().str.contains(
                valeur.lower(), na=False
            )
        ]
    return int(match[col_enc].iloc[0]) if not match.empty else 0


def predict_price(produit: str, marche: str,
                  mois: int = None, annee: int = None) -> dict:
    """
    Prédit le prix d'une céréale sur un marché pour un mois donné.

    Paramètres:
        produit : 'mil' | 'sorgho' | 'mais' | 'riz'
        marche  : nom du marché (ex: 'Abeche')
        mois    : mois cible (1-12), défaut = mois actuel
        annee   : année cible, défaut = année actuelle

    Retourne:
        dict avec prix prédit, tendance, intervalle de confiance
    """
    models = get_models()
    df     = get_dataset()

    if produit not in models:
        return {'erreur': f"Produit '{produit}' non disponible"}

    now   = datetime.date.today()
    mois  = mois  or now.month
    annee = annee or now.year

    # ── Récupérer l'historique du marché × produit ─────────
    df_prod = df[
        (df['produit'] == produit) &
        (df['marche'].str.lower() == marche.lower())
    ].sort_values('date_releve')

    marche_fallback = df_prod.empty
    if marche_fallback:
        df_prod = df[df['produit'] == produit].sort_values('date_releve')

    # Prix récents pour les lags
    prix_recents = df_prod['prix_kg_fcfa'].tail(12).values
    if len(prix_recents) < 12:
        med = float(df[df['produit'] == produit]['prix_kg_fcfa'].median())
        prix_recents = np.pad(
            prix_recents,
            (12 - len(prix_recents), 0),
            constant_values=med
        )

    lag1  = float(prix_recents[-1])
    lag2  = float(prix_recents[-2])
    lag3  = float(prix_recents[-3])
    lag6  = float(prix_recents[-6])
    lag12 = float(prix_recents[-12])
    moy3  = float(np.mean(prix_recents[-3:]))
    moy6  = float(np.mean(prix_recents[-6:]))
    var   = ((lag1 - lag2) / lag2 * 100) if lag2 > 0 else 0

    # ── Prix N'Djamena ─────────────────────────────────────
    df_ndj = df[
        (df['produit'] == produit) &
        (df['marche'].str.lower().isin(["n'djamena","ndjamena"]))
    ].sort_values('date_releve')

    if not df_ndj.empty:
        prix_ndj      = float(df_ndj['prix_ndjamena'].iloc[-1])
        prix_ndj_lag1 = float(df_ndj['prix_ndjamena'].iloc[-2]) if len(df_ndj) > 1 else prix_ndj
    else:
        prix_ndj      = lag1
        prix_ndj_lag1 = lag2

    # ── Rendement ──────────────────────────────────────────
    rdt_rec = df[df['produit'] == produit]['rendement_kg_ha'].tail(1)
    rendement = float(rdt_rec.iloc[0]) if not rdt_rec.empty else 400.0

    # ── Données économiques ────────────────────────────────
    indice_fao   = INDICE_FAO.get(annee, 135.0)
    taux_change  = TAUX_FCFA_USD.get(annee, 600.0)
    distance_km  = DISTANCES_KM.get(marche.lower(), 400)

    # ── Encodages ──────────────────────────────────────────
    saison      = SAISON_MAP[mois]
    saison_enc  = SAISON_ENC[saison]
    produit_enc = _get_enc(produit, _enc_produit, 'produit', 'produit_enc')
    marche_enc  = _get_enc(marche,  _enc_marche,  'marche',  'marche_enc')

    # ── Vecteur de features ────────────────────────────────
    X = pd.DataFrame([{
        'mois':                  mois,
        'mois_sin':              np.sin(2 * np.pi * mois / 12),
        'mois_cos':              np.cos(2 * np.pi * mois / 12),
        'saison_enc':            saison_enc,
        'produit_enc':           produit_enc,
        'marche_enc':            marche_enc,
        'prix_lag1':             lag1,
        'prix_lag2':             lag2,
        'prix_lag3':             lag3,
        'prix_lag6':             lag6,
        'prix_lag12':            lag12,
        'prix_moy3':             moy3,
        'prix_moy6':             moy6,
        'variation_pct':         var,
        'prix_ndjamena':         prix_ndj,
        'prix_ndj_lag1':         prix_ndj_lag1,
        'rendement_kg_ha':       rendement,
        'indice_fao':            indice_fao,
        'taux_fcfa_usd':         taux_change,
        'distance_ndjamena_km':  distance_km,
    }])[FEATURES]

    # ── Prédiction ─────────────────────────────────────────
    model       = models[produit]
    prix_predit = float(model.predict(X)[0])

    # Tendance vs mois précédent
    variation   = ((prix_predit - lag1) / lag1 * 100) if lag1 > 0 else 0
    if variation > 3:
        tendance, fleche = 'hausse', '↑'
    elif variation < -3:
        tendance, fleche = 'baisse', '↓'
    else:
        tendance, fleche = 'stable', '→'

    # Intervalle de confiance basé sur la MAE de référence
    mae = MAE_REF.get(produit, 30)

    # Fiabilité selon le nombre d'observations du marché
    nb_obs = len(df_prod)
    if nb_obs > 200:
        fiabilite = 'Bonne'
    elif nb_obs > 50:
        fiabilite = 'Modérée'
    else:
        fiabilite = 'Faible'

    return {
        'produit':       produit,
        'produit_fr':    PRODUITS_FR[produit],
        'marche':        marche,
        'marche_note':   '(moyenne nationale utilisée)' if marche_fallback else '',
        'mois':          mois,
        'annee':         annee,
        'saison':        saison,
        'prix_predit':   round(prix_predit, 1),
        'prix_min':      round(prix_predit - mae, 1),
        'prix_max':      round(prix_predit + mae, 1),
        'prix_actuel':   round(lag1, 1),
        'variation_pct': round(variation, 1),
        'tendance':      tendance,
        'fleche':        fleche,
        'unite':         'FCFA/kg',
        'fiabilite':     fiabilite,
        'modele_type':   MEILLEURS_MODELES[produit].upper(),
        'mae_ref':       mae,
    }


def get_tendances(produit: str = None, marche: str = None,
                  nb_mois: int = 24) -> dict:
    """Retourne tendances historiques + prévisions futures."""
    df      = get_dataset()
    models  = get_models()

    df_hist = df.copy()
    if produit:
        df_hist = df_hist[df_hist['produit'] == produit]
    if marche:
        df_hist = df_hist[df_hist['marche'].str.lower() == marche.lower()]

    tendances = (
        df_hist.groupby(['date_releve','produit'])['prix_kg_fcfa']
        .median().reset_index().sort_values('date_releve')
    )

    derniere_date = tendances['date_releve'].max()
    date_debut    = derniere_date - pd.DateOffset(months=nb_mois)
    tendances     = tendances[tendances['date_releve'] >= date_debut]

    aujourd_hui   = pd.Timestamp(datetime.date.today())
    date_fin_prev = aujourd_hui + pd.DateOffset(months=12)

    couleurs = {
        'mil':'#7F77DD', 'sorgho':'#1D9E75',
        'mais':'#EF9F27', 'riz':'#378ADD'
    }

    result = {}
    produits_a_traiter = [produit] if produit else PRODUITS_VALIDES

    for prod in produits_a_traiter:
        sub = tendances[tendances['produit'] == prod].copy()
        if sub.empty:
            continue

        labels_hist = sub['date_releve'].dt.strftime('%Y-%m').tolist()
        prix_hist   = sub['prix_kg_fcfa'].round(1).tolist()

        labels_prev = []
        prix_prev_vals = []

        if prod in models:
            prix_rolling = list(sub['prix_kg_fcfa'].tail(12).values)
            if len(prix_rolling) < 12:
                med = float(df[df['produit']==prod]['prix_kg_fcfa'].median())
                prix_rolling = [med]*(12-len(prix_rolling)) + prix_rolling

            rdt = float(df[df['produit']==prod]['rendement_kg_ha'].tail(1).iloc[0]) \
                  if not df[df['produit']==prod].empty else 400.0
            ndj = float(df[df['produit']==prod]['prix_ndjamena'].tail(1).iloc[0]) \
                  if not df[df['produit']==prod].empty else prix_rolling[-1]

            date_courante = derniere_date + pd.DateOffset(months=1)
            ndj_rolling   = [ndj, ndj]

            while date_courante <= date_fin_prev:
                m    = date_courante.month
                annee = date_courante.year
                lag1  = prix_rolling[-1]
                lag2  = prix_rolling[-2]

                X = pd.DataFrame([{
                    'mois':                 m,
                    'mois_sin':             np.sin(2*np.pi*m/12),
                    'mois_cos':             np.cos(2*np.pi*m/12),
                    'saison_enc':           SAISON_ENC[SAISON_MAP[m]],
                    'produit_enc':          _get_enc(prod, _enc_produit, 'produit', 'produit_enc'),
                    'marche_enc':           0,
                    'prix_lag1':            lag1,
                    'prix_lag2':            lag2,
                    'prix_lag3':            prix_rolling[-3],
                    'prix_lag6':            prix_rolling[-6],
                    'prix_lag12':           prix_rolling[-12],
                    'prix_moy3':            np.mean(prix_rolling[-3:]),
                    'prix_moy6':            np.mean(prix_rolling[-6:]),
                    'variation_pct':        ((lag1-lag2)/lag2*100) if lag2>0 else 0,
                    'prix_ndjamena':        ndj_rolling[-1],
                    'prix_ndj_lag1':        ndj_rolling[-2],
                    'rendement_kg_ha':      rdt,
                    'indice_fao':           INDICE_FAO.get(annee, 135.0),
                    'taux_fcfa_usd':        TAUX_FCFA_USD.get(annee, 600.0),
                    'distance_ndjamena_km': 400,
                }])[FEATURES]

                prix_p = float(models[prod].predict(X)[0])
                labels_prev.append(date_courante.strftime('%Y-%m'))
                prix_prev_vals.append(round(prix_p, 1))
                prix_rolling.append(prix_p)
                ndj_rolling.append(prix_p)
                if len(prix_rolling) > 24: prix_rolling.pop(0)
                if len(ndj_rolling)  > 24: ndj_rolling.pop(0)
                date_courante += pd.DateOffset(months=1)

        # Aligner les deux séries
        dernier_prix = prix_hist[-1] if prix_hist else None
        prev_aligne  = [None]*len(labels_hist) + prix_prev_vals
        if labels_prev and dernier_prix is not None:
            prev_aligne[len(labels_hist)-1] = dernier_prix

        result[prod] = {
            'labels':      labels_hist + labels_prev,
            'labels_prev': labels_prev,
            'prix':        prix_hist + [None]*len(labels_prev),
            'previsions':  prev_aligne,
            'couleur':     couleurs[prod],
            'label_fr':    PRODUITS_FR[prod],
        }

    return result


def get_marches_liste() -> list:
    df = get_dataset()
    return sorted(df['marche'].unique().tolist())
