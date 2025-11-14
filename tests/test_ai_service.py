# -*- coding: utf-8 -*-
import unittest
import sys
import os

# Astuce pour permettre à ce fichier de test d'importer depuis les autres dossiers
# On ajoute le dossier parent (la racine du projet) au chemin de Python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai_service import CategorizationAI

class TestCategorizationAI(unittest.TestCase):

    def test_suggestion_simple(self):
        # 1. PRÉPARATION (Arrange)
        ai = CategorizationAI()
        
        # On crée des fausses transactions pour l'entraînement
        fausses_transactions = [
            {'description': 'Achat Carrefour et Leclerc', 'categorie': 'Courses'},
            {'description': 'Facture essence Total Energies', 'categorie': 'Carburant'},
            {'description': 'Abonnement Netflix', 'categorie': 'Abonnements'}
        ]
        
        ai.train(fausses_transactions)

        # 2. ACTION (Act)
        # On demande une suggestion pour une nouvelle description
        suggestion = ai.suggest_category("Mon prélèvement mensuel Netflix")

        # 3. VÉRIFICATION (Assert)
        # On vérifie que la suggestion est bien celle attendue
        self.assertEqual(suggestion, "Abonnements")

    def test_suggestion_mot_cle_partage(self):
        # Un autre test pour vérifier un cas plus complexe
        ai = CategorizationAI()
        fausses_transactions = [
            {'description': 'Paiement Loyer Agence du Centre', 'categorie': 'Loyer'},
            {'description': 'Paiement cantine centre aéré', 'categorie': 'Enfants'}
        ]
        ai.train(fausses_transactions)

        # "centre" est dans les deux, mais "loyer" est plus spécifique
        suggestion = ai.suggest_category("Virement pour le loyer")

        self.assertEqual(suggestion, "Loyer")

    def test_aucune_suggestion(self):
        # Test pour vérifier qu'il ne suggère rien s'il ne sait pas
        ai = CategorizationAI()
        fausses_transactions = [{'description': 'Courses', 'categorie': 'Alimentation'}]
        ai.train(fausses_transactions)

        suggestion = ai.suggest_category("Un achat totalement nouveau")

        self.assertIsNone(suggestion)

if __name__ == '__main__':
    unittest.main()