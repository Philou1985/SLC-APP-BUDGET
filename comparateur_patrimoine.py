# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk
import os
import sys
import json
from collections import defaultdict

try:
    import sv_ttk
except ImportError:
    sv_ttk = None

# --- GESTION DES IMPORTS RELATIFS ---
try:
    from services import SqlDataManager
    from utils import format_nombre_fr
    from models import Compte
except ImportError:
    print("Tentative d'importation échouée, probable exécution en standalone.")


class ComparateurPatrimoineApp:
    def __init__(self, parent_root=None, db_path=None, settings=None):
        # --- GESTION DU MODE D'EXECUTION ---
        if parent_root:
            self.root = tk.Toplevel(parent_root)
            self.root.transient(parent_root)
            self.root.grab_set()
        else:
            self.root = tk.Tk()

        self.root.title("Comparateur de Patrimoine")

        # --- CORRECTION : DÉFINITION DE base_dir AU DÉBUT ---
        # On détermine le répertoire de base une seule fois, au début.
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        # --- GESTION DU THÈME CENTRALISÉE ---
        # Si les 'settings' sont passés par l'app principale, on les utilise.
        # Sinon (standalone), on les charge depuis le fichier.
        if settings is None:
             try:
                with open(os.path.join(base_dir, "settings.json"), 'r') as f:
                    settings = json.load(f)
             except (FileNotFoundError, json.JSONDecodeError):
                settings = {"theme": "light"} # Thème par défaut
        
        if sv_ttk:
            sv_ttk.set_theme(settings.get("theme", "light"))

        # --- GESTION DE LA FENETRE HAUTE DEFINITION ---
        window_width = 1100
        window_height = 700
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        center_x = int(screen_width / 2 - window_width / 2)
        center_y = int(screen_height / 2 - window_height / 2)
        self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        
        # --- GESTION DU CHEMIN DE LA BASE DE DONNEES ---
        # Le chemin est soit fourni, soit déduit de base_dir.
        if not db_path:
            db_path = os.path.join(base_dir, "budget.db")
        
        self.data_manager = SqlDataManager(db_path)
        self.comptes, self.historique = self.data_manager.charger_donnees()
        self.comptes_lookup = {c.nom: c for c in self.comptes}
        
        self.historique.sort(key=lambda x: x.get('date', ''), reverse=True)

        self.creer_widgets()
        self.populate_comboboxes()
        self.update_comparison()
        
        if parent_root:
            self.root.wait_window(self.root)

    def creer_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        selection_frame = ttk.LabelFrame(main_frame, text="Sélection des Instantanés", padding="10")
        selection_frame.pack(fill=tk.X, pady=(0, 10))
        selection_frame.columnconfigure(1, weight=1)
        selection_frame.columnconfigure(3, weight=1)

        ttk.Label(selection_frame, text="Date de référence :").grid(row=0, column=0, padx=(0, 5), pady=5, sticky=tk.W)
        self.combo1 = ttk.Combobox(selection_frame, state="readonly")
        self.combo1.grid(row=0, column=1, padx=5, pady=5, sticky=tk.EW)

        ttk.Label(selection_frame, text="Date de comparaison :").grid(row=0, column=2, padx=(20, 5), pady=5, sticky=tk.W)
        self.combo2 = ttk.Combobox(selection_frame, state="readonly")
        self.combo2.grid(row=0, column=3, padx=5, pady=5, sticky=tk.EW)
        
        self.combo1.bind("<<ComboboxSelected>>", self.update_comparison)
        self.combo2.bind("<<ComboboxSelected>>", self.update_comparison)
        
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        tab_synthese = ttk.Frame(notebook)
        tab_comptes = ttk.Frame(notebook)
        notebook.add(tab_synthese, text=' Synthèse du Patrimoine ')
        notebook.add(tab_comptes, text=' Détail par Compte ')

        self.creer_widgets_synthese(tab_synthese)
        self.creer_widgets_comptes(tab_comptes)

    def creer_widgets_synthese(self, parent_tab):
        tree_frame = ttk.Frame(parent_tab, padding=(0, 10, 0, 0))
        tree_frame.pack(fill=tk.BOTH, expand=True)
        colonnes = ('metric', 'snapshot1', 'snapshot2', 'evolution_val', 'evolution_pct')
        self.tree_synthese = ttk.Treeview(tree_frame, columns=colonnes, show='headings')
        self.tree_synthese.heading('metric', text='Indicateur')
        self.tree_synthese.heading('snapshot1', text='Instantané 1 (€)')
        self.tree_synthese.heading('snapshot2', text='Instantané 2 (€)')
        self.tree_synthese.heading('evolution_val', text='Évolution (€)')
        self.tree_synthese.heading('evolution_pct', text='Évolution (%)')
        self.tree_synthese.column('metric', width=250, anchor=tk.W)
        self.tree_synthese.column('snapshot1', width=150, anchor=tk.E)
        self.tree_synthese.column('snapshot2', width=150, anchor=tk.E)
        self.tree_synthese.column('evolution_val', width=150, anchor=tk.E)
        self.tree_synthese.column('evolution_pct', width=120, anchor=tk.E)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree_synthese.yview)
        self.tree_synthese.configure(yscroll=scrollbar.set)
        self.tree_synthese.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_synthese.tag_configure('gain', foreground='green')
        self.tree_synthese.tag_configure('perte', foreground='red')
        self.tree_synthese.tag_configure('total', font=('TkDefaultFont', 10, 'bold'))
        self.tree_synthese.tag_configure('header', font=('TkDefaultFont', 9, 'bold', 'italic'), background='#555555')

    def creer_widgets_comptes(self, parent_tab):
        action_frame = ttk.Frame(parent_tab)
        action_frame.pack(fill=tk.X, pady=(10, 5), padx=2)
        ttk.Button(action_frame, text="Tout Déplier", command=self.deplier_tout_comptes).pack(side=tk.LEFT)
        ttk.Button(action_frame, text="Tout Replier", command=self.replier_tout_comptes).pack(side=tk.LEFT, padx=5)
        
        tree_frame = ttk.Frame(parent_tab)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        colonnes = ('compte', 'solde1', 'solde2', 'evolution')
        self.tree_comptes = ttk.Treeview(tree_frame, columns=colonnes, show='headings')
        self.tree_comptes.heading('compte', text='Banque / Compte')
        self.tree_comptes.heading('solde1', text='Solde 1 (€)')
        self.tree_comptes.heading('solde2', text='Solde 2 (€)')
        self.tree_comptes.heading('evolution', text='Évolution (€)')
        self.tree_comptes.column('compte', width=400, anchor=tk.W)
        self.tree_comptes.column('solde1', width=150, anchor=tk.E)
        self.tree_comptes.column('solde2', width=150, anchor=tk.E)
        self.tree_comptes.column('evolution', width=150, anchor=tk.E)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree_comptes.yview)
        self.tree_comptes.configure(yscroll=scrollbar.set)
        self.tree_comptes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_comptes.tag_configure('gain', foreground='green')
        self.tree_comptes.tag_configure('perte', foreground='red')
        self.tree_comptes.tag_configure('subtotal', font=('TkDefaultFont', 9, 'bold'))
        self.tree_comptes.tag_configure('grandtotal', font=('TkDefaultFont', 10, 'bold'))
    
    def deplier_tout_comptes(self):
        for item_id in self.tree_comptes.get_children():
            self.tree_comptes.item(item_id, open=True)

    def replier_tout_comptes(self):
        for item_id in self.tree_comptes.get_children():
            self.tree_comptes.item(item_id, open=False)

    def populate_comboboxes(self):
        dates = [snap['date'] for snap in self.historique]
        self.combo1['values'] = dates
        self.combo2['values'] = dates
        if len(dates) >= 2:
            self.combo2.set(dates[0])
            self.combo1.set(dates[1])

    def update_comparison(self, event=None):
        date1 = self.combo1.get()
        date2 = self.combo2.get()
        if not date1 or not date2: return
        snap1 = next((s for s in self.historique if s['date'] == date1), None)
        snap2 = next((s for s in self.historique if s['date'] == date2), None)
        if not snap1 or not snap2: return
        self.update_synthese_view(snap1, snap2)
        self.update_comptes_view(snap1, snap2)

    def update_synthese_view(self, snap1, snap2):
        tree = self.tree_synthese
        for item in tree.get_children(): tree.delete(item)
        self._add_comparison_row(tree, "Patrimoine Net", snap1.get('patrimoine_net', 0.0), snap2.get('patrimoine_net', 0.0), tag='total')
        tree.insert('', 'end', values=("", "", "", "", ""), tags=('header',))
        self._add_comparison_row(tree, "Total des Actifs", snap1.get('total_actifs', 0.0), snap2.get('total_actifs', 0.0))
        self._add_comparison_row(tree, "Total des Passifs", snap1.get('total_passifs_magnitude', 0.0), snap2.get('total_passifs_magnitude', 0.0))
        tree.insert('', 'end', values=("Répartition des Actifs", "", "", "", ""), tags=('header',))
        repartition1 = snap1.get('repartition_actifs_par_classe', {})
        repartition2 = snap2.get('repartition_actifs_par_classe', {})
        all_classes = sorted(list(set(repartition1.keys()) | set(repartition2.keys())))
        for classe in all_classes:
             if classe not in ["N/A", "Non Renseigné"]:
                val1 = repartition1.get(classe, 0.0)
                val2 = repartition2.get(classe, 0.0)
                if val1 != 0 or val2 != 0:
                    self._add_comparison_row(tree, f"  {classe}", val1, val2)

    # Dans la classe ComparateurPatrimoineApp, remplacez la méthode update_comptes_view

    def update_comptes_view(self, snap1, snap2):
        """Met à jour la vue par comptes avec la logique corrigée pour l'affichage des sous-totaux."""
        tree = self.tree_comptes
        for item in tree.get_children(): tree.delete(item)

        soldes1 = snap1.get('soldes_comptes', {})
        soldes2 = snap2.get('soldes_comptes', {})
        all_account_names = set(soldes1.keys()) | set(soldes2.keys())
    
        data_par_banque = defaultdict(list)
        for nom_compte in all_account_names:
            compte_obj = self.comptes_lookup.get(nom_compte)
            banque = compte_obj.banque if compte_obj else "Banque Inconnue"
            data_par_banque[banque].append({'nom': nom_compte, 'solde1': soldes1.get(nom_compte, 0.0), 'solde2': soldes2.get(nom_compte, 0.0), 'type': compte_obj.type_compte if compte_obj else 'Actif'})
    
        for banque in sorted(data_par_banque.keys()):
            comptes_de_la_banque = data_par_banque[banque]
        
            subtotal1 = sum(c['solde1'] for c in comptes_de_la_banque)
            subtotal2 = sum(c['solde2'] for c in comptes_de_la_banque)
        
            evolution_patrimoniale_st = 0
            for c in comptes_de_la_banque:
                evo_brute = c['solde2'] - c['solde1']
                signe = -1 if c['type'] == 'Passif' else 1
                evolution_patrimoniale_st += (evo_brute * signe)

            subtotal_tags = ('subtotal',)
            if evolution_patrimoniale_st > 0.01: subtotal_tags += ('gain',)
            elif evolution_patrimoniale_st < -0.01: subtotal_tags += ('perte',)
        
            # --- CORRECTION APPLIQUÉE ICI ---
            # On affiche maintenant l'évolution patrimoniale du sous-total, et non plus la somme brute.
            parent_id = tree.insert('', 'end', values=(
                banque,
                format_nombre_fr(subtotal1),
                format_nombre_fr(subtotal2),
                f"{evolution_patrimoniale_st:+.2f}".replace('.', ',') # <-- CHANGEMENT ICI
            ), tags=subtotal_tags, open=False)

            for compte_data in sorted(comptes_de_la_banque, key=lambda x: x['nom']):
                val1, val2, evolution_brute = compte_data['solde1'], compte_data['solde2'], compte_data['solde2'] - compte_data['solde1']
                signe = -1 if compte_data['type'] == 'Passif' else 1
                evolution_patrimoniale = evolution_brute * signe
                compte_tags = ()
                if evolution_patrimoniale > 0.01: compte_tags += ('gain',)
                elif evolution_patrimoniale < -0.01: compte_tags += ('perte',)
                tree.insert(parent_id, 'end', values=(f"  {compte_data['nom']}", format_nombre_fr(val1), format_nombre_fr(val2), f"{evolution_brute:+.2f}".replace('.', ',')), tags=compte_tags)
    
        # La logique du Total Global reste inchangée et correcte
        tree.insert('', 'end', values=())
        evo_pn = snap2.get('patrimoine_net', 0.0) - snap1.get('patrimoine_net', 0.0)
        total_tags = ('grandtotal',)
        if evo_pn > 0.01: total_tags += ('gain',)
        elif evo_pn < -0.01: total_tags += ('perte',)
        tree.insert('', 'end', values=("TOTAL GLOBAL (Patrimoine Net)", format_nombre_fr(snap1.get('patrimoine_net', 0.0)), format_nombre_fr(snap2.get('patrimoine_net', 0.0)), f"{evo_pn:+.2f}".replace('.', ',')), tags=total_tags)
    def _add_comparison_row(self, tree, metric_name, val1, val2, tag=''):
        evolution_val = val2 - val1
        evolution_pct_str = "N/A"
        if val1 != 0:
            evolution_pct = (evolution_val / val1) * 100
            evolution_pct_str = f"{evolution_pct:+.2f} %".replace('.', ',')
        current_tags = (tag,)
        if evolution_val > 0.01: current_tags += ('gain',)
        elif evolution_val < -0.01: current_tags += ('perte',)
        tree.insert('', 'end', values=(metric_name, format_nombre_fr(val1), format_nombre_fr(val2), f"{evolution_val:+.2f}".replace('.', ','), evolution_pct_str), tags=current_tags)


# --- CORRECTION : SIMPLIFICATION RADICALE du point d'entrée pour le mode standalone ---
if __name__ == "__main__":
    # Gère l'affichage HD sur Windows si possible
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except (ImportError, AttributeError):
        pass # Ne fait rien sur les autres OS ou si la fonction n'existe pas
    
    # Lance l'application en mode standalone, la classe __init__ gère tout le reste
    app = ComparateurPatrimoineApp()
    app.root.mainloop()