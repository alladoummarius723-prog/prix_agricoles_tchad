from django.db import models


class Prediction(models.Model):
    """Historique des prédictions effectuées."""
    date_prediction  = models.DateTimeField(auto_now_add=True)
    produit          = models.CharField(max_length=50)
    marche           = models.CharField(max_length=100)
    mois             = models.IntegerField()
    annee            = models.IntegerField()
    prix_predit      = models.FloatField()
    prix_min         = models.FloatField()
    prix_max         = models.FloatField()
    tendance         = models.CharField(max_length=20)
    source           = models.CharField(
        max_length=20,
        choices=[('web','Web'),('sms','SMS'),('api','API')],
        default='web'
    )
    telephone        = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        ordering = ['-date_prediction']
        verbose_name = 'Prédiction'
        verbose_name_plural = 'Prédictions'

    def __str__(self):
        return f"{self.produit} - {self.marche} - {self.date_prediction.strftime('%d/%m/%Y')}"


class RequeteSMS(models.Model):
    """Log des requêtes SMS reçues."""
    date_reception = models.DateTimeField(auto_now_add=True)
    telephone      = models.CharField(max_length=20)
    message_recu   = models.TextField()
    message_envoye = models.TextField(blank=True)
    traite         = models.BooleanField(default=False)
    erreur         = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-date_reception']
        verbose_name = 'Requête SMS'
        verbose_name_plural = 'Requêtes SMS'

    def __str__(self):
        return f"{self.telephone} - {self.date_reception.strftime('%d/%m/%Y %H:%M')}"
