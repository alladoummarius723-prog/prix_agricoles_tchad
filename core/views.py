import json
import datetime
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from .ml_service import predict_price, get_tendances, get_marches_liste, PRODUITS_VALIDES
from .models import Prediction


def home(request):
    """Page d'accueil avec les tendances de prix."""
    tendances = get_tendances(nb_mois=24)
    marches   = get_marches_liste()

    # Stats rapides pour les cartes du dashboard
    from .ml_service import get_dataset
    import numpy as np
    df = get_dataset()

    stats = []
    for prod in PRODUITS_VALIDES:
        sub = df[df['produit'] == prod]['prix_kg_fcfa']
        if not sub.empty:
            prix_recent = df[df['produit'] == prod].sort_values(
                'date_releve')['prix_kg_fcfa'].tail(3).mean()
            prix_precedent = df[df['produit'] == prod].sort_values(
                'date_releve')['prix_kg_fcfa'].tail(6).head(3).mean()
            variation = ((prix_recent - prix_precedent) / prix_precedent * 100
                         if prix_precedent > 0 else 0)
            stats.append({
                'produit':    prod,
                'prix_moyen': round(prix_recent, 0),
                'variation':  round(variation, 1),
                'tendance':   'hausse' if variation > 2 else ('baisse' if variation < -2 else 'stable'),
            })

    context = {
        'tendances_json': json.dumps(tendances),
        'marches':        marches,
        'produits':       PRODUITS_VALIDES,
        'stats':          stats,
        'nb_marches':     len(marches),
        'nb_predictions': Prediction.objects.count(),
    }
    return render(request, 'core/home.html', context)


def predict_view(request):
    """Page de prévision des prix."""
    marches  = get_marches_liste()
    resultat = None
    erreur   = None

    if request.method == 'POST':
        produit = request.POST.get('produit', '').lower()
        marche  = request.POST.get('marche', '')
        mois    = int(request.POST.get('mois', datetime.date.today().month))
        annee   = int(request.POST.get('annee', datetime.date.today().year))

        if produit not in PRODUITS_VALIDES:
            erreur = f"Produit '{produit}' non valide."
        elif not marche:
            erreur = "Veuillez sélectionner un marché."
        else:
            resultat = predict_price(produit, marche, mois, annee)

            if 'erreur' not in resultat:
                # Sauvegarder en base
                Prediction.objects.create(
                    produit     = produit,
                    marche      = marche,
                    mois        = mois,
                    annee       = annee,
                    prix_predit = resultat['prix_predit'],
                    prix_min    = resultat['prix_min'],
                    prix_max    = resultat['prix_max'],
                    tendance    = resultat['tendance'],
                    source      = 'web',
                )
                # Tendances pour le graphique de contexte
                tendances_prod = get_tendances(produit=produit, nb_mois=18)
                resultat['tendances_json'] = json.dumps(
                    tendances_prod.get(produit, {})
                )

    mois_noms = [
        'Janvier','Février','Mars','Avril','Mai','Juin',
        'Juillet','Août','Septembre','Octobre','Novembre','Décembre'
    ]

    context = {
        'marches':   marches,
        'produits':  PRODUITS_VALIDES,
        'resultat':  resultat,
        'erreur':    erreur,
        'mois_liste': [(i+1, m) for i, m in enumerate(mois_noms)],
        'annees':    list(range(datetime.date.today().year,
                               datetime.date.today().year + 3)),
        'mois_actuel': datetime.date.today().month,
        'annee_actuelle': datetime.date.today().year,
    }
    return render(request, 'core/predict.html', context)


def historique_view(request):
    """Historique des prédictions."""
    predictions = Prediction.objects.all()[:50]
    context = {'predictions': predictions}
    return render(request, 'core/historique.html', context)


def aide_sms_view(request):
    """Page d'aide pour l'utilisation par SMS."""
    marches = get_marches_liste()
    context = {
        'marches':  marches[:20],
        'produits': PRODUITS_VALIDES,
    }
    return render(request, 'core/aide_sms.html', context)
