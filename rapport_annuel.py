# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk
from datetime import datetime
import os
import calendar
from collections import defaultdict
import json
import sys

# On ne met PAS le code ctypes ici. sv_ttk le gère.

try:
    import sv_ttk
    SV_TTK_AVAILABLE = True
except ImportError:
    SV_TTK_AVAILABLE = False

from services import SqlDataManager
from utils import format_nombre_fr
from ai_service import CategorizationAI

MOIS_FRANCAIS = [
    "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
]

class YearlyReportApp:
    def __init__(self, root, base_dir):
        self.root = root
        self.root.title("Tableau de Bord Annuel")
        self.root.geometry("1550x750")

        db_path = os.path.join(base_dir, "budget.db")
        
        if not os.path.exists(db_path):
            self.root.destroy()
            tk.messagebox.showerror("Erreur", f"Base de données 'budget.db' non trouvée.")
            return

        # --- CORRECTION : La logique de thème est ICI, dans le __init__ ---
        # C'est ce qui garantit la cohérence, peu importe comment la classe est appelée.
        try:
            with open(os.path.join(base_dir, "settings.json"), 'r') as f:
                settings = json.load(f)
            if SV_TTK_AVAILABLE:
                sv_ttk.set_theme(settings.get("theme", "light"))
        except (FileNotFoundError, json.JSONDecodeError):
            print("INFO: Fichier settings.json non trouvé ou invalide.")
            if SV_TTK_AVAILABLE:
                sv_ttk.set_theme("light") # Thème par défaut
        # --- FIN CORRECTION ---

        self.data_manager = SqlDataManager(db_path)
        self.ai_service = CategorizationAI()
        
        self.create_widgets()
        self.refresh_all_data()

    # Le reste de la classe (create_widgets, refresh_all_data, etc.) est identique
    # à la version fonctionnelle que nous avions validée.
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10); main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1); main_frame.rowconfigure(1, weight=1)
        top_frame = ttk.Frame(main_frame); top_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(top_frame, text="Année :").pack(side=tk.LEFT, padx=(0, 5))
        current_year = datetime.now().year
        self.year_var = tk.StringVar(value=str(current_year))
        year_spinbox = ttk.Spinbox(top_frame, from_=current_year - 10, to=current_year + 5, textvariable=self.year_var, width=6); year_spinbox.pack(side=tk.LEFT)
        ttk.Button(top_frame, text="Rafraîchir", command=self.refresh_all_data).pack(side=tk.LEFT, padx=10)
        notebook = ttk.Notebook(main_frame); notebook.grid(row=1, column=0, sticky="nsew")
        tab_patrimoine = ttk.Frame(notebook); notebook.add(tab_patrimoine, text="Synthèse Patrimoine")
        tree_frame_pat = ttk.Frame(tab_patrimoine); tree_frame_pat.pack(fill=tk.BOTH, expand=True, pady=5)
        self.tree_patrimoine = ttk.Treeview(tree_frame_pat, show="headings")
        self.tree_patrimoine.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_pat = ttk.Scrollbar(tree_frame_pat, orient=tk.VERTICAL, command=self.tree_patrimoine.yview)
        self.tree_patrimoine.configure(yscroll=scrollbar_pat.set); scrollbar_pat.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_patrimoine.tag_configure('total', font=('TkDefaultFont', 9, 'bold')); self.tree_patrimoine.tag_configure('gain', foreground='green'); self.tree_patrimoine.tag_configure('perte', foreground='red')
        tab_budget = ttk.Frame(notebook); notebook.add(tab_budget, text="Synthèse Budgétaire")
        tab_budget.columnconfigure(0, weight=1); tab_budget.rowconfigure(2, weight=1)
        summary_frame = ttk.LabelFrame(tab_budget, text="Synthèse Annuelle du Budget", padding=10)
        summary_frame.grid(row=0, column=0, sticky='ew', pady=5)
        summary_frame.columnconfigure(1, weight=1)
        self.total_recettes_label = ttk.Label(summary_frame, text="Total Recettes : ...", foreground="green"); self.total_recettes_label.grid(row=0, column=0)
        self.total_depenses_label = ttk.Label(summary_frame, text="Total Dépenses : ...", foreground="red"); self.total_depenses_label.grid(row=0, column=1)
        self.solde_annuel_label = ttk.Label(summary_frame, text="Solde Annuel : ...", font=('TkDefaultFont', 10, 'bold')); self.solde_annuel_label.grid(row=0, column=2)
        budget_controls_frame = ttk.Frame(tab_budget, padding=(0, 5)); budget_controls_frame.grid(row=1, column=0, sticky='ew')
        self.budget_type_var = tk.StringVar(value="Dépenses")
        ttk.Radiobutton(budget_controls_frame, text="Afficher les Dépenses", variable=self.budget_type_var, value="Dépenses", command=self.load_budget_data).pack(side=tk.LEFT)
        ttk.Radiobutton(budget_controls_frame, text="Afficher les Recettes", variable=self.budget_type_var, value="Recettes", command=self.load_budget_data).pack(side=tk.LEFT, padx=20)
        tree_frame_bud = ttk.Frame(tab_budget); tree_frame_bud.grid(row=2, column=0, sticky='nsew')
        self.tree_budget = ttk.Treeview(tree_frame_bud, show="headings")
        self.tree_budget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_bud_y = ttk.Scrollbar(tree_frame_bud, orient=tk.VERTICAL, command=self.tree_budget.yview)
        self.tree_budget.configure(yscroll=scrollbar_bud_y.set)
        scrollbar_bud_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_budget.tag_configure('total', font=('TkDefaultFont', 9, 'bold'))
        self.tree_budget.tag_configure('anomaly', background='#503000')
        ia_frame = ttk.LabelFrame(tab_budget, text="Analyse IA", padding=10)
        ia_frame.grid(row=3, column=0, sticky='ew', pady=(10, 0))
        self.ia_analysis_text = tk.Text(ia_frame, height=6, wrap="word", relief="flat", state="disabled")
        self.ia_analysis_text.pack(fill=tk.X, expand=True)
    def refresh_all_data(self): self.load_patrimoine_data(); self.load_budget_data()
    def load_patrimoine_data(self):
        try: year_to_load = int(self.year_var.get())
        except (ValueError, TypeError): return
        _, historique = self.data_manager.charger_donnees()
        snapshots_prev_year = [s for s in historique if datetime.strptime(s['date'], "%Y-%m-%d").year == year_to_load - 1]
        patrimoine_net_prev = 0
        if snapshots_prev_year: snapshots_prev_year.sort(key=lambda x: x['date']); patrimoine_net_prev = snapshots_prev_year[-1].get('patrimoine_net', 0.0)
        snapshots_of_year = [s for s in historique if datetime.strptime(s['date'], "%Y-%m-%d").year == year_to_load]
        last_snapshots = {}
        for snap in snapshots_of_year:
            month_key = snap['date'][:7]
            if month_key not in last_snapshots or snap['date'] > last_snapshots[month_key]['date']: last_snapshots[month_key] = snap
        all_asset_classes = set()
        for snap in last_snapshots.values():
            if 'repartition_actifs_par_classe' in snap: all_asset_classes.update(snap['repartition_actifs_par_classe'].keys())
        sorted_asset_classes = sorted(list(all_asset_classes))
        columns = ["Mois"] + sorted_asset_classes + ["Total Actifs", "Total Passifs", "Patrimoine Net", "Variation (€)"]
        self.tree_patrimoine["columns"] = columns
        for col in columns: self.tree_patrimoine.heading(col, text=col); self.tree_patrimoine.column(col, width=120, anchor=tk.E if col != "Mois" else tk.W)
        for item in self.tree_patrimoine.get_children(): self.tree_patrimoine.delete(item)
        total_variation_annuelle = 0; final_row_data = None
        for month_num in range(1, 13):
            month_name = MOIS_FRANCAIS[month_num]; month_key = f"{year_to_load:04d}-{month_num:02d}"
            snap = last_snapshots.get(month_key)
            if snap:
                current_patrimoine_net = snap.get('patrimoine_net', 0.0); variation = current_patrimoine_net - patrimoine_net_prev
                total_variation_annuelle += variation; patrimoine_net_prev = current_patrimoine_net
                row_data = {"Mois": month_name}
                for asset_class in sorted_asset_classes: row_data[asset_class] = snap['repartition_actifs_par_classe'].get(asset_class, 0.0)
                row_data["Total Actifs"] = snap.get('total_actifs', 0.0); row_data["Total Passifs"] = snap.get('total_passifs_magnitude', 0.0)
                row_data["Patrimoine Net"] = current_patrimoine_net; row_data["Variation (€)"] = variation
                values_for_tree = [month_name] + [format_nombre_fr(row_data.get(ac, 0.0)) for ac in sorted_asset_classes] + [format_nombre_fr(row_data["Total Actifs"]), format_nombre_fr(row_data["Total Passifs"]), format_nombre_fr(row_data["Patrimoine Net"]), format_nombre_fr(row_data["Variation (€)"])]
                tag = 'gain' if variation > 0 else 'perte' if variation < 0 else ''
                self.tree_patrimoine.insert("", "end", values=values_for_tree, tags=(tag,)); final_row_data = row_data
            else: self.tree_patrimoine.insert("", "end", values=[month_name] + ["-"] * (len(columns) - 1))
        if final_row_data:
            total_values = ["TOTAL ANNUEL"] + [format_nombre_fr(final_row_data.get(ac, 0.0)) for ac in sorted_asset_classes] + [format_nombre_fr(final_row_data["Total Actifs"]), format_nombre_fr(final_row_data["Total Passifs"]), format_nombre_fr(final_row_data["Patrimoine Net"]), format_nombre_fr(total_variation_annuelle)]
            self.tree_patrimoine.insert("", "end", values=[""] * len(columns)); self.tree_patrimoine.insert("", "end", values=total_values, tags=('total',))
    def load_budget_data(self):
        try: year_to_load = int(self.year_var.get())
        except (ValueError, TypeError): return
        budget_type = self.budget_type_var.get()
        budget_data = self.data_manager.charger_budget_donnees()
        all_transactions = [t for data in budget_data.values() if isinstance(data, dict) for t in data.get('transactions', [])]
        transactions_of_year = []
        for t in all_transactions:
            try:
                date_str = t.get('date_budgetaire') or t.get('date')
                if datetime.strptime(date_str, "%Y-%m-%d").date().year == year_to_load: transactions_of_year.append(t)
            except (ValueError, TypeError): continue
        total_recettes = sum(t['montant'] for t in transactions_of_year if t['montant'] > 0 and t['categorie'] != "(Virement)")
        total_depenses = sum(t['montant'] for t in transactions_of_year if t['montant'] < 0 and t['categorie'] != "(Virement)")
        solde_annuel = total_recettes + total_depenses
        self.total_recettes_label.config(text=f"Total Recettes : +{format_nombre_fr(total_recettes)} €")
        self.total_depenses_label.config(text=f"Total Dépenses : {format_nombre_fr(total_depenses)} €")
        self.solde_annuel_label.config(text=f"Solde Annuel : {format_nombre_fr(solde_annuel)} €")
        data_by_cat = defaultdict(lambda: defaultdict(float))
        all_categories = set()
        for t in transactions_of_year:
            is_expense = t.get('montant', 0.0) < 0; is_income = t.get('montant', 0.0) > 0; cat = t.get('categorie')
            if not cat or cat == '(Virement)': continue
            if (budget_type == "Dépenses" and is_expense) or (budget_type == "Recettes" and is_income):
                all_categories.add(cat)
                month = datetime.strptime(t.get('date_budgetaire') or t.get('date'), "%Y-%m-%d").date().month
                data_by_cat[cat][month] += abs(t['montant'])
        analysis_results_anomalies = self.ai_service.analyser_budget_annuel(data_by_cat, budget_type)
        categories_anormales = {res['categorie'] for res in analysis_results_anomalies}
        sorted_categories = sorted(list(all_categories), key=lambda cat: sum(data_by_cat[cat].values()), reverse=True)
        columns = ["Catégorie"] + [MOIS_FRANCAIS[i] for i in range(1, 13)] + ["Total Annuel"]
        for item in self.tree_budget.get_children(): self.tree_budget.delete(item)
        self.tree_budget["columns"] = columns
        self.tree_budget.column("Catégorie", width=180, anchor=tk.W, stretch=tk.NO)
        self.tree_budget.heading("Catégorie", text="Catégorie")
        for col in columns[1:]: self.tree_budget.column(col, width=90, anchor=tk.E); self.tree_budget.heading(col, text=col)
        totals_by_month = defaultdict(float)
        for cat in sorted_categories:
            values = [cat]; total_cat = sum(data_by_cat[cat].values())
            for month_num in range(1, 13):
                val = data_by_cat[cat].get(month_num, 0.0)
                values.append(format_nombre_fr(val) if val != 0 else "-"); totals_by_month[month_num] += val
            values.append(format_nombre_fr(total_cat))
            tags = ('anomaly',) if cat in categories_anormales else ()
            self.tree_budget.insert("", "end", values=values, tags=tags)
        total_values = ["TOTAL"]
        for month_num in range(1, 13): total_values.append(format_nombre_fr(totals_by_month[month_num]))
        total_values.append(format_nombre_fr(sum(totals_by_month.values())))
        self.tree_budget.insert("", "end", values=[""] * len(columns))
        self.tree_budget.insert("", "end", values=total_values, tags=('total',))
        analysis_results_tendances = self.ai_service.analyser_tendances(data_by_cat)
        self.ia_analysis_text.config(state="normal")
        self.ia_analysis_text.delete("1.0", tk.END)
        self.ia_analysis_text.tag_configure("bold", font=('TkDefaultFont', 9, 'bold'))
        if analysis_results_anomalies:
            self.ia_analysis_text.insert(tk.END, "Anomalies Détectées :\n", "bold")
            self.ia_analysis_text.insert(tk.END, "\n".join([res['text'] for res in analysis_results_anomalies]) + "\n\n")
        if analysis_results_tendances:
            self.ia_analysis_text.insert(tk.END, "Tendances Annuelles :\n", "bold")
            self.ia_analysis_text.insert(tk.END, "\n".join(analysis_results_tendances))
        if not analysis_results_anomalies and not analysis_results_tendances:
             self.ia_analysis_text.insert(tk.END, "Aucune observation particulière de l'IA pour cette sélection.")
        self.ia_analysis_text.config(state="disabled")

if __name__ == "__main__":
    
    # --- DÉBUT DE LA CORRECTION DÉFINITIVE ---
    # On applique la correction HiDPI ICI, pour qu'elle ne s'exécute
    # qu'en mode autonome et n'interfère jamais avec l'application principale.
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except ImportError:
        pass
    # --- FIN DE LA CORRECTION DÉFINITIVE ---

    # On détermine le répertoire de base
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    # On crée la fenêtre principale
    root = tk.Tk()
    
    # On applique le thème
    try:
        with open(os.path.join(base_dir, "settings.json"), 'r') as f:
            settings = json.load(f)
        if SV_TTK_AVAILABLE:
            sv_ttk.set_theme(settings.get("theme", "light"))
    except (FileNotFoundError, json.JSONDecodeError):
        if SV_TTK_AVAILABLE:
            sv_ttk.set_theme("light")

    # On lance notre application
    app = YearlyReportApp(root, base_dir)
    root.mainloop()