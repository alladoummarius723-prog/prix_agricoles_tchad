"""
=============================================================
bot/views.py — Webhook SMS Africa's Talking
=============================================================
Flux :
  1. Africa's Talking reçoit le SMS de l'agriculteur
  2. Envoie un POST vers /bot/sms/ (ce webhook)
  3. On parse le message, on appelle le modèle ML
  4. On envoie la réponse par SMS via Africa's Talking API
=============================================================
"""
import re
import logging
import africastalking
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from core.ml_service import predict_price, get_marches_liste, PRODUITS_VALIDES
from core.models import Prediction, RequeteSMS

logger = logging.getLogger(__name__)

# ── Initialisation Africa's Talking ───────────────────────
africastalking.initialize(
    username=settings.AFRICASTALKING_USERNAME,
    api_key=settings.AFRICASTALKING_API_KEY
)
sms_service = africastalking.SMS

# ── Synonymes de produits (gère les variantes francophones) ─
SYNONYMES_PRODUITS = {
    'mil':    ['mil', 'millet', 'petit mil'],
    'sorgho': ['sorgho', 'sorghu', 'gros mil'],
    'mais':   ['mais', 'maïs', 'maize', 'maïz'],
    'riz':    ['riz', 'rice'],
}

MOIS_NOMS = {
    'janvier':1,'février':2,'mars':3,'avril':4,
    'mai':5,'juin':6,'juillet':7,'août':8,
    'septembre':9,'octobre':10,'novembre':11,'décembre':12
}


def parser_message(message: str) -> dict:
    """
    Parse le SMS de l'agriculteur.

    Formats acceptés :
      PRIX MIL ABECHE
      PRIX SORGHO MOUNDOU MARS
      AIDE
      MARCHES

    Retourne:
      dict avec 'action', 'produit', 'marche', 'mois' ou 'erreur'
    """
    msg = message.strip().upper()
    msg_lower = message.strip().lower()

    # ── Commandes spéciales ────────────────────────────────
    if msg in ['AIDE', 'HELP', '?']:
        return {'action': 'aide'}

    if msg in ['MARCHES', 'MARCHÉS', 'LISTE']:
        return {'action': 'marches'}

    if msg in ['PRODUITS', 'CEREALES', 'CÉRÉALES']:
        return {'action': 'produits'}

    # ── Commande PRIX ──────────────────────────────────────
    # Format : PRIX <produit> <marché> [mois]
    if not msg.startswith('PRIX'):
        return {'erreur': 'format'}

    # Identifier le produit
    produit_trouve = None
    for prod, synonymes in SYNONYMES_PRODUITS.items():
        for syn in synonymes:
            if syn in msg_lower:
                produit_trouve = prod
                break
        if produit_trouve:
            break

    if not produit_trouve:
        return {'erreur': 'produit_inconnu'}

    # Identifier le marché
    marches_dispo = get_marches_liste()
    marche_trouve = None
    for marche in marches_dispo:
        if marche.lower() in msg_lower:
            marche_trouve = marche
            break

    if not marche_trouve:
        # Essai avec correspondance partielle
        mots = msg_lower.replace('prix', '').replace(produit_trouve, '').split()
        for mot in mots:
            if len(mot) > 3:
                for marche in marches_dispo:
                    if mot in marche.lower():
                        marche_trouve = marche
                        break
            if marche_trouve:
                break

    if not marche_trouve:
        return {'erreur': 'marche_inconnu', 'produit': produit_trouve}

    # Identifier le mois (optionnel)
    mois_trouve = None
    for nom_mois, num_mois in MOIS_NOMS.items():
        if nom_mois in msg_lower:
            mois_trouve = num_mois
            break

    return {
        'action':  'prix',
        'produit': produit_trouve,
        'marche':  marche_trouve,
        'mois':    mois_trouve,
    }


def formater_reponse(resultat: dict) -> str:
    """
    Formate la réponse SMS (max 160 caractères).
    """
    if 'erreur' in resultat:
        return resultat['erreur']

    prod   = resultat['produit_fr']
    marche = resultat['marche']
    prix   = resultat['prix_predit']
    fleche = resultat['fleche']
    var    = abs(resultat['variation_pct'])
    saison = resultat['saison']

    saison_msg = {
        'soudure': 'Période soudure',
        'pluies':  'Saison pluies',
        'seche':   'Saison sèche'
    }.get(saison, '')

    reponse = (
        f"{prod} - {marche}\n"
        f"Prix prévu: {prix:.0f} FCFA/kg\n"
        f"Tendance: {fleche} {var:.0f}%\n"
        f"{saison_msg}"
    )
    return reponse[:320]  # SMS long (2 SMS max)


def generer_aide() -> str:
    return (
        "AIDE - Prix agricoles Tchad\n"
        "Envoyez: PRIX [produit] [marché]\n"
        "Produits: MIL SORGHO RIZ MAIS\n"
        "Ex: PRIX MIL ABECHE\n"
        "Pour la liste: envoyez MARCHES"
    )


def generer_liste_marches() -> str:
    marches = get_marches_liste()[:15]
    return "Marchés disponibles:\n" + ", ".join(marches)


@csrf_exempt
@require_POST
def sms_webhook(request):
    """
    Webhook reçu depuis Africa's Talking.
    Africa's Talking envoie un POST avec :
      - from     : numéro de l'expéditeur
      - text     : contenu du SMS
      - to       : votre numéro court
      - date     : date de réception
    """
    telephone = request.POST.get('from', '')
    message   = request.POST.get('text', '').strip()
    reponse   = ''

    logger.info(f"SMS reçu de {telephone} : {message}")

    # Enregistrer la requête
    log_sms = RequeteSMS.objects.create(
        telephone    = telephone,
        message_recu = message,
    )

    try:
        parsed = parser_message(message)

        if parsed.get('action') == 'aide':
            reponse = generer_aide()

        elif parsed.get('action') == 'marches':
            reponse = generer_liste_marches()

        elif parsed.get('action') == 'produits':
            reponse = "Produits disponibles:\nMIL, SORGHO, RIZ, MAIS\nEx: PRIX SORGHO MOUNDOU"

        elif parsed.get('action') == 'prix':
            resultat = predict_price(
                produit = parsed['produit'],
                marche  = parsed['marche'],
                mois    = parsed.get('mois'),
            )
            reponse = formater_reponse(resultat)

            # Sauvegarder la prédiction
            if 'erreur' not in resultat:
                Prediction.objects.create(
                    produit     = parsed['produit'],
                    marche      = parsed['marche'],
                    mois        = resultat['mois'],
                    annee       = resultat['annee'],
                    prix_predit = resultat['prix_predit'],
                    prix_min    = resultat['prix_min'],
                    prix_max    = resultat['prix_max'],
                    tendance    = resultat['tendance'],
                    source      = 'sms',
                    telephone   = telephone,
                )

        elif parsed.get('erreur') == 'format':
            reponse = (
                "Format incorrect.\n"
                "Envoyez: PRIX [produit] [marché]\n"
                "Ex: PRIX MIL ABECHE\n"
                "Ou: AIDE"
            )
        elif parsed.get('erreur') == 'produit_inconnu':
            reponse = (
                "Produit non reconnu.\n"
                "Produits valides: MIL SORGHO RIZ MAIS\n"
                "Ex: PRIX SORGHO MOUNDOU"
            )
        elif parsed.get('erreur') == 'marche_inconnu':
            reponse = (
                f"Marché non trouvé pour {parsed.get('produit','')}\n"
                "Envoyez MARCHES pour la liste"
            )

        # Envoyer le SMS de réponse via Africa's Talking
        sms_service.send(
            message    = reponse,
            recipients = [telephone],
            sender_id  = settings.AFRICASTALKING_SHORTCODE,
        )

        log_sms.message_envoye = reponse
        log_sms.traite         = True
        log_sms.save()

    except Exception as e:
        logger.error(f"Erreur traitement SMS : {e}")
        log_sms.erreur = str(e)
        log_sms.save()

        try:
            sms_service.send(
                message    = "Service temporairement indisponible. Réessayez.",
                recipients = [telephone],
            )
        except:
            pass

    return HttpResponse("OK", status=200)
