import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime, date, timedelta
import calendar
from collections import defaultdict

from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

# Importe les classes et fonctions nécessaires de tes fichiers existants
from models import Compte
from services import SqlDataManager
from utils import format_nombre_fr

app = Flask(__name__)
app.config['SECRET_KEY'] = 'TA_CLE_SECRETE_ALEATOIRE_ET_LONGUE' # Utilise ta clé SECURE ici
app.config['JSON_AS_ASCII'] = False # Pour gérer les caractères accentués correctement

# Configure le chemin de la base de données sur ton SSD
DB_PATH = os.path.join(app.root_path, "budget.db")
data_manager = SqlDataManager(DB_PATH)

# --- Configuration Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id):
        self.id = id

    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    if user_id == 'admin':
        return User(user_id)
    return None

USERS_CREDENTIALS = {
    "admin": 'pbkdf2:sha256:260000$CDN0FL0qwSA2AXB7$e598e1304b5eb8ef1b19590a7d3b1e402ba06005b594bbc0a35dbb15b38441e2'
}

# --- Fonctions utilitaires réintégrées et adaptées ---

def _parse_date_flexible(date_str):
    """Tente de parser une chaîne de date avec plusieurs formats courants."""
    formats_a_tester = [
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    ]
    for fmt in formats_a_tester:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Format de date '{date_str}' non reconnu.")

def _get_all_transactions_flat(budget_data):
    """Rassemble toutes les transactions de tous les mois en une seule liste plate."""
    all_trans = []
    for cle, data in budget_data.items():
        if not cle.startswith("_") and isinstance(data, dict) and 'transactions' in data:
            all_trans.extend(data['transactions'])
    return all_trans

def _generer_transactions_recurrentes_pour_le_mois(year, month, budget_data, comptes_app, data_manager):
    """
    Adapte la logique de generer_transactions_recurrentes_pour_le_mois de main.py
    pour l'environnement Flask.
    """
    print(f"\n[DEBUG REC] Lancement génération récurrences pour {year:04d}-{month:02d}")

    if 'transactions_recurrentes' not in budget_data:
        print("[DEBUG REC] Pas de règles récurrentes définies.")
        return

    cle_mois_annee = f"{year}-{month:02d}"
    if cle_mois_annee not in budget_data:
        budget_data[cle_mois_annee] = {'categories_prevues': [], 'transactions': []}

    transactions_du_mois = budget_data[cle_mois_annee]['transactions']
    categories_prevues_du_mois = budget_data[cle_mois_annee]['categories_prevues']
    noms_categories_existantes = {cat['categorie'].lower() for cat in categories_prevues_du_mois}

    # Filtrer les transactions déjà générées ce mois-ci par une règle spécifique
    ids_recurrence_generees_mois = {t.get('id_recurrence') for t in transactions_du_mois if t.get('origine') == 'recurrente'}

    modifications_faites = False
    premier_jour_mois = date(year, month, 1)
    dernier_jour_mois = (premier_jour_mois.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    for trans_rec in budget_data['transactions_recurrentes']:
        id_recurrence = trans_rec['id']
        periodicite = trans_rec.get('periodicite', 'Mensuelle')

        # Pour les périodicités fixes (mensuelle, annuelle, etc.), on ne génère qu'une fois par règle et par mois
        if id_recurrence in ids_recurrence_generees_mois and periodicite not in ['Hebdomadaire', 'Bi-mensuelle']:
            continue

        if not trans_rec.get('active', False):
            continue

        date_debut_str = trans_rec.get('date_debut', '1900-01-01')
        date_fin_str = trans_rec.get('date_fin')
        try:
            date_debut = datetime.strptime(date_debut_str, "%Y-%m-%d").date()
            date_fin = datetime.strptime(date_fin_str, "%Y-%m-%d").date() if date_fin_str else date(9999, 12, 31)
        except (ValueError, TypeError):
            print(f"[DEBUG REC] Erreur de date pour règle {id_recurrence}: {date_debut_str}/{date_fin_str}")
            continue

        if date_fin < premier_jour_mois or date_debut > dernier_jour_mois:
            continue

        jour_echeance_str = str(trans_rec.get('jour_echeance', trans_rec.get('jour_du_mois', 1)))
        dates_a_generer = []

        if periodicite in ['Mensuelle', 'Trimestrielle', 'Tous les 4 mois', 'Semestrielle', 'Annuelle']:
            jour_echeance_val = int(jour_echeance_str.split(',')[0]) # Prend le premier jour si bi-mensuel ou autre

            should_generate = False
            if periodicite == 'Mensuelle':
                should_generate = True
            elif periodicite == 'Trimestrielle' and (month - date_debut.month) % 3 == 0:
                should_generate = True
            elif periodicite == 'Tous les 4 mois' and (month - date_debut.month) % 4 == 0:
                should_generate = True
            elif periodicite == 'Semestrielle' and (month - date_debut.month) % 6 == 0:
                should_generate = True
            elif periodicite == 'Annuelle' and month == date_debut.month:
                should_generate = True

            if should_generate:
                try:
                    dates_a_generer.append(date(year, month, min(jour_echeance_val, calendar.monthrange(year, month)[1])))
                except ValueError:
                    print(f"[DEBUG REC] Jour '{jour_echeance_val}' invalide pour {year}-{month} pour règle {id_recurrence}.")
                    pass

        elif periodicite == 'Bi-mensuelle':
            try:
                jours_echeance_bi = [int(j.strip()) for j in jour_echeance_str.split(',')]
                for jour in jours_echeance_bi:
                    try:
                        dates_a_generer.append(date(year, month, min(jour, calendar.monthrange(year, month)[1])))
                    except ValueError:
                        print(f"[DEBUG REC] Jour bi-mensuel '{jour}' invalide pour {year}-{month} pour règle {id_recurrence}.")
                        pass
            except ValueError:
                print(f"[DEBUG REC] Format jours bi-mensuels invalide pour règle {id_recurrence}.")
                pass

        elif periodicite == 'Hebdomadaire':
            try:
                jour_semaine_cible = int(jour_echeance_str)
                current_day = premier_jour_mois
                while current_day <= dernier_jour_mois:
                    if current_day.isoweekday() == jour_semaine_cible:
                        dates_a_generer.append(current_day)
                    current_day += timedelta(days=1)
            except ValueError:
                print(f"[DEBUG REC] Jour semaine invalide pour règle {id_recurrence}.")
                pass

        for date_trans in dates_a_generer:
            if not (date_debut <= date_trans <= date_fin):
                print(f"[DEBUG REC] Date {date_trans} hors période de validité pour règle {id_recurrence}.")
                continue

            id_gen = f"{id_recurrence}_{date_trans.strftime('%Y%m%d')}"
            if id_gen in ids_recurrence_generees_mois:
                print(f"[DEBUG REC] Règle {id_recurrence} déjà générée pour {date_trans}.")
                continue

            modifications_faites = True

            if trans_rec.get('type') == 'Virement':
                montant_virement = abs(trans_rec.get('montant', 0.0))
                source, dest = trans_rec.get('source'), trans_rec.get('destination')
                if not source or not dest:
                    print(f"[DEBUG REC] Virement incomplet pour règle {id_recurrence}.")
                    continue

                transactions_du_mois.extend([
                    {"id": os.urandom(16).hex(), "id_recurrence": id_gen, "origine": "recurrente", "date": date_trans.strftime("%Y-%m-%d"), "description": f"Virement récurrent vers {dest}", "montant": -montant_virement, "categorie": "(Virement)", "compte_affecte": source, "pointe": False},
                    {"id": os.urandom(16).hex(), "id_recurrence": id_gen, "origine": "recurrente", "date": date_trans.strftime("%Y-%m-%d"), "description": f"Virement récurrent depuis {source}", "montant": montant_virement, "categorie": "(Virement)", "compte_affecte": dest, "pointe": False}
                ])
                print(f"[DEBUG REC] Virement récurrent généré: {montant_virement} de {source} vers {dest} le {date_trans}.")
            else:
                # Assurez-vous que le compte affecté est un compte suivi pour le budget
                if not trans_rec.get('compte_affecte') or trans_rec.get('compte_affecte') not in [c.nom for c in comptes_app if c.suivi_budget]:
                    print(f"[DEBUG REC] Règle '{trans_rec.get('description')}' ignorée, compte affecté non spécifié ou non suivi.")
                    continue

                nouvelle_trans = {
                    "id": os.urandom(16).hex(), "id_recurrence": id_gen, "origine": "recurrente", "date": date_trans.strftime("%Y-%m-%d"),
                    "description": trans_rec['description'], "montant": trans_rec['montant'], "categorie": trans_rec['categorie'],
                    "compte_affecte": trans_rec['compte_affecte'], "pointe": False
                }
                transactions_du_mois.append(nouvelle_trans)
                print(f"[DEBUG REC] Transaction récurrente générée: {trans_rec['description']} ({trans_rec['montant']}€) le {date_trans}.")

                # --- PARTIE 3 : Création automatique du budget ---
                cat_nom_lower = trans_rec['categorie'].lower()
                if cat_nom_lower not in noms_categories_existantes:
                    type_cat = "Revenu" if trans_rec['montant'] > 0 else "Dépense"
                    nouvelle_cat_budget = {
                        'categorie': trans_rec['categorie'],
                        'prevu': abs(trans_rec['montant']),
                        'type': type_cat,
                        'compte_prevu': trans_rec['compte_affecte'],
                        'soldee': False
                    }
                    categories_prevues_du_mois.append(nouvelle_cat_budget)
                    noms_categories_existantes.add(cat_nom_lower)
                    print(f"[DEBUG REC] Catégorie de budget auto-créée pour '{trans_rec['categorie']}'.")

    if modifications_faites:
        data_manager.sauvegarder_budget_donnees(budget_data)
        print("[DEBUG REC] Modifications de budget_data sauvegardées.")
    else:
        print("[DEBUG REC] Aucune modification à sauvegarder.")

def _calculer_solde_previsionnel(year, month, comptes_app, all_budget_data):
    """
    Adapte le moteur de calcul _calculer_projection_mensuelle de main.py
    pour être utilisé dans Flask.
    """
    try:
        print(f"\n[DEBUG PROJECTION] Lancement du calcul prévisionnel pour {year:04d}-{month:02d}")
    except (ValueError, TypeError):
        print("[DEBUG PROJECTION] Erreur initiale de type/valeur pour projection.")
        return None

    comptes_suivis = [c for c in comptes_app if c.suivi_budget]
    print(f"[DEBUG PROJECTION] Nombre total de comptes passés (comptes_app) : {len(comptes_app)}")
    for c in comptes_app:
        print(f"[DEBUG PROJECTION] Compte: {c.nom} (Type: {c.type_compte}), Suivi Budget: {c.suivi_budget}, Solde: {c.solde}")

    print(f"[DEBUG PROJECTION] Nombre de comptes suivis trouvés : {len(comptes_suivis)}")

    if not comptes_suivis:
        print("[DEBUG PROJECTION] Aucun compte marqué pour le suivi budgétaire trouvé. Retourne None.")
        return None

    comptes_suivis_dict = {c.nom: c for c in comptes_suivis}
    activite_par_compte = {c.nom: 0.0 for c in comptes_suivis}
    impact_budget_restant_par_compte = {c.nom: 0.0 for c in comptes_suivis}

    # _get_all_transactions_flat est une fonction auxiliaire qui doit être définie
    toutes_les_transactions = _get_all_transactions_flat(all_budget_data)

    cle_mois_annee = f"{year:04d}-{month:02d}"

    transactions_du_mois_en_cours = [t for t in toutes_les_transactions if _parse_date_flexible(t['date']).strftime('%Y-%m') == cle_mois_annee]

    realise_par_categorie = defaultdict(float)
    for t in transactions_du_mois_en_cours:
        if t.get('categorie') != "(Virement)":
            realise_par_categorie[t.get('categorie')] += t.get('montant', 0.0)

    # --- Simulation des règlements de cartes (logique dupliquée de main.py) ---
    print("[DEBUG PROJECTION] Simulation des règlements de cartes à débit différé...")
    cartes_passives = [c for c in comptes_suivis if c.type_compte == 'Passif']
    lignes_budget_futures = [] # Pour le détail affiché
    for carte in cartes_passives:
        if not all([carte.jour_debit, carte.jour_debut_periode, carte.jour_fin_periode, carte.compte_debit_associe]):
            print(f"  [DEBUG PROJECTION] -> Carte '{carte.nom}' ignorée, infos de règlement manquantes.")
            continue

        reglement_deja_saisi = any(
            t.get('categorie') == '(Virement)' and
            (
                (t.get('compte_affecte') == carte.compte_debit_associe and f"vers {carte.nom}" in t.get('description', '')) or
                (t.get('compte_affecte') == carte.nom and f"depuis {carte.compte_debit_associe}" in t.get('description', ''))
            )
            for t in transactions_du_mois_en_cours # On cherche dans les transactions DU MOIS EN COURS
        )

        if reglement_deja_saisi:
            print(f"  [DEBUG PROJECTION] -> Un règlement manuel pour la carte '{carte.nom}' a déjà été trouvé. Simulation ignorée.")
            continue

        try:
            # Calcul robuste des dates de relevé (gestion des fins de mois)
            last_day_month_fin = calendar.monthrange(year, month)[1]
            jour_fin_releve_clamped = min(carte.jour_fin_periode, last_day_month_fin)
            date_fin_releve = date(year, month, jour_fin_releve_clamped)

            prev_month = month - 1
            prev_year = year
            if prev_month == 0:
                prev_month = 12
                prev_year -= 1

            last_day_month_debut = calendar.monthrange(prev_year, prev_month)[1]
            jour_debut_releve_clamped = min(carte.jour_debut_periode, last_day_month_debut)
            date_debut_releve = date(prev_year, prev_month, jour_debut_releve_clamped)

            transactions_reglement_carte = [
                t for t in toutes_les_transactions # On cherche dans TOUTES les transactions de la BD
                if t.get('compte_affecte') == carte.nom
                and date_debut_releve <= _parse_date_flexible(t['date']) <= date_fin_releve
                and t.get('categorie') != '(Virement)'
                and t.get('pointe', False) # On ne prend que les transactions pointées pour le solde de la CB
            ]

            montant_a_regler = sum(t.get('montant', 0.0) for t in transactions_reglement_carte)

            if montant_a_regler != 0 and carte.compte_debit_associe in comptes_suivis_dict:
                impact_debit = -abs(montant_a_regler)
                activite_par_compte[carte.compte_debit_associe] += impact_debit
                lignes_budget_futures.append(f"  Prélèvement CB {carte.nom} sur {carte.compte_debit_associe}: {format_nombre_fr(impact_debit)} €")

                impact_credit = abs(montant_a_regler)
                activite_par_compte[carte.nom] += impact_credit
                lignes_budget_futures.append(f"  Apurement solde {carte.nom}: +{format_nombre_fr(impact_credit)} €")
                print(f"  [DEBUG PROJECTION] -> Simulation règlement carte: {carte.nom} de {montant_a_regler}€")

        except (ValueError, TypeError, AttributeError) as e:
            print(f"  [DEBUG PROJECTION] -> AVERTISSEMENT: Impossible de calculer le règlement pour {carte.nom}. Erreur: {e}")
            continue

    # --- Calcul de l'activité (transactions non pointées) ---
    print("[DEBUG PROJECTION] Calcul de l'activité (transactions non pointées jusqu'à la fin du mois)...")
    _, nb_jours_mois = calendar.monthrange(year, month)
    date_fin_mois_actuel = date(year, month, nb_jours_mois)

    for t in toutes_les_transactions: # Cherche dans TOUTES les transactions
        if not t.get('pointe', False) and _parse_date_flexible(t['date']) <= date_fin_mois_actuel:
            if t.get('compte_affecte') in comptes_suivis_dict:
                 activite_par_compte[t.get('compte_affecte')] += t.get('montant', 0.0)
                 print(f"  [DEBUG PROJECTION] -> Transaction non pointée: {t.get('description')} ({t.get('montant')}€ sur {t.get('compte_affecte')})")

    # --- Calcul du budget restant (logique dupliquée de main.py) ---
    print("[DEBUG PROJECTION] Calcul de l'impact du budget restant (logique hybride)...")
    donnees_mois_budget = all_budget_data.get(cle_mois_annee, {}) # Accès aux données du mois
    categories_prevues_mois = donnees_mois_budget.get('categories_prevues', [])

    for cat in categories_prevues_mois:
        if cat.get('soldee', False):
            print(f"  [DEBUG PROJECTION] Catégorie '{cat.get('categorie')}' est soldée, ignorée pour impact prévisionnel.")
            continue

        compte_prevu = cat.get('compte_prevu')
        if not compte_prevu or compte_prevu not in comptes_suivis_dict:
            print(f"  [DEBUG PROJECTION] Catégorie '{cat.get('categorie')}' ignorée (compte non trouvé ou non suivi).")
            continue

        daily_details = cat.get('details')

        realise_pour_cette_cat = realise_par_categorie.get(cat.get('categorie'), 0.0) # Ce realise_par_categorie est pour transactions DU MOIS

        if daily_details:
            transactions_de_la_cat = [t for t in transactions_du_mois_en_cours if t.get('categorie') == cat.get('categorie')]
            jours_avec_transaction_reelle = {_parse_date_flexible(t['date']).day for t in transactions_de_la_cat}

            impact_detail_reste_a_faire = 0.0
            for detail in daily_details:
                jour_budget = detail.get('jour')
                montant_detail = detail.get('montant')

                est_neutralise_manuellement = detail.get('neutralise', False)
                a_une_transaction_reelle = jour_budget in jours_avec_transaction_reelle

                if not est_neutralise_manuellement and not a_une_transaction_reelle:
                    impact_detail_reste_a_faire += montant_detail
                    lignes_budget_futures.append(f"  Budget journalier {cat.get('categorie')} (Jour {jour_budget}): {format_nombre_fr(-montant_detail if cat.get('type')=='Dépense' else montant_detail)} €")

            if cat.get('type') == 'Dépense':
                impact_final = -impact_detail_reste_a_faire
            else:
                impact_final = impact_detail_reste_a_faire

            impact_budget_restant_par_compte[compte_prevu] += impact_final
            print(f"  [DEBUG PROJECTION] -> Impact détails journaliers '{cat.get('categorie')}': {impact_final} € sur {compte_prevu}")

        else: # Si pas de détails journaliers, la logique actuelle est bonne (prévu - réalisé)
            prevu_signe = -cat.get('prevu', 0.0) if cat.get('type') == 'Dépense' else cat.get('prevu', 0.0)
            reste_a_impacter = prevu_signe - realise_pour_cette_cat

            if abs(reste_a_impacter) > 0.01:
                impact_budget_restant_par_compte[compte_prevu] += reste_a_impacter
                lignes_budget_futures.append(f"  Budget standard '{cat.get('categorie')}': {format_nombre_fr(reste_a_impacter)} € sur {compte_prevu}")
                print(f"  [DEBUG PROJECTION] -> Impact restant '{cat.get('categorie')}': {reste_a_impacter} € sur {compte_prevu}")


    # --- Construction finale (logique des totaux inchangée) ---
    print("[DEBUG PROJECTION] Construction du détail final pour affichage...")
    details_pour_affichage = {}
    total_previsionnel_actifs = 0.0
    total_previsionnel_passifs = 0.0

    # Pour le graphique
    dates_graphe = [date(year, month, jour) for jour in range(1, calendar.monthrange(year, month)[1] + 1)]
    evolution_par_compte = {c.nom: [] for c in comptes_suivis if c.type_compte == 'Actif'}

    for compte in comptes_suivis:
        est_passif = compte.type_compte == 'Passif'
        nom_display = f"{compte.nom} (-)" if est_passif else compte.nom

        solde_pointe_compte = compte.solde # C'est le solde actuel réel de la BD
        activite_mois = activite_par_compte.get(compte.nom, 0.0)
        impact_budget = impact_budget_restant_par_compte.get(compte.nom, 0.0)

        if est_passif:
            solde_virtuel_display = solde_pointe_compte - activite_mois
            solde_previsionnel_display = solde_virtuel_display - impact_budget
            total_previsionnel_passifs += solde_previsionnel_display
        else:
            solde_virtuel_display = solde_pointe_compte + activite_mois
            solde_previsionnel_display = solde_virtuel_display + impact_budget
            total_previsionnel_actifs += solde_previsionnel_display

        details_pour_affichage[nom_display] = {
            'solde_pointe': solde_pointe_compte,
            'activite_mois': activite_mois,
            'solde_virtuel': solde_pointe_compte + activite_mois, # Recalcul ici pour la cohérence
            'impact_budget': impact_budget,
            'solde_previsionnel': solde_previsionnel_display
        }
        print(f"  [DEBUG PROJECTION] -> Compte '{compte.nom}': Solde Pointé={solde_pointe_compte}, Activité Mois={activite_mois}, Impact Budget={impact_budget}, Solde Prévisionnel={solde_previsionnel_display}")

    total_previsionnel_net = total_previsionnel_actifs - total_previsionnel_passifs
    print(f"[DEBUG PROJECTION] Total Actifs Prévisionnels : {total_previsionnel_actifs}")
    print(f"[DEBUG PROJECTION] Total Passifs Prévisionnels : {total_previsionnel_passifs}")
    print(f"[DEBUG PROJECTION] PATRIMOINE NET PRÉVISIONNEL CALCULÉ : {total_previsionnel_net}")

    # --- Calcul pour le graphique d'évolution des soldes (dans _calculer_projection_mensuelle) ---
    for compte in comptes_app: # Itérer sur tous les comptes, pas seulement suivis
        if compte.type_compte == 'Actif': # Seulement les actifs pour ce graphique
            evolution_par_compte[compte.nom] = []
            solde_courant = compte.solde # Solde initial pointé

            # Pour chaque jour du mois
            for jour in range(1, calendar.monthrange(year, month)[1] + 1):
                date_jour = date(year, month, jour)

                # Ajouter les transactions non pointées qui se sont déroulées jusqu'à ce jour
                for t in toutes_les_transactions:
                     # Assurez-vous que la transaction est du bon compte et non pointée
                     if not t.get('pointe') and t.get('compte_affecte') == compte.nom and _parse_date_flexible(t['date']) == date_jour:
                         solde_courant += t.get('montant', 0.0)

                # A la fin du mois, ajoute l'impact du budget et des règlements de cartes
                if jour == calendar.monthrange(year, month)[1]: # Dernier jour du mois
                     solde_courant += impact_budget_restant_par_compte.get(compte.nom, 0.0) # Impact du budget

                     # Impact des règlements de cartes de débit différé (qui arrivent généralement en fin de mois)
                     for carte in cartes_passives:
                         if carte.compte_debit_associe == compte.nom:
                             # On recalcule le montant à régler pour cette simulation de graphique
                             last_day_month_fin_graph = calendar.monthrange(year, month)[1]
                             jour_fin_releve_clamped_graph = min(carte.jour_fin_periode, last_day_month_fin_graph)
                             date_fin_releve_graph = date(year, month, jour_fin_releve_clamped_graph)

                             prev_month_graph = month - 1
                             prev_year_graph = year
                             if prev_month_graph == 0:
                                 prev_month_graph = 12
                                 prev_year_graph -= 1

                             last_day_month_debut_graph = calendar.monthrange(prev_year_graph, prev_month_graph)[1]
                             jour_debut_releve_clamped_graph = min(carte.jour_debut_periode, last_day_month_debut_graph)
                             date_debut_releve_graph = date(prev_year_graph, prev_month_graph, jour_debut_releve_clamped_graph)

                             montant_a_regler_graph = sum(t.get('montant', 0.0) for t in toutes_les_transactions if t.get('compte_affecte') == carte.nom and date_debut_releve_graph <= _parse_date_flexible(t['date']) <= date_fin_releve_graph and t.get('pointe'))
                             if not any(t.get('categorie') == '(Virement)' and t.get('compte_affecte') == compte.nom and f"vers {carte.nom}" in t.get('description','') for t in transactions_du_mois_en_cours):
                                  solde_courant -= abs(montant_a_regler_graph) # Si pas de virement manuel pour ce mois

                evolution_par_compte[compte.nom].append(solde_courant)

    return {
        "dates_graphe": dates_graphe,
        "evolution_par_compte": evolution_par_compte,
        "details_pour_affichage": details_pour_affichage,
        "lignes_budget_futures": sorted(lignes_budget_futures),
        "total_previsionnel_actifs": total_previsionnel_actifs,
        "total_previsionnel_passifs": total_previsionnel_passifs,
        "total_previsionnel_net": total_previsionnel_net
    }

# --- ROUTES FLASK ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in USERS_CREDENTIALS and check_password_hash(USERS_CREDENTIALS[username], password):
            user = User(username)
            login_user(user)
            flash('Connexion réussie !', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Nom d\'utilisateur ou mot de passe incorrect.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    try:
        comptes, historique_patrimoine = data_manager.charger_donnees()
        patrimoine_net = sum(c.solde if c.type_compte == 'Actif' else -abs(c.solde) for c in comptes)

        current_year = date.today().year
        current_month = date.today().month

        return render_template('dashboard.html',
                               username=current_user.id,
                               comptes=comptes,
                               patrimoine_net=format_nombre_fr(patrimoine_net),
                               current_year=current_year,
                               current_month=current_month)
    except Exception as e:
        app.logger.error(f"Erreur lors du chargement des données ou du calcul du patrimoine : {e}")
        flash(f"Une erreur est survenue lors du chargement des données du patrimoine. Détail: {str(e)}", 'danger')
        return render_template('error.html', error_message=str(e))


@app.route('/budget_mensuel', methods=['GET'])
@login_required
def budget_mensuel():
    year = request.args.get('year', type=int, default=date.today().year)
    month = request.args.get('month', type=int, default=date.today().month)

    if not (1 <= month <= 12) or not (2000 <= year <= 2100):
        flash('Mois ou année invalide.', 'danger')
        year = date.today().year
        month = date.today().month

    cle_mois_annee = f"{year:04d}-{month:02d}"

    comptes, _ = data_manager.charger_donnees() # Recharge les comptes pour avoir les dernières données
    all_budget_data = data_manager.charger_budget_donnees() # Charge toutes les données de budget

    # --- IMPORTANT : Générer les transactions récurrentes AVANT de calculer la projection ---
    _generer_transactions_recurrentes_pour_le_mois(year, month, all_budget_data, comptes, data_manager)
    # Recharger les données du budget après la génération si des modifs ont eu lieu
    all_budget_data = data_manager.charger_budget_donnees() 


    # --- Appel de la fonction de calcul du solde prévisionnel ---
    projection_results = _calculer_solde_previsionnel(year, month, comptes, all_budget_data)

    if projection_results is None:
        total_previsionnel_net = 0.0
        tresorerie_pointee = 0.0
        montant_attente = 0.0
        solde_virtuel = 0.0
        budget_categories_display = []
        transactions_display = []
        flash("Impossible de calculer le solde prévisionnel. Assurez-vous d'avoir des comptes marqués pour le suivi budgétaire.", 'info')

    else:
        total_previsionnel_net = projection_results.get('total_previsionnel_net', 0.0)
        details_pour_affichage = projection_results.get('details_pour_affichage', {})

        # Calcul des totaux actuels de trésorerie (Pointée, En Attente, Virtuel)
        comptes_suivis_budget = [c for c in comptes if c.suivi_budget]
        tresorerie_pointee = sum(c.solde if c.type_compte == 'Actif' else -abs(c.solde) for c in comptes_suivis_budget)

        transactions_non_pointees_actuelles = [t for t in _get_all_transactions_flat(all_budget_data) if not t.get('pointe', False) and _parse_date_flexible(t['date']).strftime('%Y-%m') == cle_mois_annee]
        montant_attente = sum(t.get('montant', 0.0) for t in transactions_non_pointees_actuelles)
        solde_virtuel = tresorerie_pointee + montant_attente

        # Préparation des catégories et transactions pour l'affichage (depuis les données DU MOIS)
        donnees_du_mois = all_budget_data.get(cle_mois_annee, {'categories_prevues': [], 'transactions': []})
        transactions_du_mois = donnees_du_mois.get('transactions', [])
        categories_prevues = donnees_du_mois.get('categories_prevues', [])

        realise_par_categorie = defaultdict(float)
        for trans in transactions_du_mois:
            cat_nom = trans.get('categorie', '(Non assigné)')
            if cat_nom != "(Virement)":
                realise_par_categorie[cat_nom] = realise_par_categorie.get(cat_nom, 0.0) + trans.get('montant', 0.0)

        budget_categories_display = []
        for cat_data in categories_prevues:
            nom_cat = cat_data.get('categorie')
            prevu = cat_data.get('prevu', 0.0)
            realise_brut = realise_par_categorie.get(nom_cat, 0.0)

            realise_display = abs(realise_brut) if cat_data.get('type') == 'Dépense' else realise_brut

            if cat_data.get('type') == 'Dépense':
                ecart = prevu - abs(realise_brut)
            else: # Revenu
                ecart = realise_brut - prevu

            budget_categories_display.append({
                'categorie': nom_cat,
                'prevu': format_nombre_fr(prevu),
                'realise': format_nombre_fr(realise_display),
                'reste': format_nombre_fr(ecart),
                'soldee': cat_data.get('soldee', False)
            })

        transactions_display = []
        # On n'affiche que les transactions du mois sélectionné, non pointées ou toutes si l'option est active (quand on aura l'option)
        # Pour l'instant, toutes les transactions du mois
        for trans in transactions_du_mois:
            transactions_display.append({
                'id': trans.get('id'),
                'date': trans.get('date'),
                'description': trans.get('description'),
                'categorie': trans.get('categorie'),
                'montant': format_nombre_fr(trans.get('montant')),
                'compte_affecte': trans.get('compte_affecte'),
                'pointe': "✔️" if trans.get('pointe') else ""
            })

    # Préparation des mois pour le sélecteur
    months_list = [(i, datetime(year, i, 1).strftime('%B')) for i in range(1, 13)] # Par exemple (1, 'January')

    return render_template('budget_mensuel.html',
                           username=current_user.id,
                           year=year,
                           month=month,
                           years=range(date.today().year - 5, date.today().year + 2),
                           months=months_list,
                           budget_categories=budget_categories_display,
                           transactions=transactions_display,
                           tresorerie_pointee=format_nombre_fr(tresorerie_pointee),
                           montant_attente=format_nombre_fr(montant_attente),
                           solde_virtuel=format_nombre_fr(solde_virtuel),
                           total_previsionnel_net=format_nombre_fr(total_previsionnel_net),
                           lignes_budget_futures=projection_results.get('lignes_budget_futures', []) if projection_results else [],
                           details_pour_affichage=projection_results.get('details_pour_affichage', {}) if projection_results else {} # pour le détail éventuel
                           )

@app.route('/api/budget/categorie', methods=['POST'])
def ajouter_categorie_budget_api():
    """
    API pour créer une nouvelle catégorie de budget pour un mois donné.
    Attend un JSON avec : { cle_mois_annee, categorie, prevu, type, compte_prevu }
    """
    # 1. Récupérer les données envoyées par le frontend
    data = request.get_json()
    if not data:
        return jsonify({"erreur": "Aucune donnée fournie"}), 400

    # 2. Valider les données reçues (sécurité de base)
    cle_mois_annee = data.get('cle_mois_annee')
    nom_categorie = data.get('categorie')
    montant_prevu = data.get('prevu')
    type_categorie = data.get('type')

    if not all([cle_mois_annee, nom_categorie, montant_prevu, type_categorie]):
        return jsonify({"erreur": "Données manquantes"}), 400

    try:
        # 3. Charger les données de budget existantes
        budget_data = data_manager.charger_budget_donnees()

        # 4. Vérifier si la catégorie existe déjà pour ce mois
        if cle_mois_annee in budget_data:
            categories_du_mois = budget_data[cle_mois_annee].get('categories_prevues', [])
            if any(cat['categorie'].lower() == nom_categorie.lower() for cat in categories_du_mois):
                return jsonify({"erreur": f"La catégorie '{nom_categorie}' existe déjà pour ce mois."}), 409 # 409 = Conflit

        # 5. Préparer le nouvel objet catégorie
        nouvelle_categorie = {
            "categorie": nom_categorie,
            "prevu": float(montant_prevu),
            "type": type_categorie,
            "compte_prevu": data.get('compte_prevu'),
            "soldee": False,
            "details": [] # Pour la compatibilité future avec le budget journalier
        }

        # 6. Ajouter la catégorie aux données et sauvegarder
        if cle_mois_annee not in budget_data:
             budget_data[cle_mois_annee] = {'categories_prevues': [], 'transactions': []}

        budget_data[cle_mois_annee]['categories_prevues'].append(nouvelle_categorie)
        data_manager.sauvegarder_budget_donnees(budget_data)

        # 7. Renvoyer une réponse de succès
        return jsonify({"message": "Catégorie ajoutée avec succès", "categorie": nouvelle_categorie}), 201 # 201 = Créé

    except Exception as e:
        # En cas d'erreur serveur, renvoyer une réponse claire
        print(f"ERREUR API /api/budget/categorie: {e}")
        return jsonify({"erreur": "Erreur interne du serveur"}), 500

# --- Route pour l'erreur (simple pour le moment) ---
@app.route('/error')
def error():
    return render_template('error.html')

# Ne pas lancer app.run() ici quand on utilise Gunicorn.
