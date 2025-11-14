# -*- coding: utf-8 -*-

import sqlite3
import json
import os

print("--- Début du script de migration de JSON vers SQLite ---")

# --- Configuration des chemins ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PATRIMOINE_JSON_FILE = os.path.join(BASE_DIR, "patrimoine_data.json")
BUDGET_JSON_FILE = os.path.join(BASE_DIR, "budget_data.json")
DB_FILE = os.path.join(BASE_DIR, "budget.db")

# --- Suppression de l'ancienne base de données si elle existe ---
if os.path.exists(DB_FILE):
    print(f"Suppression de l'ancienne base de données '{DB_FILE}'...")
    os.remove(DB_FILE)

# --- Connexion à la base de données (la crée si elle n'existe pas) ---
try:
    con = sqlite3.connect(DB_FILE)
    cursor = con.cursor()
    print("Base de données SQLite créée avec succès.")

    # --- Création des tables ---
    print("Création des tables...")

    # Table pour les comptes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comptes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL,
        banque TEXT,
        type_compte TEXT,
        solde REAL,
        liquidite TEXT,
        terme_passif TEXT,
        classe_actif TEXT,
        suivi_budget INTEGER,
        alerte_decouvert INTEGER
    )
    """)

    # Table pour l'historique du patrimoine (simplifié, on pourrait normaliser plus)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historique_patrimoine (
        date TEXT PRIMARY KEY,
        patrimoine_net REAL,
        total_actifs REAL,
        total_passifs_magnitude REAL,
        details_json TEXT
    )
    """)

    # Table pour les transactions du budget
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        date TEXT,
        description TEXT,
        montant REAL,
        categorie TEXT,
        compte_affecte TEXT,
        pointe INTEGER,
        virement_id TEXT,
        origine TEXT,
        id_recurrence TEXT
    )
    """)

    # Table pour les catégories prévues du budget
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categories_prevues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cle_mois_annee TEXT NOT NULL,
        categorie TEXT NOT NULL,
        prevu REAL,
        type TEXT,
        compte_prevu TEXT,
        soldee INTEGER
    )
    """)
    
    # Table pour les transactions récurrentes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions_recurrentes (
        id TEXT PRIMARY KEY,
        active INTEGER,
        jour_du_mois INTEGER,
        jour_echeance TEXT,
        description TEXT,
        categorie TEXT,
        montant REAL,
        compte_affecte TEXT,
        type TEXT,
        source TEXT,
        destination TEXT,
        date_debut TEXT,
        date_fin TEXT,
        periodicite TEXT
    )
    """)

    # Table pour les modèles de budget
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS budget_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL UNIQUE
    )
    """)

    # Table pour les catégories de chaque modèle
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS budget_template_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id INTEGER,
        categorie TEXT,
        type TEXT,
        prevu REAL,
        compte_prevu TEXT,
        FOREIGN KEY (template_id) REFERENCES budget_templates (id)
    )
    """)

    print("Toutes les tables ont été créées.")
    con.commit()

    # --- Migration des données du patrimoine ---
    print("\nMigration des données de 'patrimoine_data.json'...")
    try:
        with open(PATRIMOINE_JSON_FILE, 'r', encoding='utf-8') as f:
            patrimoine_data = json.load(f)

        # Migration des comptes
        comptes = patrimoine_data.get('comptes', [])
        for compte in comptes:
            cursor.execute("""
                INSERT INTO comptes (nom, banque, type_compte, solde, liquidite, terme_passif, classe_actif, suivi_budget, alerte_decouvert)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                compte.get('nom'), compte.get('banque'), compte.get('type_compte'), compte.get('solde'),
                compte.get('liquidite'), compte.get('terme_passif'), compte.get('classe_actif'),
                int(compte.get('suivi_budget', False)), int(compte.get('alerte_decouvert', False))
            ))
        print(f"{len(comptes)} comptes migrés.")

        # Migration de l'historique
        historique = patrimoine_data.get('historique', [])
        for snap in historique:
            cursor.execute("""
                INSERT INTO historique_patrimoine (date, patrimoine_net, total_actifs, total_passifs_magnitude, details_json)
                VALUES (?, ?, ?, ?, ?)
            """, (
                snap.get('date'), snap.get('patrimoine_net'), snap.get('total_actifs'),
                snap.get('total_passifs_magnitude'), json.dumps({
                    'repartition_actifs_par_classe': snap.get('repartition_actifs_par_classe', {}),
                    'soldes_comptes': snap.get('soldes_comptes', {})
                })
            ))
        print(f"{len(historique)} entrées d'historique migrées.")
        
        con.commit()
        print("Migration du patrimoine terminée avec succès.")

    except FileNotFoundError:
        print("AVERTISSEMENT: Fichier 'patrimoine_data.json' non trouvé. Aucune donnée de patrimoine à migrer.")
    except Exception as e:
        print(f"ERREUR lors de la migration du patrimoine: {e}")
        con.rollback()

    # --- Migration des données du budget ---
    print("\nMigration des données de 'budget_data.json'...")
    try:
        with open(BUDGET_JSON_FILE, 'r', encoding='utf-8') as f:
            budget_data = json.load(f)
        
        # Migration des transactions, catégories prévues
        total_transactions = 0
        total_categories_prevues = 0
        for cle, data in budget_data.items():
            if not isinstance(data, dict): continue

            # Catégories prévues
            categories = data.get('categories_prevues', [])
            for cat in categories:
                cursor.execute("""
                    INSERT INTO categories_prevues (cle_mois_annee, categorie, prevu, type, compte_prevu, soldee)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (cle, cat.get('categorie'), cat.get('prevu'), cat.get('type'), cat.get('compte_prevu'), int(cat.get('soldee', False))))
                total_categories_prevues += 1
            
            # Transactions
            transactions = data.get('transactions', [])
            for trans in transactions:
                cursor.execute("""
                    INSERT INTO transactions (id, date, description, montant, categorie, compte_affecte, pointe, virement_id, origine, id_recurrence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trans.get('id'), trans.get('date'), trans.get('description'), trans.get('montant'),
                    trans.get('categorie'), trans.get('compte_affecte'), int(trans.get('pointe', False)),
                    trans.get('virement_id'), trans.get('origine'), trans.get('id_recurrence')
                ))
                total_transactions += 1
        
        print(f"{total_transactions} transactions migrées.")
        print(f"{total_categories_prevues} catégories prévues migrées.")

        # Migration des transactions récurrentes
        trans_rec = budget_data.get('transactions_recurrentes', [])
        for rec in trans_rec:
            cursor.execute("""
                INSERT INTO transactions_recurrentes (id, active, jour_du_mois, jour_echeance, description, categorie, montant, compte_affecte, type, source, destination, date_debut, date_fin, periodicite)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rec.get('id'), int(rec.get('active', True)), rec.get('jour_du_mois'), str(rec.get('jour_echeance')),
                rec.get('description'), rec.get('categorie'), rec.get('montant'), rec.get('compte_affecte'),
                rec.get('type'), rec.get('source'), rec.get('destination'), rec.get('date_debut'),
                rec.get('date_fin'), rec.get('periodicite')
            ))
        print(f"{len(trans_rec)} transactions récurrentes migrées.")

        # Migration des modèles
        templates = budget_data.get('_templates', {})
        for nom, categories_template in templates.items():
            cursor.execute("INSERT INTO budget_templates (nom) VALUES (?)", (nom,))
            template_id = cursor.lastrowid # Récupère l'ID du modèle juste inséré
            for cat in categories_template:
                cursor.execute("""
                    INSERT INTO budget_template_categories (template_id, categorie, type, prevu, compte_prevu)
                    VALUES (?, ?, ?, ?, ?)
                """, (template_id, cat.get('categorie'), cat.get('type'), cat.get('prevu'), cat.get('compte_prevu')))
        print(f"{len(templates)} modèles de budget migrés.")

        con.commit()
        print("Migration du budget terminée avec succès.")

    except FileNotFoundError:
        print("AVERTISSEMENT: Fichier 'budget_data.json' non trouvé. Aucune donnée de budget à migrer.")
    except Exception as e:
        print(f"ERREUR lors de la migration du budget: {e}")
        con.rollback()


except Exception as e:
    print(f"Une erreur critique est survenue: {e}")
finally:
    if 'con' in locals() and con:
        con.close()
        print("\nConnexion à la base de données fermée.")

print("--- Fin du script de migration ---")