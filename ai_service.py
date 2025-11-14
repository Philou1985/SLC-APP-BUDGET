# Fichier: ai_service.py
# -*- coding: utf-8 -*-

import re
from collections import defaultdict
from datetime import datetime
import statistics

STOP_WORDS = set([
    'achat', 'achats', 'a', 'au', 'aux', 'avec', 'ce', 'ces', 'dans', 'de', 'des', 'du',
    'elle', 'en', 'et', 'eux', 'il', 'je', 'la', 'le', 'les', 'leur', 'lui', 'ma',
    'mais', 'me', 'même', 'mes', 'moi', 'mon', 'ne', 'nos', 'notre', 'nous',
    'on', 'ou', 'par', 'pas', 'pour', 'qu', 'que', 'qui', 'sa', 'se', 'ses',
    'son', 'sur', 'ta', 'te', 'tes', 'toi', 'ton', 'tu', 'un', 'une', 'vos',
    'votre', 'vous', 'c', 'd', 'j', 'l', 'm', 'n', 's', 't', 'y', 'facture', 'paiement',
    'prelevement', 'carte', 'cb', 'vir', 'virement', 'debit'
])

MOIS_FRANCAIS = [
    "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
]

class CategorizationAI:
    def __init__(self):
        self.keyword_map = {}
        print("INFO: Service IA de catégorisation initialisé.")

    # ... (les méthodes _get_keywords_from_description, train, suggest_category, detect_recurring_transactions ne changent pas)
    def _get_keywords_from_description(self, description):
        description_cleaned = re.sub(r'[^\w\s]', '', description.lower())
        words = description_cleaned.split()
        return [word for word in words if word not in STOP_WORDS and not word.isdigit()]
    def train(self, transactions):
        keyword_to_category = {}
        for trans in transactions:
            categorie = trans.get('categorie')
            description = trans.get('description')
            if categorie and description and categorie != "(Virement)":
                keywords = self._get_keywords_from_description(description)
                for keyword in keywords:
                    keyword_to_category[keyword] = categorie
        self.keyword_map = keyword_to_category
    def suggest_category(self, description):
        if not description: return None
        keywords = self._get_keywords_from_description(description)
        for keyword in keywords:
            if keyword in self.keyword_map:
                return self.keyword_map[keyword]
        return None
    def detect_recurring_transactions(self, transactions, existing_recurring):
        manual_transactions = [t for t in transactions if t.get('origine') != 'recurrente']
        groups = defaultdict(list)
        for trans in manual_transactions:
            keywords = self._get_keywords_from_description(trans.get('description', ''))
            if keywords: groups[keywords[0]].append(trans)
        suggestions = []
        for group_key, trans_list in groups.items():
            if len(trans_list) < 3: continue
            if any(group_key in str(rule.get('description','')).lower() for rule in existing_recurring): continue
            montants = [t['montant'] for t in trans_list]
            avg_montant = sum(montants) / len(montants)
            variance = sum((m - avg_montant) ** 2 for m in montants) / len(montants)
            if variance > 2: continue
            jours = [datetime.strptime(t['date'], "%Y-%m-%d").day for t in trans_list]
            jour_median = sorted(jours)[len(jours) // 2]
            jours_coherents = sum(1 for j in jours if abs(j - jour_median) <= 3)
            if (jours_coherents / len(jours)) < 0.7: continue
            suggestions.append({'description': trans_list[0]['description'], 'montant': avg_montant, 'jour_du_mois': jour_median, 'categorie': trans_list[0]['categorie'], 'type': 'Dépense' if avg_montant < 0 else 'Revenu'})
        return suggestions

    def analyser_budget_annuel(self, data_by_cat, budget_type):
        """Analyse les données et retourne une liste de dictionnaires d'anomalies."""
        anomalies = []
        SENSIBILITE = 1.5

        for cat, monthly_data in data_by_cat.items():
            valeurs = [v for v in monthly_data.values() if v > 0]
            if len(valeurs) < 4: continue
            moyenne = statistics.mean(valeurs)
            ecart_type = statistics.stdev(valeurs) if len(valeurs) > 1 else 0
            if ecart_type == 0: continue
            seuil = moyenne + (SENSIBILITE * ecart_type)

            for month_num, valeur in monthly_data.items():
                if valeur > seuil:
                    nom_mois = MOIS_FRANCAIS[month_num]
                    type_str = "Pic de dépenses" if budget_type == "Dépenses" else "Pic de recettes"
                    anomalie_text = f"-> {type_str} pour '{cat}' en {nom_mois} : {valeur:,.2f}€ (moyenne : {moyenne:,.2f}€)".replace(",", " ")
                    # On retourne maintenant un dictionnaire avec le texte ET la catégorie
                    anomalies.append({'text': anomalie_text, 'categorie': cat})
        
        return sorted(anomalies, key=lambda x: x['text'])


    # --- NOUVELLE MÉTHODE POUR LES TENDANCES ---
    def analyser_tendances(self, data_by_cat):
        """Analyse les données pour trouver des tendances à la hausse ou à la baisse."""
        tendances = []
        for cat, monthly_data in data_by_cat.items():
            # On crée une liste de points (mois, valeur) pour les mois avec des données
            points = [(m, v) for m, v in monthly_data.items() if v > 0]
            
            # Il faut au moins 6 points pour qu'une tendance soit significative
            if len(points) < 6:
                continue

            # Calcul de la régression linéaire simple (pente de la droite de tendance)
            n = len(points)
            sum_x = sum(p[0] for p in points)
            sum_y = sum(p[1] for p in points)
            sum_xy = sum(p[0] * p[1] for p in points)
            sum_x_sq = sum(p[0]**2 for p in points)
            
            try:
                pente = (n * sum_xy - sum_x * sum_y) / (n * sum_x_sq - sum_x**2)
            except ZeroDivisionError:
                continue

            # On interprète la pente
            variation_annuelle = pente * 12
            # Seuil de significativité : si la variation sur l'année est > 10% de la moyenne
            seuil_significatif = sum_y / n * 0.1 

            if variation_annuelle > seuil_significatif:
                tendance_str = f"-> Tendance '{cat}' : En hausse (environ +{pente:,.2f} €/mois)".replace(",", " ")
                tendances.append(tendance_str)
            elif variation_annuelle < -seuil_significatif:
                tendance_str = f"-> Tendance '{cat}' : En baisse (environ {pente:,.2f} €/mois)".replace(",", " ")
                tendances.append(tendance_str)

        return sorted(tendances)