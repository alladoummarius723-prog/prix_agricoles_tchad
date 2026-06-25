"""api/views.py — API REST pour accès externe aux prédictions."""
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from core.ml_service import predict_price, get_tendances, get_marches_liste, PRODUITS_VALIDES


@require_GET
def api_predict(request):
    produit = request.GET.get('produit', '').lower()
    marche  = request.GET.get('marche', '')
    mois    = request.GET.get('mois')
    mois    = int(mois) if mois else None

    if produit not in PRODUITS_VALIDES:
        return JsonResponse({'erreur': f'Produit invalide. Valides: {PRODUITS_VALIDES}'}, status=400)
    if not marche:
        return JsonResponse({'erreur': 'Paramètre marche requis'}, status=400)

    resultat = predict_price(produit, marche, mois)
    return JsonResponse(resultat)


@require_GET
def api_tendances(request):
    produit = request.GET.get('produit')
    marche  = request.GET.get('marche')
    nb_mois = int(request.GET.get('nb_mois', 24))
    tendances = get_tendances(produit=produit, marche=marche, nb_mois=nb_mois)
    return JsonResponse(tendances)


@require_GET
def api_marches(request):
    return JsonResponse({'marches': get_marches_liste()})


@require_GET
def api_produits(request):
    return JsonResponse({'produits': PRODUITS_VALIDES})
