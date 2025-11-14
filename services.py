# -*- coding: utf-8 -*-
import sqlite3
import json
import os
import shutil
from tkinter import messagebox
import traceback
from datetime import date, datetime, timedelta
from collections import defaultdict

# Imports pour les graphiques
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Imports depuis nos propres modules
from models import Compte, LignePortefeuille
from utils import format_nombre_fr

class GraphManager:
    """
    Gère la création et la mise à jour de tous les graphiques Matplotlib.
    """
    def __init__(self, figures_axes_canvases):
        """
        Initialise le manager avec les objets matplotlib nécessaires.
        :param figures_axes_canvases: Un dictionnaire contenant les figures, axes et canvas.
        Exemple: {'camembert_classe': {'fig': fig_obj, 'ax': ax_obj, 'canvas': canvas_obj}, ...}
        """
        self.figs = {key: value['fig'] for key, value in figures_axes_canvases.items()}
        self.axes = {key: value['ax'] for key, value in figures_axes_canvases.items()}
        self.canvases = {key: value['canvas'] for key, value in figures_axes_canvases.items()}

    def update_camembert_classe(self, comptes):
        ax = self.axes['camembert_classe']
        fig = self.figs['camembert_classe']
        canvas = self.canvases['camembert_classe']
        ax.clear()
        
        repartition = defaultdict(float)
        classes_valides = [c for c in Compte.CLASSE_ACTIF_CHOICES if c not in ["N/A", "Non Renseigné"]]
        for compte in comptes:
            if compte.type_compte == 'Actif' and compte.solde > 0 and compte.classe_actif in classes_valides:
                repartition[compte.classe_actif] += compte.solde
        
        labels = [l for l, s in repartition.items() if s > 0]
        sizes = [s for l, s in repartition.items() if s > 0]

        if not sizes:
            ax.text(0.5, 0.5, "Aucun actif classé", ha='center', va='center')
        else:
            wedges, _, _ = ax.pie(sizes, autopct='%1.1f%%', startangle=90, textprops=dict(color="w"))
            ax.legend(wedges, labels, title="Classes d'Actifs", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
            ax.axis('equal')
        
        ax.set_title("Répartition des Actifs par Classe")
        fig.tight_layout()
        canvas.draw()

    def update_camembert_banque(self, comptes):
        ax = self.axes['banque']
        fig = self.figs['banque']
        canvas = self.canvases['banque']
        ax.clear()
        
        repartition = defaultdict(float)
        for compte in comptes:
            if compte.type_compte == 'Actif' and compte.solde > 0 and compte.classe_actif != "Immobilier":
                repartition[compte.banque] += compte.solde
        
        labels = [l for l, s in repartition.items() if s > 0]
        sizes = [s for l, s in repartition.items() if s > 0]

        if not sizes:
            ax.text(0.5, 0.5, "Aucun actif bancaire", ha='center', va='center')
        else:
            ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
            ax.axis('equal')
            
        ax.set_title("Actifs par Banque (hors Immobilier)")
        fig.tight_layout()
        canvas.draw()

    def update_historique_patrimoine(self, historique):
        ax = self.axes['historique']
        fig = self.figs['historique']
        canvas = self.canvases['historique']
        ax.clear()

        if not historique:
            ax.text(0.5, 0.5, "Pas de données d'historique.", ha='center', va='center')
        else:
            dates_dt = [datetime.strptime(s['date'], "%Y-%m-%d") for s in historique]
            net = [s.get('patrimoine_net', 0) for s in historique]
            actifs = [s.get('total_actifs', 0) for s in historique]
            passifs = [s.get('total_passifs_magnitude', 0) for s in historique]
            
            ax.plot(dates_dt, net, marker='o', linestyle='-', label='Patrimoine Net')
            ax.plot(dates_dt, actifs, marker='^', linestyle='--', label='Total Actifs')
            ax.plot(dates_dt, passifs, marker='s', linestyle=':', label='Total Passifs')
            
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            fig.autofmt_xdate(rotation=45, ha='right')
            ax.set_title("Évolution du Patrimoine")
            ax.grid(True, linestyle='--', alpha=0.7)
            ax.legend(loc='best', fontsize='small')

        fig.tight_layout()
        canvas.draw()

    def update_historique_personnalise(self, historique, comptes_selectionnes):
        ax = self.axes['historique_perso']
        fig = self.figs['historique_perso']
        canvas = self.canvases['historique_perso']
        ax.clear()

        if not historique or not comptes_selectionnes:
            ax.text(0.5, 0.5, "Veuillez sélectionner au moins un compte.", ha='center', va='center')
        else:
            soldes_par_compte = {compte: [] for compte in comptes_selectionnes}
            dates_dt = []
            
            for snapshot in historique:
                if 'soldes_comptes' not in snapshot:
                    continue

                dates_dt.append(datetime.strptime(snapshot['date'], "%Y-%m-%d"))
                
                for nom_compte in comptes_selectionnes:
                    solde_du_jour = snapshot['soldes_comptes'].get(nom_compte, 0.0)
                    soldes_par_compte[nom_compte].append(solde_du_jour)

            if not dates_dt:
                ax.text(0.5, 0.5, "Aucun historique détaillé trouvé\npour les comptes sélectionnés.", ha='center', va='center')
            else:
                for nom_compte, soldes in soldes_par_compte.items():
                    ax.plot(dates_dt, soldes, marker='.', linestyle='-', label=nom_compte)
            
                ax.legend()
            
        ax.set_title("Évolution des Comptes Sélectionnés")
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        fig.autofmt_xdate(rotation=30, ha='right')
        fig.tight_layout()
        canvas.draw()
        
    def update_all_budget_graphs(self, donnees_du_mois, annee, mois):
        """Met à jour les 4 graphiques de l'onglet budget."""
        transactions = donnees_du_mois.get('transactions', [])
        categories_prevues = donnees_du_mois.get('categories_prevues', [])
        
        self._update_depenses_pie(transactions, annee, mois)
        self._update_recettes_pie(transactions, annee, mois)
        self._update_budget_vs_realise_bar(transactions, categories_prevues)

    def _update_depenses_pie(self, transactions, annee, mois):
        ax = self.axes['depenses']
        fig = self.figs['depenses']
        canvas = self.canvases['depenses']
        ax.clear()
        
        depenses_par_cat = defaultdict(float)
        for t in transactions:
            if t['montant'] < 0 and t['categorie'] != "(Virement)":
                depenses_par_cat[t['categorie']] += abs(t['montant'])
        
        if depenses_par_cat:
            ax.pie(depenses_par_cat.values(), labels=depenses_par_cat.keys(), autopct='%1.1f%%', startangle=90)
            ax.set_title(f"Dépenses de {mois:02}/{annee}")
        else:
            ax.text(0.5, 0.5, "Aucune dépense", ha='center', va='center')
            
        fig.tight_layout()
        canvas.draw()

    def _update_recettes_pie(self, transactions, annee, mois):
        ax = self.axes['recettes']
        fig = self.figs['recettes']
        canvas = self.canvases['recettes']
        ax.clear()
        
        recettes_par_cat = defaultdict(float)
        for t in transactions:
            if t['montant'] > 0 and t['categorie'] != "(Virement)":
                recettes_par_cat[t['categorie']] += t['montant']

        if recettes_par_cat:
            ax.pie(recettes_par_cat.values(), labels=recettes_par_cat.keys(), autopct='%1.1f%%', startangle=90)
            ax.set_title(f"Recettes de {mois:02}/{annee}")
        else:
            ax.text(0.5, 0.5, "Aucune recette", ha='center', va='center')
        
        fig.tight_layout()
        canvas.draw()

    def _update_budget_vs_realise_bar(self, transactions, categories_prevues):
        ax = self.axes['vs']
        fig = self.figs['vs']
        canvas = self.canvases['vs']
        ax.clear()
        
        realise_par_cat = defaultdict(float)
        for t in transactions:
            if t['categorie'] != "(Virement)":
                realise_par_cat[t['categorie']] += t['montant']

        depenses_budget = sorted([c for c in categories_prevues if c['type'] == 'Dépense' and c['prevu'] > 0], key=lambda x: x['prevu'], reverse=True)[:7]
        
        if depenses_budget:
            labels = [c['categorie'] for c in depenses_budget]
            budgete = [c['prevu'] for c in depenses_budget]
            realise = [abs(realise_par_cat.get(c['categorie'], 0.0)) for c in depenses_budget]
            
            x = range(len(labels))
            width = 0.35
            ax.bar(x, budgete, width, label='Budgeté')
            ax.bar([i + width for i in x], realise, width, label='Réalisé')
            ax.set_ylabel('Montant (€)')
            ax.set_title('Budget vs. Réalisé (Top Dépenses)')
            ax.set_xticks([i + width / 2 for i in x])
            ax.set_xticklabels(labels, rotation=45, ha="right")
            ax.legend()
        else:
            ax.text(0.5, 0.5, "Aucun budget de dépense défini", ha='center', va='center')
            
        fig.tight_layout()
        canvas.draw()

    def update_evolution_line(self, dates, evolution_par_compte):
            """Dessine le graphique d'évolution avec une courbe par compte."""
            ax = self.axes['evolution']
            fig = self.figs['evolution']
            canvas = self.canvases['evolution']
            ax.clear()

            if not dates or not evolution_par_compte:
                ax.text(0.5, 0.5, "Pas de données à afficher", ha='center', va='center')
            else:
                for nom_compte, soldes in evolution_par_compte.items():
                    ax.plot(dates, soldes, marker='.', linestyle='-', label=nom_compte)

                ax.axhline(0, color='r', linestyle='--', linewidth=0.8)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
                fig.autofmt_xdate()
                ax.grid(True, linestyle='--', alpha=0.6)
                ax.legend(fontsize='small')
            
            ax.set_title("Évolution Estimée des Soldes par Compte")
            fig.tight_layout()
            canvas.draw()

class SqlDataManager:

    def __init__(self, db_path):
        self.db_path = db_path
        self._creer_schema_si_necessaire()

    def _get_connection(self):
        """Crée et retourne une connexion à la base de données."""
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _creer_schema_si_necessaire(self):
        """S'assure que toutes les tables nécessaires existent et que leur schéma est à jour."""
        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                
                # --- ÉTAPE A : On crée TOUTES les tables si elles n'existent pas ---
                print("INFO: Création des tables si nécessaire...")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS comptes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, banque TEXT, type_compte TEXT,
                    solde REAL, liquidite TEXT, terme_passif TEXT, classe_actif TEXT,
                    suivi_budget INTEGER, alerte_decouvert INTEGER, solde_especes REAL DEFAULT 0.0 NOT NULL,
                    jour_debit INTEGER, jour_debut_periode INTEGER, jour_fin_periode INTEGER, compte_debit_associe TEXT
                )""")
                cursor.execute("CREATE TABLE IF NOT EXISTS historique_patrimoine (date TEXT PRIMARY KEY, patrimoine_net REAL, total_actifs REAL, total_passifs_magnitude REAL, details_json TEXT)")
                cursor.execute("CREATE TABLE IF NOT EXISTS transactions (id TEXT PRIMARY KEY, date TEXT, description TEXT, montant REAL, categorie TEXT, compte_affecte TEXT, pointe INTEGER, virement_id TEXT, origine TEXT, id_recurrence TEXT, date_budgetaire TEXT)")
                cursor.execute("CREATE TABLE IF NOT EXISTS categories_prevues (id INTEGER PRIMARY KEY AUTOINCREMENT, cle_mois_annee TEXT NOT NULL, categorie TEXT NOT NULL, prevu REAL, type TEXT, compte_prevu TEXT, soldee INTEGER)")
                cursor.execute("CREATE TABLE IF NOT EXISTS transactions_recurrentes (id TEXT PRIMARY KEY, active INTEGER, jour_du_mois INTEGER, jour_echeance TEXT, description TEXT, categorie TEXT, montant REAL, compte_affecte TEXT, type TEXT, source TEXT, destination TEXT, date_debut TEXT, date_fin TEXT, periodicite TEXT)")
                cursor.execute("CREATE TABLE IF NOT EXISTS budget_templates (id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL UNIQUE)")
                cursor.execute("CREATE TABLE IF NOT EXISTS budget_template_categories (id INTEGER PRIMARY KEY AUTOINCREMENT, template_id INTEGER, categorie TEXT, type TEXT, prevu REAL, compte_prevu TEXT, FOREIGN KEY (template_id) REFERENCES budget_templates (id) ON DELETE CASCADE)")
                cursor.execute("CREATE TABLE IF NOT EXISTS budget_details (id INTEGER PRIMARY KEY AUTOINCREMENT, categorie_prevue_id INTEGER NOT NULL, jour INTEGER NOT NULL, montant REAL NOT NULL, neutralise INTEGER DEFAULT 0, FOREIGN KEY (categorie_prevue_id) REFERENCES categories_prevues (id) ON DELETE CASCADE)")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS lignes_portefeuille (
                        "id" INTEGER PRIMARY KEY AUTOINCREMENT, "compte_id" INTEGER NOT NULL,
                        "nom" TEXT NOT NULL, "ticker" TEXT, "quantite" REAL NOT NULL,
                        "pru" REAL NOT NULL, "dernier_cours" REAL DEFAULT 0.0,
                        FOREIGN KEY("compte_id") REFERENCES "comptes"("id") ON DELETE CASCADE
                    )""")

                # --- ÉTAPE B : On effectue les migrations sur les tables maintenant qu'on est sûr qu'elles existent ---
                print("INFO: Vérification des migrations de schéma...")
                
                # Migration pour la colonne 'dernier_cours'
                cursor.execute("PRAGMA table_info(lignes_portefeuille)")
                if 'dernier_cours' not in [row['name'] for row in cursor.fetchall()]:
                    cursor.execute('ALTER TABLE lignes_portefeuille ADD COLUMN dernier_cours REAL DEFAULT 0.0')
                    print("INFO: Colonne 'dernier_cours' ajoutée à 'lignes_portefeuille'.")

                con.commit()
                print("INFO: Schéma de la base de données vérifié et à jour.")

        except Exception as e:
            messagebox.showerror("Erreur Critique DB", f"Impossible de créer ou vérifier le schéma de la base de données : {e}")
            raise e

    def charger_donnees(self):
        """Charge les données du patrimoine, Y COMPRIS les lignes de portefeuille."""
        print("INFO: Chargement des données du patrimoine depuis SQLite...")
        comptes = []
        historique = []
        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                
                cursor.execute("SELECT * FROM comptes ORDER BY nom")
                comptes_dict = {row['id']: Compte(**dict(row)) for row in cursor.fetchall()}

                # --- DÉBUT MODIFICATION : CHARGEMENT DU DERNIER COURS ---
                cursor.execute("SELECT * FROM lignes_portefeuille")
                for ligne_row in cursor.fetchall():
                    compte_parent_id = ligne_row['compte_id']
                    if compte_parent_id in comptes_dict:
                        # On passe maintenant le dictionnaire entier au constructeur
                        ligne_obj = LignePortefeuille(**dict(ligne_row))
                        comptes_dict[compte_parent_id].lignes_portefeuille.append(ligne_obj)
                # --- FIN MODIFICATION ---
                
                comptes = list(comptes_dict.values())

                cursor.execute("SELECT * FROM historique_patrimoine ORDER BY date")
                rows = cursor.fetchall()
                
                for row in rows:
                    try:
                        snap = dict(row)
                        details_json_str = snap.pop('details_json', None)
                        
                        if details_json_str:
                            details = json.loads(details_json_str)
                            snap.update(details)
                        
                        historique.append(snap)

                    except Exception as row_error:
                        print(f"AVERTISSEMENT: Impossible de charger une ligne d'historique. Données: {dict(row)}. Erreur: {row_error}")
                        continue 

            print(f"Chargé {len(comptes)} comptes (avec leurs lignes de portefeuille) et {len(historique)} entrées d'historique.")

        except Exception as e:
            messagebox.showerror("Erreur SQL", f"Impossible de charger les données du patrimoine : {e}")
        
        return comptes, historique

    def sauvegarder_donnees(self, comptes, historique):
        """Sauvegarde les comptes, l'historique ET les lignes de portefeuille."""
        print("INFO: Sauvegarde des données du patrimoine dans SQLite...")
        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                
                # --- DÉBUT DE LA LOGIQUE AMÉLIORÉE ---
                
                # On traite d'abord les comptes
                ids_comptes_sauvegardes = []
                for compte in comptes:
                    compte_dict = compte.to_dict()
                    if compte.id is None: # C'est un nouveau compte
                        cursor.execute("""
                            INSERT INTO comptes (nom, banque, type_compte, solde, liquidite, terme_passif, classe_actif, 
                                                 suivi_budget, alerte_decouvert, solde_especes, jour_debit, 
                                                 jour_debut_periode, jour_fin_periode, compte_debit_associe)
                            VALUES (:nom, :banque, :type_compte, :solde, :liquidite, :terme_passif, :classe_actif, 
                                    :suivi_budget, :alerte_decouvert, :solde_especes, :jour_debit, 
                                    :jour_debut_periode, :jour_fin_periode, :compte_debit_associe)
                        """, compte_dict)
                        compte.id = cursor.lastrowid # On récupère et assigne le nouvel ID
                        print(f"INFO: Nouveau compte '{compte.nom}' inséré avec l'ID {compte.id}.")
                    else: # C'est un compte existant
                        cursor.execute("""
                            UPDATE comptes SET 
                                nom=:nom, banque=:banque, type_compte=:type_compte, solde=:solde, liquidite=:liquidite, 
                                terme_passif=:terme_passif, classe_actif=:classe_actif, suivi_budget=:suivi_budget, 
                                alerte_decouvert=:alerte_decouvert, solde_especes=:solde_especes, jour_debit=:jour_debit,
                                jour_debut_periode=:jour_debut_periode, jour_fin_periode=:jour_fin_periode, 
                                compte_debit_associe=:compte_debit_associe
                            WHERE id=:id
                        """, compte_dict)
                    ids_comptes_sauvegardes.append(compte.id)

                # On supprime les lignes de portefeuille de la base pour tout recréer proprement
                cursor.execute("DELETE FROM lignes_portefeuille")
                
                # On réinsère toutes les lignes de portefeuille avec les bons compte_id
                for compte in comptes:
                    if compte.classe_actif == "Actions/Titres":
                        for ligne in compte.lignes_portefeuille:
                            cursor.execute("""
                                INSERT INTO lignes_portefeuille (compte_id, nom, ticker, quantite, pru, dernier_cours)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (compte.id, ligne.nom, ligne.ticker, ligne.quantite, ligne.pru, ligne.dernier_cours))

                # --- FIN DE LA LOGIQUE AMÉLIORÉE ---

                # La partie sur l'historique ne change pas
                for snap in historique:
                    cursor.execute("""
                        INSERT OR REPLACE INTO historique_patrimoine (date, patrimoine_net, total_actifs, total_passifs_magnitude, details_json)
                        VALUES (?, ?, ?, ?, ?)
                    """,(
                        snap.get('date'), snap.get('patrimoine_net'), snap.get('total_actifs'), snap.get('total_passifs_magnitude'),
                        json.dumps({'repartition_actifs_par_classe': snap.get('repartition_actifs_par_classe',{}), 'soldes_comptes': snap.get('soldes_comptes',{})})
                    ))
                con.commit()
                print("INFO: Sauvegarde des données du patrimoine terminée avec succès.")
        except Exception as e:
            messagebox.showerror("Erreur SQL", f"Impossible de sauvegarder les données du patrimoine : {e}")
            traceback.print_exc() # Affiche l'erreur détaillée dans la console
       
    def charger_budget_donnees(self):
        print("INFO: Chargement des données de budget depuis SQLite...")
        budget_data = defaultdict(lambda: {'categories_prevues': [], 'transactions': []})
        try:
            with self._get_connection() as con:
                try:
                    cursor_check = con.cursor()
                    cursor_check.execute("PRAGMA table_info(budget_details)")
                    if 'neutralise' not in [row['name'] for row in cursor_check.fetchall()]:
                        cursor_check.execute('ALTER TABLE budget_details ADD COLUMN neutralise INTEGER DEFAULT 0')
                        print("INFO: Colonne 'neutralise' ajoutée à la volée à 'budget_details'.")
                        con.commit()
                except sqlite3.OperationalError:
                    pass
                cursor = con.cursor()
                cursor.execute("SELECT * FROM categories_prevues")
                categories_par_id = {row['id']: dict(row) for row in cursor.fetchall()}
                for cat_id in categories_par_id:
                    categories_par_id[cat_id]['details'] = []

                cursor.execute("SELECT * FROM budget_details")
                for detail_row in cursor.fetchall():
                    parent_id = detail_row['categorie_prevue_id']
                    if parent_id in categories_par_id:
                        detail_dict = dict(detail_row)
                        detail_dict['neutralise'] = bool(detail_dict.get('neutralise'))
                        categories_par_id[parent_id]['details'].append(detail_dict)
                
                for cat_data in categories_par_id.values():
                    cle_mois = cat_data.pop('cle_mois_annee')
                    cat_data['soldee'] = bool(cat_data.get('soldee'))
                    budget_data[cle_mois]['categories_prevues'].append(cat_data)
                
                cursor.execute("SELECT * FROM transactions")
                for row in cursor.fetchall():
                    trans = dict(row)
                    trans['pointe'] = bool(trans.get('pointe'))
                    cle_mois = datetime.strptime(trans['date'], "%Y-%m-%d").strftime("%Y-%m")
                    budget_data[cle_mois]['transactions'].append(trans)
                
                cursor.execute("SELECT * FROM transactions_recurrentes")
                budget_data['transactions_recurrentes'] = [dict(row) for row in cursor.fetchall()]

                templates = {}
                cursor.execute("SELECT id, nom FROM budget_templates")
                for template_row in cursor.fetchall():
                    template_id, template_nom = template_row['id'], template_row['nom']
                    cat_cursor = con.cursor()
                    cat_cursor.execute("SELECT categorie, type, prevu, compte_prevu FROM budget_template_categories WHERE template_id = ?", (template_id,))
                    templates[template_nom] = [dict(cat_row) for cat_row in cat_cursor.fetchall()]
                budget_data['_templates'] = templates

        except Exception as e:
             messagebox.showerror("Erreur SQL", f"Impossible de charger les données du budget : {e}\n{traceback.format_exc()}")

        return dict(budget_data)

    def sauvegarder_budget_donnees(self, budget_data):
        print("INFO: Sauvegarde des données de budget dans SQLite...")
        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                cursor.execute("BEGIN TRANSACTION")
                cursor.execute("DELETE FROM budget_details")
                cursor.execute("DELETE FROM transactions")
                cursor.execute("DELETE FROM categories_prevues")
                cursor.execute("DELETE FROM transactions_recurrentes")
                cursor.execute("DELETE FROM budget_template_categories")
                cursor.execute("DELETE FROM budget_templates")
                
                for cle, data in budget_data.items():
                    if cle == "_templates":
                        for nom, cats in data.items():
                            cursor.execute("INSERT INTO budget_templates (nom) VALUES (?)", (nom,)); template_id = cursor.lastrowid
                            for cat in cats: cursor.execute("INSERT INTO budget_template_categories (template_id, categorie, type, prevu, compte_prevu) VALUES (?, ?, ?, ?, ?)", (template_id, cat.get('categorie'), cat.get('type'), cat.get('prevu'), cat.get('compte_prevu')))
                    elif cle == "transactions_recurrentes":
                        for rec in data: cursor.execute("INSERT INTO transactions_recurrentes (id, active, jour_du_mois, jour_echeance, description, categorie, montant, compte_affecte, type, source, destination, date_debut, date_fin, periodicite) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (rec.get('id'), int(rec.get('active', True)), rec.get('jour_du_mois'), str(rec.get('jour_echeance')), rec.get('description'), rec.get('categorie'), rec.get('montant'), rec.get('compte_affecte'), rec.get('type'), rec.get('source'), rec.get('destination'), rec.get('date_debut'), rec.get('date_fin'), rec.get('periodicite')))
                    else:
                        for cat in data.get('categories_prevues', []):
                            cursor.execute("INSERT INTO categories_prevues (cle_mois_annee, categorie, prevu, type, compte_prevu, soldee) VALUES (?, ?, ?, ?, ?, ?)", (cle, cat.get('categorie'), cat.get('prevu'), cat.get('type'), cat.get('compte_prevu'), int(cat.get('soldee', False))))
                            categorie_id = cursor.lastrowid
                            if 'details' in cat and cat['details']:
                                for detail in cat['details']:
                                    cursor.execute("INSERT INTO budget_details (categorie_prevue_id, jour, montant, neutralise) VALUES (?, ?, ?, ?)", 
                                                   (categorie_id, detail.get('jour'), detail.get('montant'), int(detail.get('neutralise', False))))
                        
                        for trans in data.get('transactions', []):
                            # --- CORRECTION DE LA REQUÊTE D'INSERTION ---
                            cursor.execute("""
                                INSERT INTO transactions 
                                (id, date, description, montant, categorie, compte_affecte, pointe, virement_id, origine, id_recurrence, date_budgetaire) 
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                trans.get('id'), trans.get('date'), trans.get('description'), trans.get('montant'), 
                                trans.get('categorie'), trans.get('compte_affecte'), int(trans.get('pointe', False)), 
                                trans.get('virement_id'), trans.get('origine'), trans.get('id_recurrence'),
                                trans.get('date_budgetaire') # On ajoute la nouvelle donnée
                            ))
                            # --- FIN DE LA CORRECTION ---
                
                con.commit()
        except Exception as e:
             messagebox.showerror("Erreur SQL", f"Impossible de sauvegarder les données du budget : {e}\n{traceback.format_exc()}")
             con.rollback()

    def charger_parametres(self):
        try:
            settings_path = os.path.join(os.path.dirname(self.db_path), "settings.json")
            with open(settings_path, 'r') as f: settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): settings = {"theme": "light"}
        return settings

    def sauvegarder_parametres(self, settings):
        try:
            settings_path = os.path.join(os.path.dirname(self.db_path), "settings.json")
            with open(settings_path, 'w') as f: json.dump(settings, f, indent=4)
        except IOError as e: print(f"Erreur de sauvegarde des paramètres: {e}")
