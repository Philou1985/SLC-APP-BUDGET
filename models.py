class Compte:
    LIQUIDITE_CHOICES = ["Non Renseigné", "Immédiate", "Court Terme (<1 an)", "Long Terme (>1 an)", "N/A"]
    CLASSE_ACTIF_CHOICES = ["Non Renseigné", "Monétaire", "Actions/Titres", "Obligations", "Immobilier", "Autre", "N/A"]
    TERME_PASSIF_CHOICES = ["Non Renseigné", "Court Terme", "Moyen Terme", "Long Terme", "N/A"]

    def __init__(self, id=None, nom=None, banque=None, type_compte=None, solde=None,
                 liquidite=None, terme_passif=None, classe_actif=None, 
                 suivi_budget=False, alerte_decouvert=False, solde_especes=0.0,
                 # --- AJOUT DES NOUVEAUX ARGUMENTS POUR LES RÈGLES DES COMPTES PASSIFS ---
                 jour_debit=None, jour_debut_periode=None, jour_fin_periode=None, compte_debit_associe=None):
        
        self.id = id
        self.nom = nom
        self.banque = banque
        self.type_compte = type_compte
        self.solde = float(solde) if solde is not None else 0.0
        self.suivi_budget = bool(suivi_budget)
        self.alerte_decouvert = bool(alerte_decouvert)
        self.solde_especes = float(solde_especes) if solde_especes is not None else 0.0
        self.lignes_portefeuille = []
        
        # --- AJOUT DE L'INITIALISATION DES NOUVEAUX ATTRIBUTS ---
        self.jour_debit = jour_debit
        self.jour_debut_periode = jour_debut_periode
        self.jour_fin_periode = jour_fin_periode
        self.compte_debit_associe = compte_debit_associe
        
        # Logique existante pour les attributs conditionnels
        self.liquidite = liquidite
        self.terme_passif = terme_passif
        self.classe_actif = classe_actif

        if self.type_compte == 'Actif':
            self.terme_passif = "N/A"
            if self.classe_actif is None or self.classe_actif not in self.CLASSE_ACTIF_CHOICES:
                self.classe_actif = "Autre"
            if self.liquidite is None or self.liquidite not in self.LIQUIDITE_CHOICES:
                self.liquidite = "Non Renseigné"
        
        elif self.type_compte == 'Passif':
            self.liquidite = "N/A"
            self.classe_actif = "N/A"
            if self.terme_passif is None or self.terme_passif not in self.TERME_PASSIF_CHOICES:
                self.terme_passif = "Non Renseigné"
        
        else:
            self.liquidite = "N/A"
            self.terme_passif = "N/A"
            self.classe_actif = "N/A"

    def to_dict(self):
        compte_dict = {
            'id': self.id, 'nom': self.nom, 'banque': self.banque, 'type_compte': self.type_compte,
            'solde': self.solde, 'liquidite': self.liquidite,
            'terme_passif': self.terme_passif, 'classe_actif': self.classe_actif,
            'suivi_budget': self.suivi_budget, 'alerte_decouvert': self.alerte_decouvert,
            'solde_especes': self.solde_especes,
            # On ajoute les nouveaux champs au dictionnaire
            'jour_debit': self.jour_debit,
            'jour_debut_periode': self.jour_debut_periode,
            'jour_fin_periode': self.jour_fin_periode,
            'compte_debit_associe': self.compte_debit_associe
        }
        if self.lignes_portefeuille:
            compte_dict['lignes_portefeuille'] = [ligne.to_dict() for ligne in self.lignes_portefeuille]
        return compte_dict

    def __str__(self):
        return f"{self.nom} ({self.banque}) - {self.type_compte}: {format_nombre_fr(self.solde)} €"
        
# Dans models.py
class LignePortefeuille:
    # --- DÉBUT MODIFICATION ---
    def __init__(self, nom, ticker, quantite, pru, id=None, compte_id=None, dernier_cours=0.0):
    # --- FIN MODIFICATION ---
        self.id = id
        self.compte_id = compte_id # Pour lier à un compte parent
        self.nom = nom           # Ex: "TotalEnergies SE"
        self.ticker = ticker     # Ex: "TTE.PA" (le symbole boursier)
        self.quantite = float(quantite)
        self.pru = float(pru)    # Prix de Revient Unitaire
        # --- DÉBUT MODIFICATION ---
        # Si aucun dernier_cours n'est fourni (ex: ancienne sauvegarde), on initialise avec le PRU
        self.dernier_cours = float(dernier_cours) if dernier_cours else self.pru
        # --- FIN MODIFICATION ---
            # --- MÉTHODE AJOUTÉE ---
    def to_dict(self):
        """Retourne une représentation de l'objet en dictionnaire."""
        return {
            'id': self.id,
            'compte_id': self.compte_id,
            'nom': self.nom,
            'ticker': self.ticker,
            'quantite': self.quantite,
            'pru': self.pru,
            'dernier_cours': self.dernier_cours
        }
    # --- FIN DE L'AJOUT ---