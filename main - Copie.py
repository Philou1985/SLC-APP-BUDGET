# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from tkinter import simpledialog
import json
import sys
import os
import traceback
import shutil
from datetime import date, datetime, timedelta
import matplotlib.dates as mdates
from collections import defaultdict
import csv
from tkinter import filedialog
import uuid
import copy
import calendar
from models import Compte, LignePortefeuille
from utils import format_nombre_fr
from ui_components import (ConflictStrategyDialog, TemplateManagerWindow, 
                           ApplyTemplateDialog, VirementDialog, RecurrentTransactionManager, 
                           DetailPrevisionnelWindow, DailyBudgetCalendarDialog, 
                           HoldingEditDialog, PortfolioManagerWindow, RapportMensuelWindow,
                           SelectFromListDialog, TransactionDialog)
from services import SqlDataManager, GraphManager
from ai_service import CategorizationAI
from market_service import MarketDataService

try:
    import sv_ttk
except ImportError:
    print("ATTENTION: Le package 'sv-ttk' n'est pas installé. Le thème par défaut sera utilisé.")
    sv_ttk = None


try:
    import matplotlib
    matplotlib.use('TkAgg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
    print("INFO: Matplotlib trouvé et importé.")
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("ATTENTION : Matplotlib n'est pas installé.")

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BASE_DIR = os.path.dirname(sys.executable)
    print(f"INFO: Application lancée depuis un exécutable. Répertoire de base : {BASE_DIR}")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"INFO: Application lancée en tant que script Python. Répertoire de base : {BASE_DIR}")

class PatrimoineApp:

    def __init__(self, root):
        self.data_loaded_ok = False
        try:
            self.root = root
            self.root.title("SLC Budget et finances")
            self.LignePortefeuille = LignePortefeuille
            
            window_width = 1550
            window_height = 920
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            center_x = int(screen_width / 2 - window_width / 2.2)
            center_y = int(screen_height / 2 - window_height / 2.2)
            self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
            
            db_path = os.path.join(BASE_DIR, "budget.db")
            self.data_manager = SqlDataManager(db_path)

            settings = self.data_manager.charger_parametres()
            self.comptes, self.historique_patrimoine = self.data_manager.charger_donnees()
            self.budget_data = self.data_manager.charger_budget_donnees()
            
            self.ai_service = CategorizationAI()
            all_transactions = self._get_all_transactions()
            self.ai_service.train(all_transactions)
            
            self.market_service = MarketDataService()
            
            self.theme_var = tk.StringVar(value=settings.get("theme", "light"))
            if sv_ttk:
                sv_ttk.set_theme(self.theme_var.get())

            self.tri_budget = {'col': 'default', 'reverse': False}
            self.tri_transactions = {'col': 'date', 'reverse': True}
            
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
            self.dernier_tri_col = None
            self.dernier_tri_reverse = False

            main_notebook = ttk.Notebook(root)
            main_notebook.pack(expand=True, fill='both', padx=5, pady=5)
            self.patrimoine_tab_frame = ttk.Frame(main_notebook)
            self.budget_tab_frame = ttk.Frame(main_notebook)
            main_notebook.add(self.patrimoine_tab_frame, text='Patrimoine')
            main_notebook.add(self.budget_tab_frame, text='Budget Mensuel')
            
            self.creer_widgets_patrimoine()
            self.creer_widgets_budget()
            
            if MATPLOTLIB_AVAILABLE:
                figures_axes_canvases = {
                    'camembert_classe': {'fig': self.fig_camembert_classe, 'ax': self.ax_camembert_classe, 'canvas': self.canvas_camembert_classe},
                    'banque': {'fig': self.fig_banque, 'ax': self.ax_banque, 'canvas': self.canvas_banque},
                    'historique': {'fig': self.fig_historique, 'ax': self.ax_historique, 'canvas': self.canvas_historique},
                    'historique_perso': {'fig': self.fig_historique_perso, 'ax': self.ax_historique_perso, 'canvas': self.canvas_historique_perso},
                    'depenses': {'fig': self.fig_depenses, 'ax': self.ax_depenses, 'canvas': self.canvas_depenses},
                    'recettes': {'fig': self.fig_recettes, 'ax': self.ax_recettes, 'canvas': self.canvas_recettes},
                    'evolution': {'fig': self.fig_evolution, 'ax': self.ax_evolution, 'canvas': self.canvas_evolution},
                    'vs': {'fig': self.fig_vs, 'ax': self.ax_vs, 'canvas': self.canvas_vs}
                }
                self.graph_manager = GraphManager(figures_axes_canvases)
            else:
                self.graph_manager = None

            self.mettre_a_jour_toutes_les_vues()
            
            print("INFO: __init__ - Initialisation terminée.")

        except Exception as e:
            print(f"ERREUR FATALE DANS __INIT__: {e}")
            traceback.print_exc()
            messagebox.showerror("Erreur Fatale", f"Erreur critique au démarrage:\n{e}")
            if hasattr(self, 'root') and self.root.winfo_exists():
                self.root.destroy()

    def changer_theme(self):
        if sv_ttk:
            theme = self.theme_var.get()
            sv_ttk.set_theme(theme)
            self.data_manager.sauvegarder_parametres({"theme": theme})

    def creer_widgets_patrimoine(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Fichier", menu=file_menu)
        file_menu.add_command(label="Prendre un Instantané", command=self.prendre_instantane, accelerator="Ctrl+I")
        file_menu.add_command(label="Sauvegarder les Données", command=self.sauvegarder_donnees_menu, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Exporter Comptes (CSV)...", command=self.exporter_csv)
        file_menu.add_command(label="Importer Comptes (CSV)...", command=self.importer_csv_comptes)
        file_menu.add_separator()
        file_menu.add_command(label="Exporter Historique (CSV)...", command=self.exporter_csv_historique)
        file_menu.add_command(label="Importer Historique (CSV)...", command=self.importer_csv_historique)
        file_menu.add_separator()
        file_menu.add_command(label="Quitter", command=self.on_closing)
        
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Outils", menu=tools_menu)
        tools_menu.add_command(label="Gérer les Transactions Récurrentes...", command=self.ouvrir_gestion_transactions_recurrentes)
        tools_menu.add_command(label="Détecter les récurrences...", command=self.lancer_detection_recurrences)
        tools_menu.add_command(label="Fusionner des Catégories de Budget...", command=self.ouvrir_fenetre_fusion_categories)
        tools_menu.add_separator()
        tools_menu.add_command(label="Purger les anciennes transactions...", command=self.ouvrir_fenetre_purge_transactions)

        options_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Options", menu=options_menu)
        theme_submenu = tk.Menu(options_menu, tearoff=0)
        options_menu.add_cascade(label="Thème", menu=theme_submenu)
        theme_submenu.add_radiobutton(label="Clair", variable=self.theme_var, value="light", command=self.changer_theme)
        theme_submenu.add_radiobutton(label="Sombre", variable=self.theme_var, value="dark", command=self.changer_theme)
        
        self.root.bind("<Control-s>", lambda event: self.sauvegarder_donnees_menu())
        self.root.bind("<Control-S>", lambda event: self.sauvegarder_donnees_menu())
        self.root.bind("<Control-i>", lambda event: self.prendre_instantane())
        self.root.bind("<Control-I>", lambda event: self.prendre_instantane())

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="?", menu=help_menu)
        help_menu.add_command(label="À propos", command=self.afficher_a_propos)
        help_menu.add_command(label="Afficher la notice", command=self.ouvrir_notice)
        
        main_pane = ttk.PanedWindow(self.patrimoine_tab_frame, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        left_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, weight=3)
        
        view_options_frame = ttk.Frame(left_frame)
        view_options_frame.pack(fill=tk.X, pady=(0,5))
        ttk.Label(view_options_frame, text="Grouper par:").pack(side=tk.LEFT, padx=(0,5))
        self.view_mode_var = tk.StringVar(value="Banque")
        view_mode_combo = ttk.Combobox(view_options_frame, textvariable=self.view_mode_var, values=["Type Détaillé", "Banque"], state="readonly", width=20)
        view_mode_combo.pack(side=tk.LEFT)
        view_mode_combo.bind("<<ComboboxSelected>>", self.changer_vue_treeview)
        
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        colonnes = ('nom', 'detail_col', 'solde')
        self.tree = ttk.Treeview(tree_frame, columns=colonnes, show='headings', selectmode=tk.EXTENDED)
        self.col_text_map_type = {'nom': 'Nom Compte/Catégorie', 'detail_col': 'Banque/Détail S-Total', 'solde': 'Solde (€)'}
        self.col_text_map_banque = {'nom': 'Nom Compte/Banque', 'detail_col': 'Type/Détail Solde Net', 'solde': 'Solde (€)'}
        self.update_treeview_headers()
        self.tree.column('nom', width=280, minwidth=200)
        self.tree.column('detail_col', width=150, minwidth=120)
        self.tree.column('solde', width=120, anchor=tk.E, minwidth=100)
        self.tree.tag_configure('group_header', font=('TkDefaultFont', 10, 'bold'))
        self.tree.tag_configure('sub_group_header', font=('TkDefaultFont', 9, 'italic'))
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Double-1>", self.lancer_edition_compte)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_action_buttons_state())
        
        action_buttons_frame = ttk.Frame(left_frame)
        action_buttons_frame.pack(fill=tk.X, pady=(5,0))
        ttk.Button(action_buttons_frame, text="Ajouter", command=lambda: self.ouvrir_fenetre_gestion_compte(None)).grid(row=0, column=0, sticky=tk.W, padx=(0,2))
        ttk.Button(action_buttons_frame, text="Supprimer", command=self.supprimer_compte_selectionne).grid(row=0, column=1, sticky=tk.W, padx=2)
        ttk.Button(action_buttons_frame, text="Modifier", command=self.lancer_edition_compte).grid(row=0, column=2, sticky=tk.W, padx=2)
        self.bouton_echeancier = ttk.Button(action_buttons_frame, text="Importer Échéancier...", command=self.importer_echeancier, state=tk.DISABLED)
        self.bouton_echeancier.grid(row=0, column=3, sticky=tk.W, padx=2)

        expand_collapse_frame = ttk.Frame(left_frame)
        expand_collapse_frame.pack(fill=tk.X, pady=(2,0))
        ttk.Button(expand_collapse_frame, text="Tout Déplier", command=self.deplier_tout).pack(side=tk.LEFT, padx=(0,2))
        ttk.Button(expand_collapse_frame, text="Tout Replier", command=self.replier_tout).pack(side=tk.LEFT, padx=2)
        ttk.Button(expand_collapse_frame, text="Actualiser les Cours", command=self.lancer_actualisation_globale).pack(side=tk.LEFT, padx=10)
        self.label_patrimoine = ttk.Label(expand_collapse_frame, text="Patrimoine Net : 0,00 €", font=("Arial", 12, "bold"))
        self.label_patrimoine.pack(side=tk.RIGHT, padx=(10, 0))
        
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=2)
        self.notebook_graphiques = ttk.Notebook(right_frame)
        self.tab_camembert_classe = ttk.Frame(self.notebook_graphiques)
        self.tab_banque = ttk.Frame(self.notebook_graphiques)
        self.tab_historique = ttk.Frame(self.notebook_graphiques)
        self.notebook_graphiques.add(self.tab_camembert_classe, text='Actifs par Classe')
        self.notebook_graphiques.add(self.tab_banque, text='Actifs par Banque')
        self.notebook_graphiques.add(self.tab_historique, text='Évolution Patrimoine')
        self.notebook_graphiques.pack(expand=True, fill='both')
        self.canvas_camembert_classe = None
        self.fig_camembert_classe = None
        self.ax_camembert_classe = None
        self.canvas_historique = None
        self.fig_historique = None
        self.ax_historique = None
        self.canvas_banque = None
        self.fig_banque = None
        self.ax_banque = None
        
        self.tab_historique_perso = ttk.Frame(self.notebook_graphiques)
        self.notebook_graphiques.add(self.tab_historique_perso, text='Historique Personnalisé')
        pane_hist_perso = ttk.PanedWindow(self.tab_historique_perso, orient=tk.HORIZONTAL)
        pane_hist_perso.pack(fill=tk.BOTH, expand=True)
        list_frame_hist = ttk.Frame(pane_hist_perso, padding=5)
        pane_hist_perso.add(list_frame_hist, weight=1)
        ttk.Label(list_frame_hist, text="Sélectionner les comptes :").pack(anchor=tk.W)
        
        canvas_comptes = tk.Canvas(list_frame_hist)
        scrollbar_comptes = ttk.Scrollbar(list_frame_hist, orient="vertical", command=canvas_comptes.yview)
        self.frame_checkboxes = ttk.Frame(canvas_comptes)
        self.frame_checkboxes.bind("<Configure>", lambda e: canvas_comptes.configure(scrollregion=canvas_comptes.bbox("all")))
        canvas_comptes.create_window((0, 0), window=self.frame_checkboxes, anchor="nw")
        canvas_comptes.configure(yscrollcommand=scrollbar_comptes.set)
        canvas_comptes.pack(side="left", fill="both", expand=True)
        scrollbar_comptes.pack(side="right", fill="y")
        
        self.vars_comptes_historique = {}
        for compte in sorted(self.comptes, key=lambda c: c.nom.lower()):
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(self.frame_checkboxes, text=compte.nom, variable=var, command=self.mettre_a_jour_graphique_historique_personnalise)
            cb.pack(anchor=tk.NW, padx=5)
            self.vars_comptes_historique[compte.nom] = var

        graph_frame_hist = ttk.Frame(pane_hist_perso)
        pane_hist_perso.add(graph_frame_hist, weight=4)

        if MATPLOTLIB_AVAILABLE:
            self.fig_historique_perso = Figure(figsize=(5, 4), dpi=100)
            self.ax_historique_perso = self.fig_historique_perso.add_subplot(111)
            self.canvas_historique_perso = FigureCanvasTkAgg(self.fig_historique_perso, master=graph_frame_hist)
            self.canvas_historique_perso.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        else:
            ttk.Label(graph_frame_hist, text="Graphique indisponible.", justify=tk.CENTER).pack(padx=20, pady=50)
        
        if MATPLOTLIB_AVAILABLE:
            try:
                plt.ioff()
                self.fig_camembert_classe, self.ax_camembert_classe = plt.subplots()
                self.canvas_camembert_classe = FigureCanvasTkAgg(self.fig_camembert_classe, master=self.tab_camembert_classe)
                self.canvas_camembert_classe.get_tk_widget().pack(side=tk.TOP,fill=tk.BOTH,expand=True)
                
                self.fig_banque, self.ax_banque = plt.subplots()
                self.canvas_banque = FigureCanvasTkAgg(self.fig_banque, master=self.tab_banque)
                self.canvas_banque.get_tk_widget().pack(side=tk.TOP,fill=tk.BOTH,expand=True)
                
                self.fig_historique, self.ax_historique = plt.subplots()
                self.canvas_historique = FigureCanvasTkAgg(self.fig_historique, master=self.tab_historique)
                self.canvas_historique.get_tk_widget().pack(side=tk.TOP,fill=tk.BOTH,expand=True)
            except Exception as e:
                print(f"ERREUR Init Graphiques: {e}")
                self.canvas_camembert_classe = self.canvas_historique = self.canvas_banque = None
        
        if not self.canvas_camembert_classe: ttk.Label(self.tab_camembert_classe, text="Graphique indisponible.").pack(padx=20, pady=50)
        if not self.canvas_banque: ttk.Label(self.tab_banque, text="Graphique indisponible.").pack(padx=20, pady=50)
        if not self.canvas_historique: ttk.Label(self.tab_historique, text="Graphique indisponible.").pack(padx=20, pady=50)

    def creer_widgets_budget(self):
        alertes_frame = ttk.Frame(self.budget_tab_frame, padding="10 5")
        alertes_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.label_alertes_decouvert = ttk.Label(alertes_frame, text="", font=("Arial", 9, "bold"), justify=tk.LEFT)
        self.label_alertes_decouvert.pack(anchor=tk.W)

        date_frame = ttk.Frame(self.budget_tab_frame, padding="10")
        date_frame.pack(fill=tk.X, side=tk.TOP)
        ttk.Label(date_frame, text="Sélectionner un mois :").pack(side=tk.LEFT)
        current_year = date.today().year
        self.budget_annee_var = tk.StringVar(value=str(current_year))
        self.budget_annee_combo = ttk.Combobox(date_frame, textvariable=self.budget_annee_var, values=[str(y) for y in range(current_year - 5, current_year + 6)], state="readonly", width=6)
        self.budget_annee_combo.pack(side=tk.LEFT, padx=5)
        self.budget_mois_var = tk.StringVar(value=f"{date.today().month:02d}")
        self.budget_mois_combo = ttk.Combobox(date_frame, textvariable=self.budget_mois_var, values=[f"{m:02d}" for m in range(1, 13)], state="readonly", width=4)
        self.budget_mois_combo.pack(side=tk.LEFT)
        self.budget_annee_combo.bind("<<ComboboxSelected>>", self.mettre_a_jour_toutes_les_vues)
        self.budget_mois_combo.bind("<<ComboboxSelected>>", self.mettre_a_jour_toutes_les_vues)
        
        summary_frame = ttk.Frame(self.budget_tab_frame, padding="5")
        summary_frame.pack(fill=tk.X, side=tk.TOP)
        self.label_tresorerie_pointee = ttk.Label(summary_frame, text="Trésorerie Pointée : ...", font=("Arial", 10, "bold"))
        self.label_tresorerie_pointee.pack(side=tk.LEFT, padx=5)
        detail_button = ttk.Button(summary_frame, text="Détail", command=self.afficher_detail_tresorerie_pointee)
        detail_button.pack(side=tk.LEFT, padx=(0, 15))
        self.label_transactions_attente = ttk.Label(summary_frame, text="En Attente : ...")
        self.label_transactions_attente.pack(side=tk.LEFT)
        self.label_solde_virtuel = ttk.Label(summary_frame, text="Solde Courant Virtuel : ...", font=("Arial", 10, "bold"))
        self.label_solde_virtuel.pack(side=tk.LEFT, padx=20)
        
        prevision_frame = ttk.Frame(summary_frame)
        prevision_frame.pack(side=tk.LEFT, padx=20)
        self.label_solde_previsionnel = ttk.Label(prevision_frame, text="Solde Prévisionnel Fin de Mois : ...", font=("Arial", 10, "bold"))
        self.label_solde_previsionnel.pack(side=tk.LEFT, anchor=tk.W)
        self.detail_previsionnel_button = ttk.Button(prevision_frame, text="Détail", command=self.afficher_detail_solde_previsionnel, width=8)
        self.detail_previsionnel_button.pack(side=tk.LEFT, padx=(5,0))
        
        main_budget_pane = ttk.PanedWindow(self.budget_tab_frame, orient=tk.HORIZONTAL)
        main_budget_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        left_pane_tables = ttk.Frame(main_budget_pane)
        main_budget_pane.add(left_pane_tables, weight=2)

        budget_pane_vertical = ttk.PanedWindow(left_pane_tables, orient=tk.VERTICAL)
        budget_pane_vertical.pack(fill=tk.BOTH, expand=True)
        
        categories_frame = ttk.Frame(budget_pane_vertical)
        budget_pane_vertical.add(categories_frame, weight=1)
        ttk.Label(categories_frame, text="Budget du Mois", font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W, pady=(0,5))
        
        budget_tree_frame = ttk.Frame(categories_frame)
        budget_tree_frame.pack(fill=tk.BOTH, expand=True)
        colonnes_budget = ('categorie', 'previsionnel', 'realise', 'reste')
        self.budget_tree = ttk.Treeview(budget_tree_frame, columns=colonnes_budget, show='headings', selectmode=tk.EXTENDED)
        self.budget_tree.heading('categorie', text='Catégorie', command=lambda: self.definir_tri_budget('categorie'))
        self.budget_tree.heading('previsionnel', text='Prévisionnel (€)', command=lambda: self.definir_tri_budget('previsionnel'))
        self.budget_tree.heading('realise', text='Réalisé (€)', command=lambda: self.definir_tri_budget('realise'))
        self.budget_tree.heading('reste', text='Gain / Perte (€)', command=lambda: self.definir_tri_budget('reste'))
        self.budget_tree.column('categorie', width=250)
        self.budget_tree.column('previsionnel', width=120, anchor=tk.E)
        self.budget_tree.column('realise', width=120, anchor=tk.E)
        self.budget_tree.column('reste', width=120, anchor=tk.E)
        self.budget_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        budget_scrollbar = ttk.Scrollbar(budget_tree_frame, orient=tk.VERTICAL, command=self.budget_tree.yview)
        self.budget_tree.config(yscrollcommand=budget_scrollbar.set)
        budget_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.budget_tree.tag_configure('gain', foreground='green')
        self.budget_tree.tag_configure('perte', foreground='red')
        self.budget_tree.tag_configure('soldee', font=('TkDefaultFont', 9, 'overstrike'))
        
        self.menu_categorie = tk.Menu(self.root, tearoff=0)
        self.menu_categorie.add_command(label="Solder / Ré-ouvrir la catégorie", command=self.solder_ou_reouvrir_categorie)
        
        def afficher_menu_categorie(event):
            item_id = self.budget_tree.identify_row(event.y)
            if item_id:
                self.budget_tree.selection_set(item_id)
                self.menu_categorie.post(event.x_root, event.y_root)

        self.budget_tree.bind("<Button-3>", afficher_menu_categorie)
        self.budget_tree.bind("<Double-1>", self.modifier_categorie_budget)

        budget_buttons_frame = ttk.Frame(categories_frame)
        budget_buttons_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0))
        ttk.Button(budget_buttons_frame, text="Appliquer un Modèle", command=self.appliquer_modele_budget).pack(side=tk.LEFT, padx=(0,15))
        ttk.Button(budget_buttons_frame, text="Ajouter Catégorie", command=self.ajouter_categorie_budget).pack(side=tk.LEFT)
        ttk.Button(budget_buttons_frame, text="Modifier", command=self.modifier_categorie_budget).pack(side=tk.LEFT, padx=5)
        ttk.Button(budget_buttons_frame, text="Supprimer", command=self.supprimer_categorie_budget).pack(side=tk.LEFT)
        ttk.Separator(budget_buttons_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=(15, 5), fill='y')
        ttk.Button(budget_buttons_frame, text="Gérer les Modèles...", command=self.ouvrir_gestion_modeles).pack(side=tk.LEFT)
        ttk.Button(budget_buttons_frame, text="Rapport Mensuel", command=self.generer_rapport_mensuel).pack(side=tk.LEFT, padx=15)
        
        transactions_frame = ttk.Frame(budget_pane_vertical)
        budget_pane_vertical.add(transactions_frame, weight=2)
        
        ttk.Label(transactions_frame, text="Transactions du Mois", font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W, pady=(5,5))
        
        trans_tree_frame = ttk.Frame(transactions_frame)
        trans_tree_frame.pack(fill=tk.BOTH, expand=True)
        colonnes_transactions = ('pointe', 'date', 'description', 'categorie', 'montant', 'compte')
        self.transactions_tree = ttk.Treeview(trans_tree_frame, columns=colonnes_transactions, show='headings', selectmode=tk.EXTENDED)
        self.transactions_tree.heading('pointe', text='P', command=lambda: self.definir_tri_transactions('pointe'))
        self.transactions_tree.heading('date', text='Date', command=lambda: self.definir_tri_transactions('date'))
        self.transactions_tree.heading('description', text='Description', command=lambda: self.definir_tri_transactions('description'))
        self.transactions_tree.heading('categorie', text='Catégorie', command=lambda: self.definir_tri_transactions('categorie'))
        self.transactions_tree.heading('montant', text='Montant (€)', command=lambda: self.definir_tri_transactions('montant'))
        self.transactions_tree.heading('compte', text='Compte', command=lambda: self.definir_tri_transactions('compte'))
        self.transactions_tree.column('pointe', width=30, anchor=tk.CENTER)
        self.transactions_tree.column('date', width=80, anchor=tk.CENTER)
        self.transactions_tree.column('description', width=200)
        self.transactions_tree.column('categorie', width=100, anchor=tk.CENTER)
        self.transactions_tree.column('montant', width=80, anchor=tk.E)
        self.transactions_tree.column('compte', width=120)
        self.transactions_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        trans_scrollbar = ttk.Scrollbar(trans_tree_frame, orient=tk.VERTICAL, command=self.transactions_tree.yview)
        self.transactions_tree.config(yscrollcommand=trans_scrollbar.set)
        trans_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.transactions_tree.bind("<Double-1>", self.modifier_transaction)
        
        transactions_buttons_frame = ttk.Frame(transactions_frame)
        transactions_buttons_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        ttk.Button(transactions_buttons_frame, text="Ajouter", command=self.ajouter_transaction).pack(side=tk.LEFT)
        ttk.Button(transactions_buttons_frame, text="Virement", command=self.ajouter_virement).pack(side=tk.LEFT, padx=5)
        ttk.Button(transactions_buttons_frame, text="Modifier", command=self.modifier_transaction).pack(side=tk.LEFT, padx=5)
        ttk.Button(transactions_buttons_frame, text="Supprimer", command=self.supprimer_transaction).pack(side=tk.LEFT, padx=5)
        ttk.Button(transactions_buttons_frame, text="Solder Carte Différée", command=self.solder_carte_differee).pack(side=tk.LEFT, padx=5)
        ttk.Separator(transactions_buttons_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=(15, 5), fill='y')
        ttk.Button(transactions_buttons_frame, text="Pointer Sélection", command=self.pointer_transactions).pack(side=tk.LEFT)
        self.afficher_pointees_var = tk.BooleanVar(value=False)
        show_pointed_check = ttk.Checkbutton(transactions_buttons_frame, text="Afficher les pointées", variable=self.afficher_pointees_var, command=self.mettre_a_jour_toutes_les_vues)
        show_pointed_check.pack(side=tk.RIGHT, padx=5)
        
        right_pane_graphs = ttk.Frame(main_budget_pane)
        main_budget_pane.add(right_pane_graphs, weight=1)

        self.notebook_budget_graphs = ttk.Notebook(right_pane_graphs)
        self.notebook_budget_graphs.pack(fill=tk.BOTH, expand=True)
        self.tab_graph_depenses = ttk.Frame(self.notebook_budget_graphs)
        self.tab_graph_recettes = ttk.Frame(self.notebook_budget_graphs)
        self.tab_graph_evolution = ttk.Frame(self.notebook_budget_graphs)
        self.tab_graph_vs = ttk.Frame(self.notebook_budget_graphs)
        self.notebook_budget_graphs.add(self.tab_graph_depenses, text="Dépenses")
        self.notebook_budget_graphs.add(self.tab_graph_recettes, text="Recettes")
        self.notebook_budget_graphs.add(self.tab_graph_evolution, text="Évolution")
        self.notebook_budget_graphs.add(self.tab_graph_vs, text="Budget/Réalisé")

        if MATPLOTLIB_AVAILABLE:
            self.fig_depenses, self.ax_depenses = plt.subplots()
            self.canvas_depenses = FigureCanvasTkAgg(self.fig_depenses, master=self.tab_graph_depenses)
            self.canvas_depenses.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            self.fig_recettes, self.ax_recettes = plt.subplots()
            self.canvas_recettes = FigureCanvasTkAgg(self.fig_recettes, master=self.tab_graph_recettes)
            self.canvas_recettes.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            self.fig_evolution, self.ax_evolution = plt.subplots()
            self.canvas_evolution = FigureCanvasTkAgg(self.fig_evolution, master=self.tab_graph_evolution)
            self.canvas_evolution.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            self.fig_vs, self.ax_vs = plt.subplots()
            self.canvas_vs = FigureCanvasTkAgg(self.fig_vs, master=self.tab_graph_vs)
            self.canvas_vs.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        else:
            for tab in [self.tab_graph_depenses, self.tab_graph_recettes, self.tab_graph_evolution, self.tab_graph_vs]:
                ttk.Label(tab, text="Matplotlib non disponible.").pack()

    def mettre_a_jour_vue_budget(self, resultats_projection=None):
        if not hasattr(self, 'budget_tree') or not hasattr(self, 'transactions_tree'): return

        for item in self.budget_tree.get_children(): self.budget_tree.delete(item)
        for item in self.transactions_tree.get_children(): self.transactions_tree.delete(item)

        try:
            annee_selectionnee = int(self.budget_annee_var.get())
            mois_selectionne = int(self.budget_mois_var.get())
            cle_mois_annee = f"{annee_selectionnee:04d}-{mois_selectionne:02d}"
        except (ValueError, TypeError):
            return

        if cle_mois_annee not in self.budget_data:
            self.budget_data[cle_mois_annee] = {'categories_prevues': [], 'transactions': []}

        self.generer_transactions_recurrentes_pour_le_mois(annee_selectionnee, mois_selectionne)
        
        comptes_suivis_budget = [c for c in self.comptes if c.suivi_budget]
        tresorerie_pointee_correcte = 0.0
        for compte in comptes_suivis_budget:
            if compte.type_compte == 'Actif':
                tresorerie_pointee_correcte += compte.solde
            elif compte.type_compte == 'Passif':
                tresorerie_pointee_correcte -= abs(compte.solde)
        
        transactions_du_mois_non_pointees = [
            t for t in self.budget_data.get(cle_mois_annee, {}).get('transactions', [])
            if not t.get('pointe', False)
        ]
        montant_attente_correct = sum(t.get('montant', 0.0) for t in transactions_du_mois_non_pointees)
        
        solde_virtuel_correct = tresorerie_pointee_correcte + montant_attente_correct

        self.label_tresorerie_pointee.config(text=f"Trésorerie Pointée : {format_nombre_fr(tresorerie_pointee_correcte)} €")
        self.label_transactions_attente.config(text=f"En Attente : {format_nombre_fr(montant_attente_correct)} €")
        self.label_solde_virtuel.config(text=f"Solde Courant Virtuel : {format_nombre_fr(solde_virtuel_correct)} €")

        if resultats_projection:
             solde_previsionnel_net = resultats_projection.get('total_previsionnel_net', 0.0)
             self.label_solde_previsionnel.config(text=f"Solde Prévisionnel Fin de Mois : {format_nombre_fr(solde_previsionnel_net)} €")
        
        donnees_du_mois = self.budget_data.get(cle_mois_annee, {})
        transactions_du_mois = donnees_du_mois.get('transactions', [])
        
        transactions_reportees = []
        ids_deja_presentes = {t.get('id') for t in transactions_du_mois}
        for cle, data in self.budget_data.items():
            if cle.startswith("_") or cle == cle_mois_annee or not isinstance(data, dict): continue
            try:
                annee_cle, mois_cle = map(int, cle.split('-'))
                if date(annee_cle, mois_cle, 1) < date(annee_selectionnee, mois_selectionne, 1):
                    for t in data.get('transactions', []):
                        if not t.get('pointe', False) and t.get('id') not in ids_deja_presentes:
                            transactions_reportees.append(t)
                            ids_deja_presentes.add(t.get('id'))
            except (ValueError, TypeError): continue

        toutes_les_transactions_pour_calculs = transactions_du_mois + transactions_reportees
        transactions_non_pointees_global = [t for t in toutes_les_transactions_pour_calculs if not t.get('pointe', False)]

        realise_par_categorie = defaultdict(float)
        for trans in toutes_les_transactions_pour_calculs: 
            cat_nom = trans.get('categorie', '(Non assigné)')
            if cat_nom != "(Virement)":
                realise_par_categorie[cat_nom] += trans.get('montant', 0.0)
        
        categories_prevues = donnees_du_mois.get('categories_prevues', [])
        cat_a_afficher = {cat['categorie']: cat for cat in categories_prevues}
        for cat_nom, montant_realise in realise_par_categorie.items():
            if cat_nom not in cat_a_afficher and cat_nom != '(Non assigné)' and montant_realise != 0:
                cat_a_afficher[cat_nom] = {'categorie': cat_nom, 'prevu': 0.0, 'type': 'Dépense' if montant_realise < 0 else 'Revenu'}
        if '(Non assigné)' in realise_par_categorie and realise_par_categorie['(Non assigné)'] != 0:
             cat_a_afficher['(Non assigné)'] = {'categorie': '(Non assigné)', 'prevu': 0.0, 'type': 'Dépense'}

        liste_categories_budget = []
        for cat_nom, cat_data in cat_a_afficher.items():
            cat_data['nom_categorie'] = cat_nom
            realise_brut = realise_par_categorie.get(cat_nom, 0.0)
            cat_data['realise_abs'] = abs(realise_brut)
            if cat_data.get('type', 'Dépense') == 'Dépense':
                cat_data['ecart'] = cat_data.get('prevu', 0.0) - abs(realise_brut)
            else:
                cat_data['ecart'] = abs(realise_brut) - cat_data.get('prevu', 0.0)
            liste_categories_budget.append(cat_data)
        
        col_tri_budget = self.tri_budget['col']
        if col_tri_budget == 'default':
            liste_categories_budget.sort(key=lambda c: (c.get('soldee', False), c['nom_categorie'].lower()))
        else:
            key_func = None
            if col_tri_budget == 'categorie': key_func = lambda c: c['nom_categorie'].lower()
            elif col_tri_budget == 'previsionnel': key_func = lambda c: c.get('prevu', 0.0)
            elif col_tri_budget == 'realise': key_func = lambda c: c['realise_abs']
            elif col_tri_budget == 'reste': key_func = lambda c: c['ecart']
            if key_func:
                liste_categories_budget.sort(key=key_func, reverse=self.tri_budget['reverse'])
        
        self._update_header_arrows(self.budget_tree, self.tri_budget)
        
        for cat_data in liste_categories_budget:
            tags_visuels = []
            if cat_data['ecart'] > 0: tags_visuels.append('gain')
            elif cat_data['ecart'] < 0: tags_visuels.append('perte')
            if cat_data.get('soldee', False): tags_visuels.append('soldee')
            ecart_str = f"+{format_nombre_fr(cat_data['ecart'])}" if cat_data['ecart'] > 0 else format_nombre_fr(cat_data['ecart'])
            self.budget_tree.insert('', tk.END, values=(
                cat_data['nom_categorie'], 
                format_nombre_fr(cat_data.get('prevu', 0.0)) + " €", 
                format_nombre_fr(cat_data['realise_abs']) + " €", 
                f"{ecart_str} €"
            ), tags=tuple(tags_visuels))

        if self.afficher_pointees_var.get():
            transactions_a_afficher = toutes_les_transactions_pour_calculs
        else:
            transactions_a_afficher = transactions_non_pointees_global

        col_tri_trans = self.tri_transactions['col']
        key_func_trans = None
        if col_tri_trans == 'date': key_func_trans = lambda t: t.get('date', '')
        elif col_tri_trans == 'montant': key_func_trans = lambda t: t.get('montant', 0.0)
        else: key_func_trans = lambda t: str(t.get(col_tri_trans, '')).lower()
        if key_func_trans:
            transactions_a_afficher.sort(key=key_func_trans, reverse=self.tri_transactions['reverse'])
        
        self._update_header_arrows(self.transactions_tree, self.tri_transactions)

        for trans in transactions_a_afficher:
            montant_formatte = format_nombre_fr(trans.get('montant', 0.0)) + " €"
            pointe_str = "✔️" if trans.get('pointe') else ""
            tags = []
            try:
                trans_date_obj = datetime.strptime(trans.get('date'), "%Y-%m-%d").date()
                if trans_date_obj.year != annee_selectionnee or trans_date_obj.month != mois_selectionne:
                    tags.append('reporte_style')
            except (ValueError, TypeError): pass
            if trans.get('categorie') == "(Virement)": tags.append('virement_style')
            if trans.get('origine') in ['recurrente', 'echeancier']: tags.append('recurrente_style')
            self.transactions_tree.insert('', tk.END, iid=trans.get('id'), values=(
                pointe_str, trans.get('date', ''), trans.get('description', ''), 
                trans.get('categorie', ''), montant_formatte, trans.get('compte_affecte', '')
            ), tags=tuple(tags))
        
        self.transactions_tree.tag_configure('virement_style', foreground='blue')
        self.transactions_tree.tag_configure('recurrente_style', foreground='grey')
        self.transactions_tree.tag_configure('reporte_style', foreground='orange')

        self.verifier_et_afficher_alertes_decouvert()
    
    def afficher_detail_tresorerie_pointee(self):
        comptes_budget = [c for c in self.comptes if c.suivi_budget]
        if not comptes_budget:
            messagebox.showinfo("Détail Trésorerie Pointée", "Aucun compte n'est actuellement marqué pour le suivi budgétaire.", parent=self.root)
            return
        detail_message = "Détail de la Trésorerie Pointée\n(Soldes actuels des comptes suivis)\n----------------------------------------------\n"
        total = 0.0
        for compte in comptes_budget:
            solde_a_ajouter = compte.solde if compte.type_compte == 'Actif' else -abs(compte.solde)
            detail_message += f"- {compte.nom} ({compte.banque}): {format_nombre_fr(compte.solde)} €\n"
            total += solde_a_ajouter
        detail_message += "----------------------------------------------\n"
        detail_message += f"TOTAL POINTÉ : {format_nombre_fr(total)} €"
        messagebox.showinfo("Détail Trésorerie Pointée", detail_message, parent=self.root)

    def importer_csv_historique(self):
        filename = filedialog.askopenfilename(title="Ouvrir un fichier CSV d'historique", filetypes=[("Fichiers CSV (*.csv)", "*.csv"), ("Tous les fichiers (*.*)", "*.*")])
        if not filename: return
        entrees_ajoutees, entrees_mises_a_jour, lignes_ignorees, modifications_effectuees = 0, 0, 0, False
        erreurs_detaillees = []
        expected_headers = ["Date", "Patrimoine Net", "Total Actifs", "Total Passifs Magnitude"]
        try:
            lignes_csv_temp = []
            header = None
            with open(filename, 'r', newline='', encoding='utf-8-sig') as f_csv:
                reader = csv.reader(f_csv, delimiter=';')
                header = next(reader, None)
                if header is None:
                    messagebox.showerror("Erreur Fichier", "CSV historique vide.", parent=self.root)
                    return
                if header[:len(expected_headers)] != expected_headers:
                    messagebox.showerror("Erreur En-tête CSV", f"En-têtes incorrects.\nAttendu: {';'.join(expected_headers)}\nObtenu: {';'.join(header)}", parent=self.root)
                    return
                for row in reader: lignes_csv_temp.append(row)
            if not lignes_csv_temp:
                messagebox.showinfo("Import Historique", "Aucune donnée après en-tête.", parent=self.root)
                return
            map_classe_col = {}
            for i, col_name in enumerate(header):
                if col_name.startswith("Classe:"):
                    classe_name = col_name.split(":", 1)[1]
                    if classe_name in Compte.CLASSE_ACTIF_CHOICES: map_classe_col[classe_name] = i
            potential_conflicts = sum(1 for row in lignes_csv_temp if len(row) >= 1 and row[0].strip() and any(snap.get('date') == datetime.strptime(row[0].strip(), "%Y-%m-%d").strftime("%Y-%m-%d") for snap in self.historique_patrimoine))
            strategy = "ask_each"
            if potential_conflicts > 0:
                dialog = ConflictStrategyDialog(self.root, title="Stratégie d'Import Historique", potential_conflicts=potential_conflicts)
                strategy = dialog.result
                if strategy is None:
                    messagebox.showinfo("Import Annulé", "Importation annulée.", parent=self.root)
                    return
            for num_ligne, row in enumerate(lignes_csv_temp, start=2):
                if len(row) < len(expected_headers):
                    erreurs_detaillees.append(f"L{num_ligne}: Pas assez de colonnes.")
                    lignes_ignorees += 1
                    continue
                try:
                    date_str = row[0].strip()
                    pn_str = row[1].strip().replace(' ', '').replace(',', '.')
                    ta_str = row[2].strip().replace(' ', '').replace(',', '.')
                    tp_str = row[3].strip().replace(' ', '').replace(',', '.')
                    if not date_str:
                        erreurs_detaillees.append(f"L{num_ligne}: Date manquante.")
                        lignes_ignorees += 1
                        continue
                    date_obj_norm = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
                    pn_val = float(pn_str) if pn_str else 0.0
                    ta_val = float(ta_str) if ta_str else 0.0
                    tp_val = float(tp_str) if tp_str else 0.0
                    repartition_actifs_csv = {}
                    for classe_name, col_idx in map_classe_col.items():
                        if col_idx < len(row) and row[col_idx].strip():
                            try: repartition_actifs_csv[classe_name] = float(row[col_idx].strip().replace(' ', '').replace(',', '.'))
                            except ValueError: erreurs_detaillees.append(f"L{num_ligne}: Format nombre invalide pour {header[col_idx]} ('{row[col_idx]}').")
                    nouvel_instantane = {'date': date_obj_norm, 'patrimoine_net': pn_val, 'total_actifs': ta_val, 'total_passifs_magnitude': tp_val, 'repartition_actifs_par_classe': repartition_actifs_csv}
                    index_existant = next((i for i, snap in enumerate(self.historique_patrimoine) if snap.get('date') == date_obj_norm), -1)
                    appliquer_maj = False
                    if index_existant != -1:
                        if strategy == "update_all": appliquer_maj = True
                        elif strategy == "skip_all":
                            lignes_ignorees += 1
                            continue
                        elif strategy == "ask_each":
                            ancien_snap = self.historique_patrimoine[index_existant]
                            msg_upd = (f"Instantané existe pour {date_obj_norm}:\nAnc.Net: {format_nombre_fr(ancien_snap.get('patrimoine_net', 0))} €\nNouv.Net: {format_nombre_fr(pn_val)} €\nRemplacer?")
                            choix = messagebox.askyesnocancel("Remplacer Instantané?", msg_upd, parent=self.root)
                            if choix is True: appliquer_maj = True
                            elif choix is False:
                                lignes_ignorees += 1
                                continue
                            else:
                                messagebox.showinfo("Import Annulé", "Importation annulée.", parent=self.root)
                                return
                        if appliquer_maj:
                            self.historique_patrimoine[index_existant] = nouvel_instantane
                            entrees_mises_a_jour += 1
                            modifications_effectuees = True
                    else:
                        self.historique_patrimoine.append(nouvel_instantane)
                        entrees_ajoutees += 1
                        modifications_effectuees = True
                except ValueError as ve:
                    erreurs_detaillees.append(f"L{num_ligne} ('{row[0]}'): Format date/nombre invalide - {ve}.")
                    lignes_ignorees += 1
                except Exception as ex_row:
                    erreurs_detaillees.append(f"L{num_ligne} ('{row[0]}'): Erreur - {ex_row}.")
                    lignes_ignorees += 1
            
            if modifications_effectuees:
                self.historique_patrimoine.sort(key=lambda x: x.get('date', ''))
                if self.graph_manager:
                    self.graph_manager.update_historique_patrimoine(self.historique_patrimoine)
            
            summary = (f"Terminé.\nAjoutées: {entrees_ajoutees}\nMis à jour: {entrees_mises_a_jour}\nIgnorées: {lignes_ignorees}")
            if erreurs_detaillees: summary += "\n\nErreurs (premières 5):\n" + "\n".join(erreurs_detaillees[:5])
            if len(erreurs_detaillees) > 5: summary += f"\n...et {len(erreurs_detaillees) - 5} autres."
            messagebox.showinfo("Rapport Import Historique", summary, parent=self.root)
            if modifications_effectuees: messagebox.showinfo("Sauvegarde", "N'oubliez pas de sauvegarder.", parent=self.root)
        except FileNotFoundError: messagebox.showerror("Erreur", f"Fichier non trouvé: {filename}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Erreur Importation Majeure", f"Erreur: {e}", parent=self.root)
            print(f"ERREUR Import Historique CSV: {e}")
            traceback.print_exc()

    def exporter_csv_historique(self):
        if not self.historique_patrimoine:
            messagebox.showinfo("Exporter Historique CSV", "Aucune donnée d'historique à exporter.", parent=self.root)
            return
        filename = filedialog.asksaveasfilename(title="Enregistrer l'historique sous...", defaultextension=".csv", filetypes=[("Fichiers CSV (*.csv)", "*.csv"), ("Tous les fichiers (*.*)", "*.*")], initialfile="patrimoine_historique_export.csv")
        if not filename: return
        try:
            toutes_classes_actifs_historique = set()
            for snap in self.historique_patrimoine:
                if 'repartition_actifs_par_classe' in snap and isinstance(snap['repartition_actifs_par_classe'], dict):
                    toutes_classes_actifs_historique.update(snap['repartition_actifs_par_classe'].keys())
            sorted_classes_actifs = sorted(list(toutes_classes_actifs_historique))
            headers = ["Date", "Patrimoine Net", "Total Actifs", "Total Passifs Magnitude"]
            for classe_nom in sorted_classes_actifs: headers.append(f"Classe:{classe_nom}")
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f_csv:
                writer = csv.writer(f_csv, delimiter=';')
                writer.writerow(headers)
                for snapshot in self.historique_patrimoine:
                    row = [snapshot.get('date', ''), str(snapshot.get('patrimoine_net', 0.0)).replace('.', ','), str(snapshot.get('total_actifs', 0.0)).replace('.', ','), str(snapshot.get('total_passifs_magnitude', 0.0)).replace('.', ',')]
                    repartition = snapshot.get('repartition_actifs_par_classe', {})
                    for classe_nom in sorted_classes_actifs: row.append(str(repartition.get(classe_nom, 0.0)).replace('.', ','))
                    writer.writerow(row)
            messagebox.showinfo("Exportation Réussie", f"Historique exporté avec succès vers :\n{filename}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Erreur d'Exportation", f"Une erreur est survenue lors de l'exportation de l'historique :\n{e}", parent=self.root)
            print(f"ERREUR Export Historique CSV: {e}")
            traceback.print_exc()

    def exporter_csv(self):
        if not self.comptes:
            messagebox.showinfo("Exporter CSV", "Aucun compte à exporter.")
            return
        filename = filedialog.asksaveasfilename(title="Enregistrer les comptes sous...", defaultextension=".csv", filetypes=[("Fichiers CSV (*.csv)", "*.csv"), ("Tous les fichiers (*.*)", "*.*")], initialfile="patrimoine_comptes_export.csv")
        if not filename: return
        try:
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f_csv:
                writer = csv.writer(f_csv, delimiter=';')
                headers = ["Nom du Compte", "Banque", "Type de Compte", "Solde", "Classe d'Actif", "Liquidité", "Terme du Passif", "Suivi Budget"]
                writer.writerow(headers)
                for compte in self.comptes:
                    solde_csv = str(compte.solde).replace('.', ',')
                    suivi_budget_csv = "Oui" if compte.suivi_budget else "Non"
                    row = [compte.nom, compte.banque, compte.type_compte, solde_csv, compte.classe_actif, compte.liquidite, compte.terme_passif, suivi_budget_csv]
                    writer.writerow(row)
            messagebox.showinfo("Exportation Réussie", f"Données exportées vers :\n{filename}")
        except Exception as e:
            messagebox.showerror("Erreur d'Exportation", f"Erreur :\n{e}")
            print(f"ERREUR Export CSV: {e}")
            traceback.print_exc()

    def _set_item_open_state_recursive(self, item_iid, open_state):
        if self.tree.exists(item_iid):
            try:
                self.tree.item(item_iid, open=open_state)
            except tk.TclError:
                pass
            for child_iid in self.tree.get_children(item_iid):
                self._set_item_open_state_recursive(child_iid, open_state)

    def deplier_tout(self):
        for top_level_item_iid in self.tree.get_children(''):
            self._set_item_open_state_recursive(top_level_item_iid, True)

    def replier_tout(self):
        for top_level_item_iid in self.tree.get_children(''):
            self._set_item_open_state_recursive(top_level_item_iid, False)

    def _finalize_app(self):
        if MATPLOTLIB_AVAILABLE:
            plt.close('all')
        print("INFO: Fermé.")

    def on_closing(self):
        reponse = messagebox.askyesnocancel("Quitter", "Voulez-vous sauvegarder les modifications avant de quitter ?")
        
        if reponse is True:
            self.sauvegarder_donnees()
            self.sauvegarder_budget_donnees()
            self._finalize_app()
            self.root.quit()
            self.root.destroy()
        elif reponse is False:
            self._finalize_app()
            self.root.quit()
            self.root.destroy()

    def changer_vue_treeview(self, event=None):
        self.update_treeview_headers()
        self.mettre_a_jour_liste()

    def update_treeview_headers(self):
        current_mode = self.view_mode_var.get()
        col_map = self.col_text_map_type if current_mode == "Type Détaillé" else self.col_text_map_banque
        for col_id in self.tree['columns']:
            new_text = col_map.get(col_id, col_id)
            self.tree.heading(col_id, text=new_text)
            if col_id == self.dernier_tri_col:
                fleche = ' ▲' if not self.dernier_tri_reverse else ' ▼'
                self.tree.heading(col_id, text=new_text + fleche)

    def mettre_a_jour_liste(self):
        self.update_action_buttons_state()
        for item in self.tree.get_children():
            self.tree.delete(item)
        current_view_mode = self.view_mode_var.get()
        if current_view_mode == "Type Détaillé":
            actifs_comptes_all = [c for c in self.comptes if c.type_compte == 'Actif']
            passifs_comptes_all = [c for c in self.comptes if c.type_compte == 'Passif']
            total_actifs_value = sum(c.solde for c in actifs_comptes_all)
            total_passifs_value = sum(c.solde for c in passifs_comptes_all)
            id_main_actifs = self.tree.insert('', tk.END, iid='___actifs_main_group___', values=(f"ACTIFS ({len(actifs_comptes_all)} compte{'s' if len(actifs_comptes_all)!=1 else ''})", "TOTAL:", f"{format_nombre_fr(total_actifs_value)} €"), tags=('group_header',), open=False)
            id_main_passifs = self.tree.insert('', tk.END, iid='___passifs_main_group___', values=(f"PASSIFS ({len(passifs_comptes_all)} compte{'s' if len(passifs_comptes_all)!=1 else ''})", "TOTAL:", f"{format_nombre_fr(total_passifs_value)} €"), tags=('group_header',), open=False)
            grouped_actifs = defaultdict(list)
            for compte in actifs_comptes_all: grouped_actifs[compte.classe_actif].append(compte)
            for classe in Compte.CLASSE_ACTIF_CHOICES:
                if classe in grouped_actifs and classe not in ["N/A", "Non Renseigné"]:
                    comptes_in_classe = grouped_actifs[classe]
                    if not comptes_in_classe: continue
                    subtotal_classe = sum(c.solde for c in comptes_in_classe)
                    iid_classe = f"actifs_classe_{classe.replace(' ', '_').replace('/', '_').replace('<', 'lt').replace('>', 'gt')}"
                    id_classe_row = self.tree.insert(id_main_actifs, tk.END, iid=iid_classe, values=(f"  {classe} ({len(comptes_in_classe)})", "S-Total:", f"{format_nombre_fr(subtotal_classe)} €"), tags=('sub_group_header',), open=False)
                    for compte in comptes_in_classe: self.tree.insert(id_classe_row, tk.END, values=(f"    {compte.nom}", "", f"{format_nombre_fr(compte.solde)} €"))
            grouped_passifs = defaultdict(list)
            for compte in passifs_comptes_all: grouped_passifs[compte.terme_passif].append(compte)
            for terme in Compte.TERME_PASSIF_CHOICES:
                if terme in grouped_passifs and terme not in ["N/A", "Non Renseigné"]:
                    comptes_in_terme = grouped_passifs[terme]
                    if not comptes_in_terme: continue
                    subtotal_terme = sum(c.solde for c in comptes_in_terme)
                    iid_terme = f"passifs_terme_{terme.replace(' ', '_').replace('/', '_').replace('<', 'lt').replace('>', 'gt')}"
                    id_terme_row = self.tree.insert(id_main_passifs, tk.END, iid=iid_terme, values=(f"  {terme} ({len(comptes_in_terme)})", "S-Total:", f"{format_nombre_fr(subtotal_terme)} €"), tags=('sub_group_header',), open=False)
                    for compte in comptes_in_terme: self.tree.insert(id_terme_row, tk.END, values=(f"    {compte.nom}", "", f"{format_nombre_fr(compte.solde)} €"))
        elif current_view_mode == "Banque":
            comptes_par_banque = defaultdict(list)
            for compte in self.comptes: comptes_par_banque[compte.banque].append(compte)
            for nom_banque in sorted(comptes_par_banque.keys(), key=lambda b: b.lower()):
                liste_comptes_banque = comptes_par_banque[nom_banque]
                solde_net_banque = 0
                for compte_b in liste_comptes_banque:
                    if compte_b.type_compte == 'Actif': solde_net_banque += compte_b.solde
                    elif compte_b.type_compte == 'Passif': solde_net_banque -= abs(compte_b.solde)
                iid_banque = f"___banque_{nom_banque.replace(' ', '_')}___"
                id_banque_header = self.tree.insert('', tk.END, iid=iid_banque, values=(f"{nom_banque} ({len(liste_comptes_banque)} compte{'s' if len(liste_comptes_banque)!=1 else ''})", "Solde Net:", f"{format_nombre_fr(solde_net_banque)} €"), tags=('group_header',), open=False)
                for compte_b in liste_comptes_banque: self.tree.insert(id_banque_header, tk.END, values=(f"  {compte_b.nom}", compte_b.type_compte, f"{format_nombre_fr(compte_b.solde)} €"))

    def trier_colonne(self, col_id):
        if col_id not in self.tree['columns']: return
        reverse = False
        if col_id == self.dernier_tri_col: reverse = not self.dernier_tri_reverse
        current_mode = self.view_mode_var.get()
        key_func = None
        if col_id == 'solde': key_func = lambda compte: compte.solde
        elif col_id == 'nom': key_func = lambda compte: compte.nom.lower()
        elif col_id == 'detail_col':
            if current_mode == "Banque": key_func = lambda compte: compte.type_compte.lower()
            else: key_func = lambda compte: compte.banque.lower()
        if not key_func: return
        try: self.comptes.sort(key=key_func, reverse=reverse)
        except Exception as e:
            print(f"Erreur de tri: {e}")
            return
        self.dernier_tri_col = col_id
        self.dernier_tri_reverse = reverse
        self.update_treeview_headers()
        self.mettre_a_jour_liste()

    def sauvegarder_donnees(self):
        aujourdhui_str = date.today().strftime("%Y-%m-%d")
        pat_net, total_actifs, total_passifs_magnitude = 0.0, 0.0, 0.0
        soldes_comptes_details = {c.nom: c.solde for c in self.comptes}
        repartition_actifs = defaultdict(float)
        
        for compte in self.comptes:
            if compte.type_compte == 'Actif':
                total_actifs += compte.solde
                pat_net += compte.solde
                if compte.classe_actif not in ["N/A", "Non Renseigné"]:
                    repartition_actifs[compte.classe_actif] += compte.solde
            elif compte.type_compte == 'Passif':
                total_passifs_magnitude += abs(compte.solde)
                pat_net -= abs(compte.solde)

        nouvel_instantane = {
            'date': aujourdhui_str,
            'total_actifs': total_actifs,
            'total_passifs_magnitude': total_passifs_magnitude,
            'patrimoine_net': pat_net,
            'repartition_actifs_par_classe': dict(repartition_actifs),
            'soldes_comptes': soldes_comptes_details
        }

        index_existant = next((i for i, snap in enumerate(self.historique_patrimoine) if snap.get('date') == aujourdhui_str), -1)
        if index_existant != -1:
            self.historique_patrimoine[index_existant] = nouvel_instantane
        else:
            self.historique_patrimoine.append(nouvel_instantane)
        
        self.historique_patrimoine.sort(key=lambda x: x.get('date', ''))
        self.nettoyer_historique()

        self.data_manager.sauvegarder_donnees(self.comptes, self.historique_patrimoine)

    def sauvegarder_donnees_menu(self):
        self.sauvegarder_donnees()
        self.sauvegarder_budget_donnees()
        messagebox.showinfo("Sauvegarde", "Données et instantané sauvegardés avec succès !", parent=self.root)
        self.mettre_a_jour_toutes_les_vues()

    def sauvegarder_budget_donnees(self):
        self.data_manager.sauvegarder_budget_donnees(self.budget_data)

    def calculer_et_afficher_patrimoine(self):
        patrimoine_net = 0.0
        try:
            for compte in self.comptes:
                if compte.type_compte == 'Actif': patrimoine_net += compte.solde
                elif compte.type_compte == 'Passif': patrimoine_net -= abs(compte.solde)
            self.label_patrimoine.config(text=f"Patrimoine Net : {format_nombre_fr(patrimoine_net)} €")
        except Exception as e:
            print(f"ERREUR Calcul: {e}")
            traceback.print_exc()
            messagebox.showerror("Erreur Calcul", f"Erreur:\n{e}")

    def prendre_instantane(self):
        self.sauvegarder_donnees_menu()

    def importer_csv_comptes(self):
        filename = filedialog.askopenfilename(title="Ouvrir un fichier CSV de comptes", filetypes=[("Fichiers CSV (*.csv)", "*.csv"), ("Tous les fichiers (*.*)", "*.*")])
        if not filename: return
        comptes_ajoutes, comptes_mis_a_jour, lignes_ignorees, modifications_effectuees = 0, 0, 0, False
        erreurs_detaillees = []
        expected_headers = ["Nom du Compte", "Banque", "Type de Compte", "Solde", "Classe d'Actif", "Liquidité", "Terme du Passif", "Suivi Budget"]
        try:
            lignes_csv_temp = []
            with open(filename, 'r', newline='', encoding='utf-8-sig') as f_csv:
                reader = csv.reader(f_csv, delimiter=';')
                header = next(reader, None)
                if header is None:
                    messagebox.showerror("Erreur Fichier", "CSV vide.", parent=self.root)
                    return
                if header != expected_headers:
                    messagebox.showerror("Erreur En-tête", f"En-têtes CSV incorrects.\nAttendu: {';'.join(expected_headers)}\nObtenu: {';'.join(header)}", parent=self.root)
                    return
                for row in reader: lignes_csv_temp.append(row)
            if not lignes_csv_temp:
                messagebox.showinfo("Import CSV", "Aucune donnée après en-tête.", parent=self.root)
                return
            potential_conflicts = sum(1 for r in lignes_csv_temp if len(r) == len(expected_headers) and any(c.nom == r[0].strip() and c.banque == r[1].strip() for c in self.comptes))
            strategy = "ask_each"
            if potential_conflicts > 0:
                dialog = ConflictStrategyDialog(self.root, title="Stratégie d'Import Comptes", potential_conflicts=potential_conflicts)
                strategy = dialog.result
                if strategy is None:
                    messagebox.showinfo("Import Annulé", "Importation annulée.", parent=self.root)
                    return
            for num_ligne, row in enumerate(lignes_csv_temp, start=2):
                if len(row) != len(expected_headers):
                    erreurs_detaillees.append(f"L{num_ligne}: Nb colonnes incorrect.")
                    lignes_ignorees += 1
                    continue
                try:
                    nom, banque, type_c, solde_s, classe_a, liq, ter_p, suivi_budget_str = map(str.strip, row)
                    if not all([nom, banque, type_c, solde_s]):
                        erreurs_detaillees.append(f"L{num_ligne} ('{nom}'): Données manquantes.")
                        lignes_ignorees += 1
                        continue
                    solde = float(solde_s.replace(' ', '').replace(',', '.'))
                    if type_c not in ["Actif", "Passif"]:
                        erreurs_detaillees.append(f"L{num_ligne} ('{nom}'): Type '{type_c}' invalide.")
                        lignes_ignorees += 1
                        continue
                    suivi_budget_val = suivi_budget_str.lower() == 'oui'
                    compte_existant = next((c for c in self.comptes if c.nom == nom and c.banque == banque), None)
                    if compte_existant:
                        appliquer_maj = False
                        if strategy == "update_all": appliquer_maj = True
                        elif strategy == "skip_all":
                            lignes_ignorees += 1
                            continue
                        elif strategy == "ask_each":
                            msg_upd = (f"Compte '{nom}' ({banque}) existe.\nActuel: {format_nombre_fr(compte_existant.solde)} €\nCSV: {format_nombre_fr(solde)} €\nMettre à jour?")
                            choix = messagebox.askyesnocancel("Mise à jour", msg_upd, parent=self.root)
                            if choix is True: appliquer_maj = True
                            elif choix is False:
                                lignes_ignorees += 1
                                continue
                            else:
                                messagebox.showinfo("Import Annulé", "Importation annulée.", parent=self.root)
                                return
                        if appliquer_maj:
                            compte_existant.nom, compte_existant.banque, compte_existant.type_compte, compte_existant.solde = nom, banque, type_c, solde
                            compte_existant.liquidite, compte_existant.classe_actif, compte_existant.terme_passif = liq, classe_a, ter_p
                            compte_existant.suivi_budget = suivi_budget_val
                            compte_existant.__init__(**compte_existant.to_dict())
                            comptes_mis_a_jour += 1
                            modifications_effectuees = True
                    else:
                        self.comptes.append(Compte(nom=nom, banque=banque, type_compte=type_c, solde=solde, liquidite=liq, terme_passif=ter_p, classe_actif=classe_a, suivi_budget=suivi_budget_val))
                        comptes_ajoutes += 1
                        modifications_effectuees = True
                except ValueError as ve:
                    erreurs_detaillees.append(f"L{num_ligne} ('{row[0]}'): Données invalides - {ve}.")
                    lignes_ignorees += 1
                except Exception as ex:
                    erreurs_detaillees.append(f"L{num_ligne} ('{row[0]}'): Erreur - {ex}.")
                    lignes_ignorees += 1
            if modifications_effectuees: self.mettre_a_jour_toutes_les_vues()
            summary = (f"Terminé.\nAjoutés: {comptes_ajoutes}\nMis à jour: {comptes_mis_a_jour}\nIgnorés: {lignes_ignorees}")
            if erreurs_detaillees: summary += "\n\nErreurs (premières 5):\n" + "\n".join(erreurs_detaillees[:5])
            if len(erreurs_detaillees) > 5: summary += f"\n...et {len(erreurs_detaillees) - 5} autres."
            messagebox.showinfo("Rapport Importation Comptes", summary, parent=self.root)
            if modifications_effectuees: messagebox.showinfo("Sauvegarde", "N'oubliez pas de sauvegarder.", parent=self.root)
        except FileNotFoundError: messagebox.showerror("Erreur", f"Fichier non trouvé: {filename}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Erreur Importation Majeure", f"Erreur: {e}", parent=self.root)
            print(f"ERREUR Import CSV Comptes: {e}")
            traceback.print_exc()

    def valider_gestion_compte(self, window, entries, compte_existant):
        nom = entries['nom'].get().strip()
        banque = entries['banque'].get().strip()
        type_compte = entries['type_combo'].get()
        solde_str = entries['solde'].get().strip()
        
        if not all([nom, banque, type_compte, solde_str]):
            messagebox.showerror("Erreur", "Champs obligatoires.", parent=window)
            return
        
        try: solde = float(solde_str.replace(',', '.'))
        except ValueError:
            messagebox.showerror("Erreur", "Solde invalide.", parent=window)
            return

        liquidite, classe_actif, terme_passif = None, None, None
        jour_debit, jour_debut, jour_fin, compte_associe = None, None, None, None

        if type_compte == 'Actif':
            liquidite = entries['liquidite_combo'].get()
            classe_actif = entries['classe_actif_combo'].get()
        elif type_compte == 'Passif':
            terme_passif = entries['terme_passif_combo'].get()
            try:
                jour_debit_str = entries['jour_debit_entry'].get()
                jour_debut_str = entries['jour_debut_periode_entry'].get()
                jour_fin_str = entries['jour_fin_periode_entry'].get()
                compte_associe = entries['compte_debit_associe_combo'].get()
                
                jour_debit = int(jour_debit_str) if jour_debit_str else None
                jour_debut = int(jour_debut_str) if jour_debut_str else None
                jour_fin = int(jour_fin_str) if jour_fin_str else None
            except ValueError:
                messagebox.showerror("Erreur", "Les jours de débit/période doivent être des nombres.", parent=window)
                return

        suivi_budget_val = entries['suivi_budget_var'].get()
        alerte_decouvert_val = entries['alerte_decouvert_var'].get() if suivi_budget_val else False

        args_compte = {
            'nom': nom, 'banque': banque, 'type_compte': type_compte, 'solde': solde,
            'liquidite': liquidite, 'terme_passif': terme_passif, 'classe_actif': classe_actif,
            'suivi_budget': suivi_budget_val, 'alerte_decouvert': alerte_decouvert_val,
            'jour_debit': jour_debit, 'jour_debut_periode': jour_debut,
            'jour_fin_periode': jour_fin, 'compte_debit_associe': compte_associe
        }

        if compte_existant:
            args_compte['id'] = compte_existant.id
            compte_existant.__init__(**args_compte)
        else:
            self.comptes.append(Compte(**args_compte))
        
        self.mettre_a_jour_toutes_les_vues()
        self.sauvegarder_donnees()
        window.destroy()
        
    def lancer_edition_compte(self, event=None):
        selected_item_ids = self.tree.selection()
        if not selected_item_ids:
            messagebox.showinfo("Info", "Sélectionnez un compte à modifier.", parent=self.root)
            return

        selected_iid = selected_item_ids[0]
        if selected_iid.startswith('___'):
            return

        try:
            nom_compte_affiche = self.tree.item(selected_iid, 'values')[0].strip()
            nom_compte_reel = nom_compte_affiche.replace(" (-)", "")

            compte_a_modif = next((c for c in self.comptes if c.nom == nom_compte_reel), None)

            if compte_a_modif:
                if compte_a_modif.classe_actif == "Actions/Titres":
                    self.ouvrir_gestion_portefeuille(compte_a_modif)
                else:
                    self.ouvrir_fenetre_gestion_compte(compte_a_modif)
            else:
                messagebox.showerror("Erreur", f"Compte '{nom_compte_reel}' non trouvé pour édition.")

        except Exception as e:
            print(f"Erreur lors du lancement de l'édition : {e}")
            traceback.print_exc()
            return

    def ouvrir_fenetre_gestion_compte(self, compte_a_modifier=None):
        ajout_window = tk.Toplevel(self.root)
        ajout_window.transient(self.root)
        ajout_window.grab_set()
        
        titre = "Modifier le compte" if compte_a_modifier else "Ajouter un nouveau compte"
        ajout_window.title(titre)
        
        form_frame = ttk.Frame(ajout_window, padding="15")
        form_frame.pack(fill=tk.BOTH, expand=True)
        form_frame.columnconfigure(1, weight=1)
        
        entries = {}
        current_row = 0
        
        std_labels = {"Nom:": "nom", "Banque:": "banque", "Type:": "type", "Solde (€):": "solde"}
        for txt, key in std_labels.items():
            ttk.Label(form_frame, text=txt).grid(row=current_row, column=0, sticky=tk.W, pady=2)
            if key == "type":
                entries['type_combo'] = ttk.Combobox(form_frame, values=["Actif", "Passif"], state="readonly")
                entries['type_combo'].grid(row=current_row, column=1, sticky=tk.EW, pady=2)
            else:
                entries[key] = ttk.Entry(form_frame, width=40)
                entries[key].grid(row=current_row, column=1, sticky=tk.EW, pady=2)
            current_row += 1
        
        entries['classe_actif_label'] = ttk.Label(form_frame, text="Classe d'Actif:")
        entries['classe_actif_combo'] = ttk.Combobox(form_frame, values=Compte.CLASSE_ACTIF_CHOICES, state="readonly")
        entries['liquidite_label'] = ttk.Label(form_frame, text="Liquidité:")
        entries['liquidite_combo'] = ttk.Combobox(form_frame, values=Compte.LIQUIDITE_CHOICES, state="readonly")
        
        entries['terme_passif_label'] = ttk.Label(form_frame, text="Terme du Passif:")
        entries['terme_passif_combo'] = ttk.Combobox(form_frame, values=Compte.TERME_PASSIF_CHOICES, state="readonly")
        
        entries['jour_debit_label'] = ttk.Label(form_frame, text="Jour du débit (1-31):")
        entries['jour_debit_entry'] = ttk.Entry(form_frame)
        entries['jour_debut_periode_label'] = ttk.Label(form_frame, text="Jour début période relevé:")
        entries['jour_debut_periode_entry'] = ttk.Entry(form_frame)
        entries['jour_fin_periode_label'] = ttk.Label(form_frame, text="Jour fin période relevé:")
        entries['jour_fin_periode_entry'] = ttk.Entry(form_frame)
        entries['compte_debit_associe_label'] = ttk.Label(form_frame, text="Compte débité:")
        comptes_actifs_noms = [c.nom for c in self.comptes if c.type_compte == 'Actif']
        entries['compte_debit_associe_combo'] = ttk.Combobox(form_frame, values=comptes_actifs_noms, state="readonly")

        entries['suivi_budget_var'] = tk.BooleanVar()
        entries['suivi_budget_check'] = ttk.Checkbutton(form_frame, text="Inclure dans le suivi budgétaire ?", variable=entries['suivi_budget_var'])
        entries['alerte_decouvert_var'] = tk.BooleanVar()
        entries['alerte_decouvert_check'] = ttk.Checkbutton(form_frame, text="Activer l'alerte de découvert ?", variable=entries['alerte_decouvert_var'])
        
        button_frame = ttk.Frame(form_frame)
        
        def _update_visibility(event=None):
            all_specific_widgets = [
                entries['classe_actif_label'], entries['classe_actif_combo'], entries['liquidite_label'], entries['liquidite_combo'],
                entries['terme_passif_label'], entries['terme_passif_combo'], entries['jour_debit_label'], entries['jour_debit_entry'],
                entries['jour_debut_periode_label'], entries['jour_debut_periode_entry'], entries['jour_fin_periode_label'], entries['jour_fin_periode_entry'],
                entries['compte_debit_associe_label'], entries['compte_debit_associe_combo']
            ]
            for widget in all_specific_widgets: widget.grid_remove()
            
            sel_type = entries['type_combo'].get()
            row = current_row
            
            if sel_type == 'Actif':
                entries['classe_actif_label'].grid(row=row, column=0, sticky=tk.W, pady=2)
                entries['classe_actif_combo'].grid(row=row, column=1, sticky=tk.EW, pady=2)
                row += 1
                entries['liquidite_label'].grid(row=row, column=0, sticky=tk.W, pady=2)
                entries['liquidite_combo'].grid(row=row, column=1, sticky=tk.EW, pady=2)
                row += 1
            elif sel_type == 'Passif':
                entries['terme_passif_label'].grid(row=row, column=0, sticky=tk.W, pady=2)
                entries['terme_passif_combo'].grid(row=row, column=1, sticky=tk.EW, pady=2)
                row += 1
                ttk.Separator(form_frame, orient='horizontal').grid(row=row, column=0, columnspan=2, sticky='ew', pady=5)
                row += 1
                ttk.Label(form_frame, text="Règles de Règlement (Débit Différé)", font=('TkDefaultFont', 9, 'bold')).grid(row=row, column=0, columnspan=2, sticky=tk.W)
                row += 1
                entries['jour_debit_label'].grid(row=row, column=0, sticky=tk.W, pady=2)
                entries['jour_debit_entry'].grid(row=row, column=1, sticky=tk.EW, pady=2)
                row += 1
                entries['jour_debut_periode_label'].grid(row=row, column=0, sticky=tk.W, pady=2)
                entries['jour_debut_periode_entry'].grid(row=row, column=1, sticky=tk.EW, pady=2)
                row += 1
                entries['jour_fin_periode_label'].grid(row=row, column=0, sticky=tk.W, pady=2)
                entries['jour_fin_periode_entry'].grid(row=row, column=1, sticky=tk.EW, pady=2)
                row += 1
                entries['compte_debit_associe_label'].grid(row=row, column=0, sticky=tk.W, pady=2)
                entries['compte_debit_associe_combo'].grid(row=row, column=1, sticky=tk.EW, pady=2)
                row += 1
                
            entries['suivi_budget_check'].grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(10, 2))
            row += 1
            if entries['suivi_budget_var'].get():
                entries['alerte_decouvert_check'].grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=(15,0), pady=2)
                row += 1
            
            button_frame.grid(row=row, column=0, columnspan=2, pady=(10, 0), sticky=tk.E)

        entries['type_combo'].bind("<<ComboboxSelected>>", _update_visibility)
        entries['suivi_budget_var'].trace_add("write", lambda *args: _update_visibility())

        if compte_a_modifier:
            entries['nom'].insert(0, compte_a_modifier.nom)
            entries['banque'].insert(0, compte_a_modifier.banque)
            entries['type_combo'].set(compte_a_modifier.type_compte)
            entries['solde'].insert(0, str(compte_a_modifier.solde).replace('.', ','))
            entries['suivi_budget_var'].set(compte_a_modifier.suivi_budget)
            entries['alerte_decouvert_var'].set(compte_a_modifier.alerte_decouvert)
            if compte_a_modifier.type_compte == 'Actif':
                entries['classe_actif_combo'].set(compte_a_modifier.classe_actif or '')
                entries['liquidite_combo'].set(compte_a_modifier.liquidite or '')
            elif compte_a_modifier.type_compte == 'Passif':
                entries['terme_passif_combo'].set(compte_a_modifier.terme_passif or '')
                entries['jour_debit_entry'].insert(0, str(compte_a_modifier.jour_debit or ''))
                entries['jour_debut_periode_entry'].insert(0, str(compte_a_modifier.jour_debut_periode or ''))
                entries['jour_fin_periode_entry'].insert(0, str(compte_a_modifier.jour_fin_periode or ''))
                entries['compte_debit_associe_combo'].set(compte_a_modifier.compte_debit_associe or '')
        
        _update_visibility()
        
        ttk.Button(button_frame, text="Valider", command=lambda: self.valider_gestion_compte(ajout_window, entries, compte_a_modifier)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Annuler", command=ajout_window.destroy).pack(side=tk.LEFT)
        entries['nom'].focus()
        self.root.wait_window(ajout_window)
            
    def _ouvrir_fenetre_gestion_categorie(self, categorie_existante=None):
        dialog = tk.Toplevel(self.root)
        dialog.transient(self.root)
        titre = "Modifier Catégorie" if categorie_existante else "Ajouter Catégorie"
        dialog.title(titre)
        dialog.geometry("400x230")
        dialog.resizable(False, False)
        dialog.grab_set()
        form_frame = ttk.Frame(dialog, padding="15")
        form_frame.pack(fill=tk.BOTH, expand=True)
        form_frame.columnconfigure(1, weight=1)
        resultat = {}
        comptes_disponibles = [c.nom for c in self.comptes if c.suivi_budget]
        if not comptes_disponibles:
            messagebox.showerror("Erreur", "Aucun compte n'est configuré pour le suivi budgétaire.", parent=dialog)
            dialog.destroy()
            return None

        ttk.Label(form_frame, text="Nom:").grid(row=0, column=0, sticky=tk.W, pady=3)
        nom_entry = ttk.Entry(form_frame)
        nom_entry.grid(row=0, column=1, columnspan=2, sticky=tk.EW, pady=3)
        ttk.Label(form_frame, text="Type:").grid(row=1, column=0, sticky=tk.W, pady=3)
        type_var = tk.StringVar()
        type_combo = ttk.Combobox(form_frame, textvariable=type_var, values=["Dépense", "Revenu"], state="readonly")
        type_combo.grid(row=1, column=1, columnspan=2, sticky=tk.EW, pady=3)
        
        ttk.Label(form_frame, text="Montant Prévisionnel (€):").grid(row=2, column=0, sticky=tk.W, pady=3)
        montant_entry = ttk.Entry(form_frame)
        montant_entry.grid(row=2, column=1, sticky=tk.EW, pady=3)
        montant_entry.bind("<Return>", lambda event: self._evaluate_math_in_entry(montant_entry))
        montant_entry.bind("<FocusOut>", lambda event: self._evaluate_math_in_entry(montant_entry))
        
        details_calendrier = categorie_existante.get('details', []) if categorie_existante else []

        def _open_calendar():
            nonlocal details_calendrier
            try:
                year = int(self.budget_annee_var.get())
                month = int(self.budget_mois_var.get())
                cal_dialog = DailyBudgetCalendarDialog(dialog, "Budget Journalier", year, month, details=details_calendrier)

                if cal_dialog.result is not None:
                    montant_total = cal_dialog.result['total']
                    details_calendrier = cal_dialog.result['details']

                    montant_entry.delete(0, tk.END)
                    montant_entry.insert(0, str(montant_total).replace('.',','))
            except Exception as e:
                messagebox.showerror("Erreur", f"Impossible d'ouvrir le calendrier : {e}", parent=dialog)

        cal_button = ttk.Button(form_frame, text="Détailler...", command=_open_calendar, width=10)
        cal_button.grid(row=2, column=2, sticky=tk.W, padx=(5,0))
        
        ttk.Label(form_frame, text="Compte par Défaut:").grid(row=3, column=0, sticky=tk.W, pady=3)
        compte_var = tk.StringVar()
        compte_combo = ttk.Combobox(form_frame, textvariable=compte_var, values=comptes_disponibles, state="readonly")
        compte_combo.grid(row=3, column=1, columnspan=2, sticky=tk.EW, pady=3)

        if categorie_existante:
            nom_entry.insert(0, categorie_existante.get('categorie', ''))
            montant_entry.insert(0, str(categorie_existante.get('prevu', 0.0)).replace('.', ','))
            type_var.set(categorie_existante.get('type', 'Dépense'))
            compte_var.set(categorie_existante.get('compte_prevu', ''))
        else:
            type_var.set("Dépense")
            if comptes_disponibles: compte_combo.current(0)
            
        def on_validate():
            try:
                nom_val = nom_entry.get().strip()
                montant_val = abs(float(montant_entry.get().strip().replace(' ', '').replace(',', '.')))
                type_val = type_var.get()
                compte_val = compte_var.get()
                if not all([nom_val, type_val, compte_val]):
                    messagebox.showerror("Erreur", "Tous les champs sont obligatoires.", parent=dialog)
                    return
                resultat['ok'] = True
                resultat['valeurs'] = {
                    "categorie": nom_val, "prevu": montant_val, "type": type_val, 
                    "compte_prevu": compte_val,
                    "details": details_calendrier
                }
                dialog.destroy()
            except (ValueError, TypeError): messagebox.showerror("Erreur", "Le montant est invalide.", parent=dialog)
        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=(15, 0), sticky=tk.E)
        ttk.Button(button_frame, text="Valider", command=on_validate).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Annuler", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        nom_entry.focus()
        self.root.wait_window(dialog)
        return resultat.get('valeurs')

    def ajouter_categorie_budget(self):
        result = self._ouvrir_fenetre_gestion_categorie(None)
        if result:
            cle_mois_annee = f"{self.budget_annee_var.get()}-{self.budget_mois_var.get()}"
            if cle_mois_annee not in self.budget_data:
                self.budget_data[cle_mois_annee] = {'categories_prevues': [], 'transactions': []}
            
            categories_du_mois = self.budget_data[cle_mois_annee].get('categories_prevues', [])
            if any(cat['categorie'].lower() == result['categorie'].lower() for cat in categories_du_mois):
                messagebox.showwarning("Catégorie Existante", f"La catégorie '{result['categorie']}' existe déjà pour ce mois.", parent=self.root)
                return
                
            categories_du_mois.append(result)
            self.mettre_a_jour_toutes_les_vues()

    def modifier_categorie_budget(self, event=None):
        selection = self.budget_tree.selection()
        if not selection: return
        
        nom_categorie_actuel = self.budget_tree.item(selection[0])['values'][0]
        cle_mois_annee = f"{self.budget_annee_var.get()}-{self.budget_mois_var.get()}"
        categories_du_mois = self.budget_data.get(cle_mois_annee, {}).get('categories_prevues', [])
        cat_a_modifier = next((cat for cat in categories_du_mois if cat['categorie'] == nom_categorie_actuel), None)
        
        if cat_a_modifier:
            result = self._ouvrir_fenetre_gestion_categorie(cat_a_modifier)
            if result:
                nom_deja_pris = any(cat['categorie'].lower() == result['categorie'].lower() and cat['categorie'] != nom_categorie_actuel for cat in categories_du_mois)
                if nom_deja_pris:
                    messagebox.showwarning("Nom Existant", f"Une catégorie avec le nom '{result['categorie']}' existe déjà.", parent=self.root)
                    return
                cat_a_modifier.update(result)
                self.mettre_a_jour_toutes_les_vues()

    def _parse_date_flexible(self, date_str):
        formats_a_tester = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"]
        for fmt in formats_a_tester:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Format de date '{date_str}' non reconnu.")

    def _calculate_expression(self, expr_str):
            import ast, operator as op
            operators = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.Pow: op.pow, ast.USub: op.neg}
            def _eval(node):
                if isinstance(node, ast.Constant): return node.value
                elif isinstance(node, ast.BinOp): return operators[type(node.op)](_eval(node.left), _eval(node.right))
                elif isinstance(node, ast.UnaryOp): return operators[type(node.op)](_eval(node.operand))
                else: raise TypeError(node)
            expr_str_safe = expr_str.strip().replace(',', '.')
            if not expr_str_safe: return 0.0
            try: return float(expr_str_safe)
            except ValueError:
                try: return _eval(ast.parse(expr_str_safe, mode='eval').body)
                except (TypeError, SyntaxError, KeyError, ZeroDivisionError, NameError): raise ValueError("Expression mathématique invalide")

    def get_all_unique_budget_categories(self):
            all_categories = set()
            for cle, data in self.budget_data.items():
                if cle == "_templates" and isinstance(data, dict):
                    for template_name, template_cats in data.items():
                        if isinstance(template_cats, list):
                            for cat in template_cats:
                                if cat.get('categorie'): all_categories.add(cat.get('categorie'))
                elif isinstance(data, dict) and not cle.startswith("_"):
                    for cat in data.get('categories_prevues', []):
                        if cat.get('categorie'): all_categories.add(cat.get('categorie'))
                    for trans in data.get('transactions', []):
                        cat_name = trans.get('categorie')
                        if cat_name and cat_name not in ["(Virement)", "(Hors Budget)"]: all_categories.add(cat_name)
            for trans_rec in self.budget_data.get('transactions_recurrentes', []):
                cat_name = trans_rec.get('categorie')
                if cat_name and cat_name not in ["(Virement)", "(Hors Budget)"]: all_categories.add(cat_name)
            return sorted(list(all_categories))

    def ajouter_transaction(self):
        dialog = TransactionDialog(self.root, "Ajouter une Transaction", self.comptes, self.get_all_budget_categories(), self.ai_service)
        if dialog.result:
            new_trans = dialog.result
            new_trans['id'] = uuid.uuid4().hex
            cle_mois_annee = datetime.strptime(new_trans['date'], "%Y-%m-%d").strftime("%Y-%m")
            if cle_mois_annee not in self.budget_data:
                self.budget_data[cle_mois_annee] = {'categories_prevues': [], 'transactions': []}
            self.budget_data[cle_mois_annee]['transactions'].append(new_trans)
            self.mettre_a_jour_toutes_les_vues()
            
    def trouver_transaction_par_id(self, transaction_id):
        for cle_mois, data in self.budget_data.items():
            if isinstance(data, dict) and 'transactions' in data:
                for transaction in data['transactions']:
                    if transaction.get('id') == transaction_id:
                        return transaction, cle_mois
        return None, None

    def modifier_transaction(self, event=None):
        selection = self.transactions_tree.selection()
        if not selection:
            messagebox.showinfo("Information", "Veuillez sélectionner une transaction à modifier.", parent=self.root)
            return
        trans_id = selection[0]
        trans_a_modifier, cle_originale = self.trouver_transaction_par_id(trans_id)
        if trans_a_modifier:
            dialog = TransactionDialog(self.root, "Modifier une Transaction", self.comptes, self.get_all_budget_categories(), self.ai_service, trans_existante=trans_a_modifier)
            if dialog.result:
                nouvelle_cle = datetime.strptime(dialog.result['date'], "%Y-%m-%d").strftime("%Y-%m")
                if cle_originale != nouvelle_cle:
                    self.budget_data[cle_originale]['transactions'] = [t for t in self.budget_data[cle_originale]['transactions'] if t['id'] != trans_id]
                    if nouvelle_cle not in self.budget_data:
                        self.budget_data[nouvelle_cle] = {'categories_prevues': [], 'transactions': []}
                    self.budget_data[nouvelle_cle]['transactions'].append(dialog.result)
                else:
                    trans_a_modifier.update(dialog.result)
                self.mettre_a_jour_toutes_les_vues()
            
    def ouvrir_gestion_modeles(self):
        TemplateManagerWindow(self)

    def appliquer_modele_budget(self):
        templates = self.budget_data.get("_templates", {})
        if not templates:
            messagebox.showinfo("Aucun Modèle", "Veuillez d'abord créer un modèle via 'Gérer les Modèles...'.", parent=self.root)
            return
        dialog = ApplyTemplateDialog(self.root, templates)
        nom_modele_choisi = dialog.result
        if nom_modele_choisi:
            cle_mois_annee = f"{self.budget_annee_var.get()}-{self.budget_mois_var.get()}"
            if self.budget_data.get(cle_mois_annee, {}).get('categories_prevues'):
                if not messagebox.askyesno("Confirmer", "Ce mois contient déjà un budget. Voulez-vous l'écraser ?", parent=self.root): return
            modele_cats = templates.get(nom_modele_choisi, [])
            nouvelles_categories = [cat for cat in copy.deepcopy(modele_cats) if cat.get('prevu', 0.0) > 0]
            if cle_mois_annee not in self.budget_data: self.budget_data[cle_mois_annee] = {'categories_prevues': [], 'transactions': []}
            self.budget_data[cle_mois_annee]['categories_prevues'] = nouvelles_categories
            self.sauvegarder_budget_donnees()
            self.mettre_a_jour_toutes_les_vues()
            messagebox.showinfo("Modèle Appliqué", f"Le modèle '{nom_modele_choisi}' a été appliqué.", parent=self.root)

    def pointer_transactions(self):
        selection = self.transactions_tree.selection()
        if not selection:
            messagebox.showinfo("Information", "Veuillez sélectionner une ou plusieurs transactions à pointer.", parent=self.root)
            return
        if not messagebox.askyesno("Confirmer le Pointage", f"Pointer {len(selection)} transaction(s) ?\nCette action modifiera définitivement le solde des comptes associés.", parent=self.root): return
        transactions_a_pointer_ids = set(selection)
        modifications_effectuees = False
        
        # On doit potentiellement chercher dans plusieurs mois si des transactions reportées sont sélectionnées
        for cle_mois_annee, data in self.budget_data.items():
            if not isinstance(data, dict) or 'transactions' not in data: continue
            
            for trans in data.get('transactions', []):
                if trans.get('id') in transactions_a_pointer_ids and not trans.get('pointe', False):
                    compte_a_modifier = next((c for c in self.comptes if c.nom == trans.get('compte_affecte')), None)
                    if compte_a_modifier:
                        montant_transaction = trans.get('montant', 0.0)
                        if compte_a_modifier.type_compte == 'Passif':
                            compte_a_modifier.solde -= montant_transaction
                        else:
                            compte_a_modifier.solde += montant_transaction
                        trans['pointe'] = True
                        modifications_effectuees = True
                    else:
                        messagebox.showwarning("Compte Non Trouvé", f"Le compte '{trans.get('compte_affecte')}' pour la transaction '{trans.get('description')}' n'a pas été trouvé.", parent=self.root)
        
        if modifications_effectuees:
            messagebox.showinfo("Pointage Réussi", "Transactions pointées et soldes mis à jour.", parent=self.root)
            self.sauvegarder_donnees()
            self.sauvegarder_budget_donnees()
            self.mettre_a_jour_toutes_les_vues()

    def mettre_a_jour_toutes_les_vues(self, event=None):
        resultats_projection = self._calculer_projection_mensuelle()
        self.mettre_a_jour_liste()
        self.calculer_et_afficher_patrimoine()
        self.mettre_a_jour_vue_budget(resultats_projection)
        if self.graph_manager:
            self.graph_manager.update_camembert_classe(self.comptes)
            self.graph_manager.update_camembert_banque(self.comptes)
            self.graph_manager.update_historique_patrimoine(self.historique_patrimoine)
            
            cle_mois_annee = f"{self.budget_annee_var.get()}-{self.budget_mois_var.get()}"
            donnees_du_mois = self.budget_data.get(cle_mois_annee, {})
            annee, mois = map(int, cle_mois_annee.split('-'))
            self.graph_manager.update_all_budget_graphs(donnees_du_mois, annee, mois)
            
            if resultats_projection:
                self.graph_manager.update_evolution_line(
                    resultats_projection['dates_graphe'], 
                    resultats_projection['evolution_par_compte']
                )
        self.verifier_et_afficher_alertes_decouvert()
    
    def ajouter_virement(self):
        dialog = VirementDialog(self.root, self.comptes)
        if dialog.result:
            virement_id = uuid.uuid4().hex
            data = dialog.result
            
            trans_debit = {
                "id": uuid.uuid4().hex, "date": data['date'], "description": f"{data['description']} vers {data['destination']}",
                "montant": -data['montant'], "categorie": "(Virement)", "compte_affecte": data['source'],
                "pointe": False, "virement_id": virement_id
            }
            trans_credit = {
                "id": uuid.uuid4().hex, "date": data['date'], "description": f"{data['description']} depuis {data['source']}",
                "montant": data['montant'], "categorie": "(Virement)", "compte_affecte": data['destination'],
                "pointe": False, "virement_id": virement_id
            }
            
            cle_mois_annee = datetime.strptime(data['date'], "%Y-%m-%d").strftime("%Y-%m")
            if cle_mois_annee not in self.budget_data:
                self.budget_data[cle_mois_annee] = {'categories_prevues': [], 'transactions': []}
            
            self.budget_data[cle_mois_annee]['transactions'].extend([trans_debit, trans_credit])
            self.mettre_a_jour_toutes_les_vues()
            
    def supprimer_compte_selectionne(self):
        selected_item_ids = self.tree.selection()
        if not selected_item_ids:
            messagebox.showinfo("Info", "Sélectionnez un ou plusieurs comptes à supprimer.", parent=self.root)
            return
        
        comptes_a_suppr_noms = []
        for selected_iid in selected_item_ids:
            if not (selected_iid.startswith('___') or selected_iid.startswith('actifs_classe_') or selected_iid.startswith('passifs_terme_') or selected_iid.startswith('___banque_')):
                try:
                    nom_compte_affiche = self.tree.item(selected_iid, 'values')[0].strip()
                    comptes_a_suppr_noms.append(nom_compte_affiche)
                except Exception:
                    continue
        
        if not comptes_a_suppr_noms:
             messagebox.showwarning("Attention", "Veuillez sélectionner des comptes individuels à supprimer.", parent=self.root)
             return

        if messagebox.askyesno("Confirmer", f"Supprimer {len(comptes_a_suppr_noms)} compte(s) ?"):
            self.comptes[:] = [c for c in self.comptes if c.nom not in comptes_a_suppr_noms]
            self.mettre_a_jour_toutes_les_vues()

    def supprimer_categorie_budget(self):
        selection = self.budget_tree.selection()
        if not selection: return
        
        noms_categories = [self.budget_tree.item(item_id)['values'][0] for item_id in selection]

        if messagebox.askyesno("Confirmer", f"Êtes-vous sûr de vouloir supprimer {len(noms_categories)} catégorie(s) ?", parent=self.root):
            cle_mois_annee = f"{self.budget_annee_var.get()}-{self.budget_mois_var.get()}"
            if cle_mois_annee in self.budget_data:
                categories_du_mois = self.budget_data[cle_mois_annee].get('categories_prevues', [])
                self.budget_data[cle_mois_annee]['categories_prevues'][:] = [cat for cat in categories_du_mois if cat['categorie'] not in noms_categories]
                self.mettre_a_jour_toutes_les_vues()

    def supprimer_transaction(self):
        selection = self.transactions_tree.selection()
        if not selection:
            messagebox.showinfo("Information", "Veuillez sélectionner une ou plusieurs transactions à supprimer.", parent=self.root)
            return

        if messagebox.askyesno("Confirmer", f"Êtes-vous sûr de vouloir supprimer {len(selection)} transaction(s) ?", parent=self.root):
            ids_to_delete = set(selection)
            for cle_mois in list(self.budget_data.keys()):
                if isinstance(self.budget_data[cle_mois], dict) and 'transactions' in self.budget_data[cle_mois]:
                    self.budget_data[cle_mois]['transactions'][:] = [t for t in self.budget_data[cle_mois]['transactions'] if t.get('id') not in ids_to_delete]
            
            self.mettre_a_jour_toutes_les_vues()
            
    def verifier_et_afficher_alertes_decouvert(self):
        if not hasattr(self, 'label_alertes_decouvert'): return 

        resultats = self._calculer_projection_mensuelle()
        if not resultats or not resultats.get('details_pour_affichage'):
            self.label_alertes_decouvert.config(text="")
            return

        messages_alerte = []
        for nom_compte_display, data in resultats['details_pour_affichage'].items():
            compte_nom_reel = nom_compte_display.replace(" (-)", "")
            compte = next((c for c in self.comptes if c.nom == compte_nom_reel and c.alerte_decouvert), None)

            if compte:
                solde_previsionnel = data.get('solde_previsionnel', 0.0)
                # Pour les passifs, une alerte serait si le solde devient positif (ce qui est rare)
                # On se concentre sur les actifs qui deviennent négatifs
                if compte.type_compte == 'Actif' and solde_previsionnel < 0:
                    message = (f"Risque de découvert sur '{compte.nom}': Prévisionnel de {format_nombre_fr(solde_previsionnel)} €.")
                    messages_alerte.append(message)
        
        if messages_alerte:
            self.label_alertes_decouvert.config(text="\n".join(messages_alerte), foreground="red")
        else:
            self.label_alertes_decouvert.config(text="Aucune alerte de découvert.", foreground="green")
            
    def ouvrir_gestion_transactions_recurrentes(self):
        RecurrentTransactionManager(self)

    def get_all_budget_categories(self, type_filtre=None):
        all_categories = set()
        for cle, data in self.budget_data.items():
            if not cle.startswith("_") and isinstance(data, dict):
                for cat in data.get('categories_prevues', []):
                    if type_filtre is None or cat.get('type') == type_filtre:
                        all_categories.add(cat['categorie'])

        templates = self.budget_data.get("_templates", {})
        for template_name, template_cats in templates.items():
            for cat in template_cats:
                if type_filtre is None or cat.get('type') == type_filtre:
                    all_categories.add(cat['categorie'])

        return sorted(list(all_categories))

    def generer_transactions_recurrentes_pour_le_mois(self, annee, mois):
        if 'transactions_recurrentes' not in self.budget_data: return

        cle_mois_annee = f"{annee}-{mois:02d}"
        if cle_mois_annee not in self.budget_data:
            self.budget_data[cle_mois_annee] = {'categories_prevues': [], 'transactions': []}
        
        transactions_du_mois = self.budget_data[cle_mois_annee]['transactions']
        categories_prevues_du_mois = self.budget_data[cle_mois_annee]['categories_prevues']
        noms_categories_existantes = {cat['categorie'].lower() for cat in categories_prevues_du_mois}
        
        ids_recurrence_generees_mois = {t.get('id_recurrence') for t in transactions_du_mois if t.get('origine') == 'recurrente'}
        
        modifications_faites = False
        premier_jour_mois = date(annee, mois, 1)
        dernier_jour_mois = (premier_jour_mois.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

        for trans_rec in self.budget_data['transactions_recurrentes']:
            id_recurrence = trans_rec['id']
            periodicite = trans_rec.get('periodicite', 'Mensuelle')

            if id_recurrence in ids_recurrence_generees_mois and periodicite not in ['Hebdomadaire', 'Bi-mensuelle']:
                continue
            if not trans_rec.get('active', False): continue

            date_debut_str = trans_rec.get('date_debut', '1900-01-01')
            date_fin_str = trans_rec.get('date_fin')
            try:
                date_debut = datetime.strptime(date_debut_str, "%Y-%m-%d").date()
                date_fin = datetime.strptime(date_fin_str, "%Y-%m-%d").date() if date_fin_str else date(9999, 12, 31)
            except (ValueError, TypeError): continue

            if date_fin < premier_jour_mois or date_debut > dernier_jour_mois: continue
            
            jour_echeance_str = str(trans_rec.get('jour_echeance', trans_rec.get('jour_du_mois', 1)))
            dates_a_generer = []
            
            if periodicite in ['Mensuelle', 'Trimestrielle', 'Tous les 4 mois', 'Semestrielle', 'Annuelle']:
                # --- DÉBUT DE LA CORRECTION ---
                try:
                    jour_cible = int(jour_echeance_str)
                    # On récupère le nombre de jours dans le mois cible
                    _, nb_jours_du_mois = calendar.monthrange(annee, mois)
                    # Le jour effectif est le minimum entre le jour cible et le dernier jour du mois
                    jour_effectif_mois = min(jour_cible, nb_jours_du_mois)
                except ValueError:
                    continue # Si le jour n'est pas un nombre, on ignore cette règle pour ce mois
                # --- FIN DE LA CORRECTION ---  
                
                mois_debut_regle = date_debut.month
                
                should_generate = False
                if periodicite == 'Mensuelle': should_generate = True
                elif periodicite == 'Trimestrielle' and (mois - mois_debut_regle) % 3 == 0: should_generate = True
                elif periodicite == 'Tous les 4 mois' and (mois - mois_debut_regle) % 4 == 0: should_generate = True
                elif periodicite == 'Semestrielle' and (mois - mois_debut_regle) % 6 == 0: should_generate = True
                elif periodicite == 'Annuelle' and mois == mois_debut_regle: should_generate = True
                
                if should_generate:
                    # --- DÉBUT DE LA CORRECTION ---
                    # Ligne originale (incorrecte) :
                    # try: dates_a_generer.append(date(annee, mois, jour_echeance))
                    # Ligne corrigée :
                    try: dates_a_generer.append(date(annee, mois, jour_effectif_mois))
                    # --- FIN DE LA CORRECTION ---
                    except ValueError: pass
            
            elif periodicite == 'Bi-mensuelle':
                try:
                    jours_echeance = [int(j.strip()) for j in jour_echeance_str.split(',')]
                    for jour in jours_echeance:
                        try: dates_a_generer.append(date(annee, mois, jour))
                        except ValueError: pass
                except ValueError: pass

            elif periodicite == 'Hebdomadaire':
                jour_semaine_cible = int(jour_echeance_str)
                current_day = premier_jour_mois
                while current_day <= dernier_jour_mois:
                    if current_day.isoweekday() == jour_semaine_cible:
                        dates_a_generer.append(current_day)
                    current_day += timedelta(days=1)
            
            for date_trans in dates_a_generer:
                if not (date_debut <= date_trans <= date_fin): continue
                
                id_gen = f"{id_recurrence}_{date_trans.strftime('%Y%m%d')}"
                if id_gen in ids_recurrence_generees_mois: continue

                modifications_faites = True
                
                if trans_rec.get('type') == 'Virement':
                    montant_virement = abs(trans_rec.get('montant', 0.0))
                    source, dest = trans_rec.get('source'), trans_rec.get('destination')
                    if not source or not dest: continue
                    transactions_du_mois.extend([
                        {"id": uuid.uuid4().hex, "id_recurrence": id_gen, "origine": "recurrente", "date": date_trans.strftime("%Y-%m-%d"), "description": f"Virement récurrent vers {dest}", "montant": -montant_virement, "categorie": "(Virement)", "compte_affecte": source, "pointe": False},
                        {"id": uuid.uuid4().hex, "id_recurrence": id_gen, "origine": "recurrente", "date": date_trans.strftime("%Y-%m-%d"), "description": f"Virement récurrent depuis {source}", "montant": montant_virement, "categorie": "(Virement)", "compte_affecte": dest, "pointe": False}
                    ])
                else:
                    nouvelle_trans = {
                        "id": uuid.uuid4().hex, "id_recurrence": id_gen, "origine": "recurrente", "date": date_trans.strftime("%Y-%m-%d"),
                        "description": trans_rec['description'], "montant": trans_rec['montant'], "categorie": trans_rec['categorie'],
                        "compte_affecte": trans_rec['compte_affecte'], "pointe": False
                    }
                    transactions_du_mois.append(nouvelle_trans)

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

        if modifications_faites:
            self.sauvegarder_budget_donnees()
        
    def update_action_buttons_state(self, event=None):
        selected_item_ids = self.tree.selection()
        compte_passif_selectionne = False
        if len(selected_item_ids) == 1:
            selected_iid = selected_item_ids[0]
            if not (selected_iid.startswith('___') or selected_iid.startswith('actifs_classe_') or selected_iid.startswith('passifs_terme_') or selected_iid.startswith('___banque_')):
                try:
                    nom_compte_affiche = self.tree.item(selected_iid, 'values')[0].strip()
                    compte = next((c for c in self.comptes if c.nom == nom_compte_affiche), None)
                    if compte and compte.type_compte == 'Passif':
                        compte_passif_selectionne = True
                except Exception:
                    pass
        self.bouton_echeancier.config(state=tk.NORMAL if compte_passif_selectionne else tk.DISABLED)

    def importer_echeancier(self):
        selection = self.tree.selection()
        if not selection: return
        nom_compte_passif = self.tree.item(selection[0], 'values')[0].strip()
        compte_passif = next((c for c in self.comptes if c.nom == nom_compte_passif), None)
        if not compte_passif or compte_passif.type_compte != 'Passif':
            messagebox.showerror("Erreur", "Veuillez sélectionner un seul compte de type 'Passif'.", parent=self.root)
            return

        comptes_suivis = [c.nom for c in self.comptes if c.suivi_budget and c.type_compte == 'Actif']
        if not comptes_suivis:
            messagebox.showerror("Erreur", "Aucun compte de dépenses (Actif avec suivi budget) n'est disponible pour le paiement.", parent=self.root)
            return
            
        dialog_compte = SelectFromListDialog(self.root, "Compte Source", "Depuis quel compte les mensualités seront-elles payées ?", comptes_suivis)
        compte_source_paiement = dialog_compte.result
        if not compte_source_paiement: return

        categories_depenses = self.get_all_budget_categories(type_filtre='Dépense')
        if not categories_depenses:
            messagebox.showerror("Erreur", "Aucune catégorie de dépense n'a été créée. Veuillez en créer une d'abord.", parent=self.root)
            return

        dialog_cat_int = SelectFromListDialog(self.root, "Catégorie Intérêts", "Dans quelle catégorie de dépense classer les intérêts ?", categories_depenses)
        cat_interets = dialog_cat_int.result
        if not cat_interets: return
            
        dialog_cat_ass = SelectFromListDialog(self.root, "Catégorie Assurance", "Dans quelle catégorie de dépense classer l'assurance ?\n(Annuler si non applicable)", categories_depenses)
        cat_assurance = dialog_cat_ass.result

        filename = filedialog.askopenfilename(title=f"Sélectionner l'échéancier pour '{nom_compte_passif}'", filetypes=[("Fichiers CSV (*.csv)", "*.csv")], parent=self.root)
        if not filename: return

        try:
            lignes_ajoutees = 0
            with open(filename, 'r', newline='', encoding='utf-8-sig') as f_csv:
                reader = csv.DictReader(f_csv, delimiter=';')
                headers = reader.fieldnames
                if not all(h in headers for h in ['Date', 'Capital', 'Interets']):
                    messagebox.showerror("Erreur de Fichier", "Le fichier CSV doit contenir au minimum les colonnes 'Date', 'Capital', et 'Interets'.", parent=self.root)
                    return

                for row in reader:
                    try:
                        date_str = row['Date']
                        if '/' in date_str: date_obj = datetime.strptime(date_str, "%d/%m/%Y")
                        else: date_obj = datetime.strptime(date_str, "%Y-%m-%d")

                        capital = float(row['Capital'].replace(',', '.'))
                        interets = float(row['Interets'].replace(',', '.'))
                        assurance = float(row['Assurance'].replace(',', '.')) if 'Assurance' in row and row['Assurance'] else 0.0

                        cle_mois_annee = date_obj.strftime("%Y-%m")
                        if cle_mois_annee not in self.budget_data:
                            self.budget_data[cle_mois_annee] = {'categories_prevues': [], 'transactions': []}
                        
                        transactions_du_mois = self.budget_data[cle_mois_annee]['transactions']

                        if capital > 0:
                            id_virement = uuid.uuid4().hex
                            trans_sortie_k = { "id": uuid.uuid4().hex, "virement_id": id_virement, "origine": "echeancier", "date": date_obj.strftime("%Y-%m-%d"), "description": f"Remb. Capital Prêt {nom_compte_passif}", "montant": -capital, "categorie": "(Virement)", "compte_affecte": compte_source_paiement, "pointe": False }
                            trans_entree_k = { "id": uuid.uuid4().hex, "virement_id": id_virement, "origine": "echeancier", "date": date_obj.strftime("%Y-%m-%d"), "description": f"Remb. Capital Prêt {nom_compte_passif}", "montant": capital, "categorie": "(Virement)", "compte_affecte": nom_compte_passif, "pointe": False }
                            transactions_du_mois.extend([trans_sortie_k, trans_entree_k])

                        if interets > 0:
                            trans_interets = { "id": uuid.uuid4().hex, "origine": "echeancier", "date": date_obj.strftime("%Y-%m-%d"), "description": f"Intérêts Prêt {nom_compte_passif}", "montant": -interets, "categorie": cat_interets, "compte_affecte": compte_source_paiement, "pointe": False }
                            transactions_du_mois.append(trans_interets)

                        if assurance > 0 and cat_assurance:
                            trans_assurance = { "id": uuid.uuid4().hex, "origine": "echeancier", "date": date_obj.strftime("%Y-%m-%d"), "description": f"Assurance Prêt {nom_compte_passif}", "montant": -assurance, "categorie": cat_assurance, "compte_affecte": compte_source_paiement, "pointe": False }
                            transactions_du_mois.append(trans_assurance)
                        
                        lignes_ajoutees += 1
                    except (ValueError, KeyError) as row_err:
                        print(f"Ligne ignorée dans le CSV : {row}. Erreur : {row_err}")
                        continue
            
            self.sauvegarder_budget_donnees()
            self.mettre_a_jour_toutes_les_vues()
            messagebox.showinfo("Importation Réussie", f"{lignes_ajoutees} échéances ont été importées comme transactions futures.", parent=self.root)

        except FileNotFoundError: messagebox.showerror("Erreur", f"Fichier non trouvé: {filename}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Erreur d'Importation", f"Une erreur imprévue est survenue:\n{e}", parent=self.root)
            traceback.print_exc()

    def mettre_a_jour_graphique_historique_personnalise(self):
        if self.graph_manager:
            comptes_selectionnes = [nom for nom, var in self.vars_comptes_historique.items() if var.get()]
            self.graph_manager.update_historique_personnalise(self.historique_patrimoine, comptes_selectionnes)

    def generer_rapport_mensuel(self):
        cle_mois_annee = f"{self.budget_annee_var.get()}-{self.budget_mois_var.get()}"
        donnees_du_mois = self.budget_data.get(cle_mois_annee, {})
        transactions_du_mois = donnees_du_mois.get('transactions', [])
        
        if not transactions_du_mois:
            messagebox.showinfo("Rapport Mensuel", f"Aucune transaction n'a été trouvée pour le mois de {cle_mois_annee}.", parent=self.root)
            return

        RapportMensuelWindow(self.root, cle_mois_annee, self.budget_data, self.historique_patrimoine)
        
    def nettoyer_historique(self):
        if not self.historique_patrimoine:
            return

        histo_nettoye = []
        snapshots_par_mois = defaultdict(list)
        
        for snap in self.historique_patrimoine:
            try:
                snap_date = datetime.strptime(snap['date'], "%Y-%m-%d").date()
                cle_mois = snap_date.strftime("%Y-%m")
                snapshots_par_mois[cle_mois].append(snap)
            except (ValueError, KeyError):
                continue

        mois_actuel_str = date.today().strftime("%Y-%m")

        for cle_mois, snaps_du_mois in snapshots_par_mois.items():
            if not snaps_du_mois:
                continue
                
            snaps_du_mois.sort(key=lambda x: x['date'])

            if cle_mois == mois_actuel_str:
                histo_nettoye.extend(snaps_du_mois)
            else:
                histo_nettoye.append(snaps_du_mois[0])
                if len(snaps_du_mois) > 1:
                    histo_nettoye.append(snaps_du_mois[-1])

        liste_finale_sans_doublons = []
        vus = set()
        for snap in histo_nettoye:
            identifiant = snap['date'] 
            if identifiant not in vus:
                liste_finale_sans_doublons.append(snap)
                vus.add(identifiant)

        liste_finale_sans_doublons.sort(key=lambda x: x['date'])
        self.historique_patrimoine = liste_finale_sans_doublons

    def ouvrir_fenetre_purge_transactions(self):
        date_limite_str = simpledialog.askstring("Purger les Données du Budget", 
                                                 "Veuillez saisir la date limite.\n"
                                                 "TOUTES les données de budget (transactions, règles) ANTÉRIEURES\n"
                                                 "à cette date seront supprimées ou mises à jour.\n\n"
                                                 "Format : AAAA-MM-JJ",
                                                 initialvalue="2025-06-01",
                                                 parent=self.root)
        
        if not date_limite_str:
            return

        try:
            date_limite = datetime.strptime(date_limite_str, "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror("Format invalide", "Le format de la date est incorrect. L'opération a été annulée.", parent=self.root)
            return

        msg = (f"Vous allez purger toutes les données de budget avant le {date_limite.strftime('%d/%m/%Y')}.\n\n"
               f"Ceci va :\n"
               f"1. Supprimer les transactions individuelles passées.\n"
               f"2. Supprimer les règles récurrentes terminées avant cette date.\n"
               f"3. Mettre à jour la date de début des règles récurrentes encore actives.\n\n"
               f"L'action est IRRÉVERSIBLE. Êtes-vous certain de vouloir continuer ?")

        if not messagebox.askyesno("CONFIRMATION FINALE REQUISE", msg, icon='error', parent=self.root):
            messagebox.showinfo("Annulé", "L'opération de purge a été annulée.", parent=self.root)
            return

        transactions_supprimees, regles_modifiees, regles_supprimees = 0, 0, 0

        for cle in list(self.budget_data.keys()):
            if isinstance(self.budget_data[cle], dict) and not cle.startswith("_"):
                transactions_mois = self.budget_data[cle].get('transactions', [])
                transactions_a_garder = []
                for trans in transactions_mois:
                    try:
                        trans_date = datetime.strptime(trans.get('date'), "%Y-%m-%d").date()
                        if trans_date >= date_limite:
                            transactions_a_garder.append(trans)
                        else:
                            transactions_supprimees += 1
                    except (ValueError, TypeError):
                        transactions_a_garder.append(trans)
                self.budget_data[cle]['transactions'] = transactions_a_garder

        regles_recurrentes_actives = []
        for regle in self.budget_data.get('transactions_recurrentes', []):
            try:
                date_debut_regle_str = regle.get('date_debut')
                date_fin_regle_str = regle.get('date_fin')

                if not date_debut_regle_str:
                    regles_recurrentes_actives.append(regle)
                    continue

                date_debut_regle = datetime.strptime(date_debut_regle_str, "%Y-%m-%d").date()
                date_fin_regle = datetime.strptime(date_fin_regle_str, "%Y-%m-%d").date() if date_fin_regle_str else None

                if date_fin_regle and date_fin_regle < date_limite:
                    regles_supprimees += 1
                    continue 

                if date_debut_regle < date_limite:
                    regle['date_debut'] = date_limite.strftime("%Y-%m-%d")
                    regles_modifiees += 1
                
                regles_recurrentes_actives.append(regle)

            except (ValueError, TypeError):
                regles_recurrentes_actives.append(regle)

        self.budget_data['transactions_recurrentes'] = regles_recurrentes_actives

        self.sauvegarder_budget_donnees()
        self.mettre_a_jour_toutes_les_vues()

        rapport_final = (f"Opération de purge terminée !\n\n"
                         f"- Transactions individuelles supprimées : {transactions_supprimees}\n"
                         f"- Règles récurrentes mises à jour : {regles_modifiees}\n"
                         f"- Règles récurrentes obsolètes supprimées : {regles_supprimees}")
        
        messagebox.showinfo("Purge Terminée", rapport_final, parent=self.root)

    def ouvrir_fenetre_fusion_categories(self):
        try:
            all_categories = set()
            for cle in list(self.budget_data.keys()):
                data = self.budget_data.get(cle)
                if cle == "_templates":
                    if isinstance(data, dict):
                        for template_name, template_cats in data.items():
                            if isinstance(template_cats, list):
                                for cat in template_cats:
                                    all_categories.add(cat.get('categorie'))
                elif isinstance(data, dict) and not cle.startswith("_"):
                    for cat in data.get('categories_prevues', []): 
                        all_categories.add(cat.get('categorie'))
                    for trans in data.get('transactions', []):
                        cat_name = trans.get('categorie')
                        if cat_name and cat_name != "(Virement)":
                            all_categories.add(cat_name)
            
            for trans_rec in self.budget_data.get('transactions_recurrentes', []):
                cat_name = trans_rec.get('categorie')
                if cat_name and cat_name != "(Virement)":
                    all_categories.add(cat_name)
                    
            sorted_categories = sorted([cat for cat in all_categories if cat])
            
            if not sorted_categories:
                messagebox.showinfo("Aucune Catégorie", "Aucune catégorie de budget à fusionner n'a été trouvée.", parent=self.root)
                return

        except Exception as e:
            messagebox.showerror("Erreur de Lecture", f"Impossible de lire les catégories existantes.\n\nErreur : {e}", parent=self.root)
            traceback.print_exc()
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Outil de Fusion des Catégories")
        dialog.geometry("600x400")
        dialog.transient(self.root)
        dialog.grab_set()

        main_frame = ttk.Frame(dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        source_frame = ttk.LabelFrame(main_frame, text="1. Sélectionner la ou les catégorie(s) à fusionner", padding=5)
        source_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        source_listbox = tk.Listbox(source_frame, selectmode=tk.EXTENDED, exportselection=False)
        for cat in sorted_categories: source_listbox.insert(tk.END, cat)
        source_listbox.pack(fill=tk.BOTH, expand=True)

        dest_frame = ttk.LabelFrame(main_frame, text="2. Choisir ou saisir la catégorie de destination", padding=5)
        dest_frame.pack(fill=tk.X, pady=5)
        
        dest_var = tk.StringVar()
        dest_combo = ttk.Combobox(dest_frame, textvariable=dest_var, values=sorted_categories)
        dest_combo.pack(fill=tk.X, expand=True)

        def _executer_fusion():
            sources_indices = source_listbox.curselection()
            if not sources_indices:
                messagebox.showwarning("Aucune sélection", "Veuillez sélectionner au moins une catégorie source.", parent=dialog)
                return
                
            sources = [source_listbox.get(i) for i in sources_indices]
            destination = dest_var.get().strip()

            if not destination:
                messagebox.showwarning("Aucune destination", "Veuillez choisir une catégorie de destination.", parent=dialog)
                return
            
            if destination in sources:
                messagebox.showerror("Conflit", "La catégorie de destination ne peut pas être l'une des sources.", parent=dialog)
                return

            msg = f"Êtes-vous sûr de vouloir fusionner {len(sources)} catégorie(s) dans '{destination}' ?\n\n"
            msg += "Cette action est IRRÉVERSIBLE et modifiera l'intégralité de vos données de budget."
            
            if not messagebox.askyesno("Confirmer la fusion", msg, icon='warning', parent=dialog):
                return

            for cle in list(self.budget_data.keys()):
                data = self.budget_data.get(cle)
                if cle == "_templates" and isinstance(data, dict):
                    for template_name in data:
                        if isinstance(data[template_name], list):
                            cats_a_garder = [cat for cat in data[template_name] if cat.get('categorie') not in sources]
                            self.budget_data[cle][template_name] = cats_a_garder
                elif isinstance(data, dict) and not cle.startswith("_"):
                    for trans in data.get('transactions', []):
                        if trans.get('categorie') in sources: trans['categorie'] = destination
                    cats_prevues_a_garder = [cat for cat in data.get('categories_prevues', []) if cat.get('categorie') not in sources]
                    self.budget_data[cle]['categories_prevues'] = cats_prevues_a_garder
            
            for trans_rec in self.budget_data.get('transactions_recurrentes', []):
                if trans_rec.get('categorie') in sources:
                    trans_rec['categorie'] = destination

            self.sauvegarder_budget_donnees()
            self.mettre_a_jour_toutes_les_vues()
            
            messagebox.showinfo("Succès", "La fusion des catégories a été effectuée avec succès.", parent=dialog)
            dialog.destroy()

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10,0))
        ttk.Button(button_frame, text="Fusionner", command=_executer_fusion).pack(side=tk.RIGHT)
        ttk.Button(button_frame, text="Annuler", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

        self.root.wait_window(dialog)

    def solder_ou_reouvrir_categorie(self):
        selection = self.budget_tree.selection()
        if not selection: return
        
        nom_categorie = self.budget_tree.item(selection[0])['values'][0]
        cle_mois_annee = f"{self.budget_annee_var.get()}-{self.budget_mois_var.get()}"
        categories_prevues_mois = self.budget_data.get(cle_mois_annee, {}).get('categories_prevues', [])
        cat_trouvee = next((cat for cat in categories_prevues_mois if cat['categorie'] == nom_categorie), None)

        if not cat_trouvee:
            messagebox.showwarning("Action impossible", "Impossible de solder une catégorie qui n'a pas de prévisionnel défini.", parent=self.root)
            return

        cat_trouvee['soldee'] = not cat_trouvee.get('soldee', False)
        self.mettre_a_jour_toutes_les_vues()
        
    def _update_header_arrows(self, tree, tri_state):
        for col in tree["columns"]:
            text = tree.heading(col, "text")
            if ' ▲' in text: text = text.replace(' ▲', '')
            if ' ▼' in text: text = text.replace(' ▼', '')
            
            if col == tri_state['col']:
                arrow = ' ▲' if not tri_state['reverse'] else ' ▼'
                tree.heading(col, text=text + arrow)
            else:
                tree.heading(col, text=text)

    def definir_tri_budget(self, col_id):
        if self.tri_budget['col'] == col_id:
            self.tri_budget['reverse'] = not self.tri_budget['reverse']
        else:
            self.tri_budget['col'] = col_id
            self.tri_budget['reverse'] = False
        self.mettre_a_jour_toutes_les_vues()

    def definir_tri_transactions(self, col_id):
        if self.tri_transactions['col'] == col_id:
            self.tri_transactions['reverse'] = not self.tri_transactions['reverse']
        else:
            self.tri_transactions['col'] = col_id
            self.tri_transactions['reverse'] = col_id == 'montant' 
        self.mettre_a_jour_toutes_les_vues()

    def _evaluate_math_in_entry(self, entry_widget):
        import ast
        import operator as op
        operators = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.Pow: op.pow, ast.USub: op.neg}
        def eval_expr(expr_str):
            def _eval(node):
                if isinstance(node, ast.Constant): return node.value
                elif isinstance(node, ast.BinOp): return operators[type(node.op)](_eval(node.left), _eval(node.right))
                elif isinstance(node, ast.UnaryOp): return operators[type(node.op)](_eval(node.operand))
                else: raise TypeError(node)
            expr_str_safe = expr_str.replace(',', '.')
            if not all(c in '0123456789.+-*/()^ ' for c in expr_str_safe): return None
            return _eval(ast.parse(expr_str_safe, mode='eval').body)
        expression = entry_widget.get()
        if not expression: return
        try:
            resultat = eval_expr(expression)
            if resultat is not None:
                s_formate = "{:_.2f}".format(resultat).replace('_', ' ').replace('.', ',')
                entry_widget.delete(0, tk.END)
                entry_widget.insert(0, s_formate)
        except (TypeError, SyntaxError, KeyError, ZeroDivisionError):
            pass
            
    def solder_carte_differee(self):
        comptes_passifs = sorted([c.nom for c in self.comptes if c.type_compte == 'Passif' and abs(c.solde) > 0])
        comptes_actifs_budget = sorted([c.nom for c in self.comptes if c.type_compte == 'Actif' and c.suivi_budget])

        if not comptes_passifs:
            messagebox.showinfo("Information", "Aucun compte passif avec un solde à régler n'a été trouvé.", parent=self.root)
            return
        if not comptes_actifs_budget:
            messagebox.showinfo("Information", "Aucun compte actif participant au budget n'a été trouvé pour effectuer le paiement.", parent=self.root)
            return

        dialog = tk.Toplevel(self.root)
        dialog.transient(self.root)
        dialog.title("Solder une Carte à Débit Différé")
        dialog.geometry("450x230")
        dialog.resizable(False, False)
        dialog.grab_set()

        form_frame = ttk.Frame(dialog, padding="15")
        form_frame.pack(fill=tk.BOTH, expand=True)
        form_frame.columnconfigure(1, weight=1)

        ttk.Label(form_frame, text="Date du prélèvement:").grid(row=0, column=0, sticky=tk.W, pady=5)
        date_entry = ttk.Entry(form_frame)
        date_entry.insert(0, date.today().strftime("%Y-%m-%d"))
        date_entry.grid(row=0, column=1, sticky=tk.EW)

        ttk.Label(form_frame, text="Carte à solder (Compte Passif):").grid(row=1, column=0, sticky=tk.W, pady=5)
        carte_var = tk.StringVar()
        carte_combo = ttk.Combobox(form_frame, textvariable=carte_var, values=comptes_passifs, state="readonly")
        carte_combo.grid(row=1, column=1, sticky=tk.EW)

        ttk.Label(form_frame, text="Débiter le compte (Compte Actif):").grid(row=2, column=0, sticky=tk.W, pady=5)
        source_var = tk.StringVar()
        source_combo = ttk.Combobox(form_frame, textvariable=source_var, values=comptes_actifs_budget, state="readonly")
        source_combo.grid(row=2, column=1, sticky=tk.EW)
        
        if comptes_actifs_budget: source_combo.current(0)

        def on_validate():
            carte_nom = carte_var.get()
            source_nom = source_var.get()
            date_str = date_entry.get().strip()
            
            if not all([carte_nom, source_nom, date_str]):
                messagebox.showwarning("Champs requis", "Veuillez remplir tous les champs.", parent=dialog)
                return

            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Erreur de format", "Le format de la date est invalide (AAAA-MM-JJ).", parent=dialog)
                return
            
            compte_carte = next((c for c in self.comptes if c.nom == carte_nom), None)
            if not compte_carte: return

            montant_a_regler = abs(compte_carte.solde)
            if montant_a_regler == 0:
                messagebox.showinfo("Information", "Le solde de cette carte est déjà à zéro.", parent=dialog)
                return

            id_virement = uuid.uuid4().hex
            trans_sortie = {
                "id": uuid.uuid4().hex, "virement_id": id_virement, "date": date_obj.strftime("%Y-%m-%d"),
                "description": f"Règlement CB {carte_nom}", "montant": -montant_a_regler,
                "categorie": "(Virement)", "compte_affecte": source_nom, "pointe": False
            }
            trans_entree = {
                "id": uuid.uuid4().hex, "virement_id": id_virement, "date": date_obj.strftime("%Y-%m-%d"),
                "description": f"Apurement solde CB {carte_nom}", "montant": montant_a_regler,
                "categorie": "(Virement)", "compte_affecte": carte_nom, "pointe": False
            }

            cle_mois_annee = date_obj.strftime("%Y-%m")
            if cle_mois_annee not in self.budget_data:
                self.budget_data[cle_mois_annee] = {'categories_prevues': [], 'transactions': []}
            
            self.budget_data[cle_mois_annee]['transactions'].extend([trans_sortie, trans_entree])
            self.sauvegarder_budget_donnees()
            self.mettre_a_jour_toutes_les_vues()
            messagebox.showinfo("Opération Réussie", f"Le règlement de la carte {carte_nom} a bien été enregistré.", parent=self.root)
            dialog.destroy()

        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=15, sticky=tk.E)
        ttk.Button(button_frame, text="Valider le Solde", command=on_validate).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Annuler", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

        self.root.wait_window(dialog)

    def afficher_a_propos(self):
        messagebox.showinfo(
            "À Propos de SLC Budget",
            "SLC Budget & Finances\n\n"
            "Version 1.1.1 (Correctifs & Stabilité)\n"
            "Année : 2025\n\n"
            "Créé par : Sébastien LE CORRE\n\n"
            "Une application pour suivre votre budget et votre patrimoine.",
            parent=self.root
        )

    def ouvrir_notice(self):
        try:
            notice_path = os.path.join(BASE_DIR, "notice.pdf") 
            if not os.path.exists(notice_path):
                messagebox.showerror("Fichier introuvable", f"Le fichier de notice '{notice_path}' n'a pas été trouvé.", parent=self.root)
                return
            os.startfile(notice_path)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'ouvrir le fichier : {e}", parent=self.root)

    def _get_all_transactions(self):
        all_trans = []
        for cle, data in self.budget_data.items():
            if not cle.startswith("_") and isinstance(data, dict) and 'transactions' in data:
                all_trans.extend(data['transactions'])
        return all_trans

    def lancer_detection_recurrences(self):
        all_trans = self._get_all_transactions()
        existing_rules = self.budget_data.get('transactions_recurrentes', [])

        if not all_trans:
            messagebox.showinfo("Détection", "Pas assez de transactions pour lancer une analyse.", parent=self.root)
            return

        suggestions = self.ai_service.detect_recurring_transactions(all_trans, existing_rules)

        if not suggestions:
            messagebox.showinfo("Détection", "Aucune nouvelle transaction récurrente potentielle n'a été détectée.", parent=self.root)
            return

        suggestions_ajoutees = 0
        for sugg in suggestions:
            montant_abs = abs(sugg['montant'])
            jour = sugg['jour_du_mois']
            desc = sugg['description']

            question = (f"Nous avons détecté une transaction potentiellement récurrente :\n\n"
                        f"Description : '{desc}'\n"
                        f"Montant : ~{format_nombre_fr(montant_abs)} €\n"
                        f"Jour du mois : ~{jour}\n\n"
                        f"Voulez-vous créer une règle de transaction récurrente pour cela ?")

            if messagebox.askyesno("Suggestion de Récurrence", question, parent=self.root):
                nouvelle_regle = {
                    "id": uuid.uuid4().hex, "active": True, "jour_du_mois": jour,
                    "jour_echeance": str(jour), "description": sugg['description'],
                    "montant": sugg['montant'], "categorie": sugg['categorie'],
                    "type": sugg['type'], "compte_affecte": None,
                    "source": None, "destination": None,
                    "date_debut": date.today().strftime("%Y-%m-%d"),
                    "date_fin": None, "periodicite": "Mensuelle"
                }
                self.budget_data['transactions_recurrentes'].append(nouvelle_regle)
                suggestions_ajoutees += 1

        if suggestions_ajoutees > 0:
            self.sauvegarder_budget_donnees()
            messagebox.showinfo("Succès", 
                                f"{suggestions_ajoutees} nouvelle(s) règle(s) ont été ajoutées.\n\n"
                                f"N'oubliez pas d'aller dans 'Gérer les Transactions Récurrentes' pour leur assigner un compte.",
                                parent=self.root)

    def ouvrir_gestion_portefeuille(self, compte):
        PortfolioManagerWindow(self, compte, self.market_service)

    def lancer_actualisation_globale(self):
        self.root.config(cursor="watch")
        self.root.update()

        comptes_a_mettre_a_jour = [c for c in self.comptes if c.classe_actif == "Actions/Titres" and c.lignes_portefeuille]

        if not comptes_a_mettre_a_jour:
            messagebox.showinfo("Information", "Aucun compte de portefeuille avec des lignes à mettre à jour n'a été trouvé.", parent=self.root)
            self.root.config(cursor="")
            return

        total_lignes = sum(len(c.lignes_portefeuille) for c in comptes_a_mettre_a_jour)
        if not messagebox.askyesno("Confirmer", f"Vous allez interroger Internet pour mettre à jour les cours de {total_lignes} ligne(s).\nL'application peut être gelée pendant quelques instants.\n\nContinuer ?", parent=self.root):
            self.root.config(cursor="")
            return

        for compte in comptes_a_mettre_a_jour:
            valeur_titres = 0
            for ligne in compte.lignes_portefeuille:
                prix_eur = self.market_service.get_price_in_eur(ligne.ticker)
                if prix_eur is not None:
                    ligne.dernier_cours = prix_eur
                    valeur_titres += ligne.quantite * prix_eur
                else:
                    valeur_titres += ligne.quantite * ligne.pru
            
            compte.solde = valeur_titres + compte.solde_especes

        print("INFO: Actualisation terminée. Mise à jour de l'affichage...")
        self.mettre_a_jour_toutes_les_vues()
        self.sauvegarder_donnees()
        self.root.config(cursor="")
        messagebox.showinfo("Succès", "Les soldes de tous les portefeuilles ont été mis à jour avec les derniers cours du marché.", parent=self.root)

    def afficher_detail_solde_previsionnel(self):
        print("INFO: Affichage du détail du solde prévisionnel...")
        resultats = self._calculer_projection_mensuelle()
        if resultats:
            DetailPrevisionnelWindow(self.root, 
                                     resultats['details_pour_affichage'], 
                                     resultats['lignes_budget_futures'], 
                                     resultats.get('total_previsionnel_actifs', 0.0),
                                     resultats.get('total_previsionnel_passifs', 0.0),
                                     resultats.get('total_previsionnel_net', 0.0))
        else:
            messagebox.showinfo("Information", "Impossible de calculer les prévisions.", parent=self.root)
            
    def _calculer_projection_mensuelle(self):
        try:
            annee = int(self.budget_annee_var.get())
            mois = int(self.budget_mois_var.get())
        except (ValueError, TypeError):
            return None

        comptes_suivis = [c for c in self.comptes if c.suivi_budget]
        if not comptes_suivis: return None

        comptes_suivis_dict = {c.nom: c for c in comptes_suivis}
        activite_par_compte = {c.nom: 0.0 for c in comptes_suivis}
        impact_budget_restant_par_compte = {c.nom: 0.0 for c in comptes_suivis}
        
        toutes_les_transactions = self._get_all_transactions()
        cle_mois_annee = f"{annee:04d}-{mois:02d}"

        transactions_du_mois_en_cours = [t for t in toutes_les_transactions if self._parse_date_flexible(t['date']).strftime('%Y-%m') == cle_mois_annee]

        realise_par_categorie = defaultdict(float)
        for t in transactions_du_mois_en_cours:
            if t.get('categorie') != "(Virement)":
                realise_par_categorie[t.get('categorie')] += t.get('montant', 0.0)

        cartes_passives = [c for c in comptes_suivis if c.type_compte == 'Passif']
        lignes_budget_futures = []
        for carte in cartes_passives:
            if not all([carte.jour_debit, carte.jour_debut_periode, carte.jour_fin_periode, carte.compte_debit_associe]):
                continue
            # --- DÉBUT DE LA CORRECTION ---
            # On vérifie si un virement de règlement pour cette carte a déjà été saisi ce mois-ci
            reglement_deja_saisi = any(
                t.get('categorie') == '(Virement)' and
                (
                    # Soit on trouve le débit sur le compte source vers la carte
                    (t.get('compte_affecte') == carte.compte_debit_associe and f"vers {carte.nom}" in t.get('description', '')) or
                    # Soit on trouve le crédit sur la carte depuis le compte source
                    (t.get('compte_affecte') == carte.nom and f"depuis {carte.compte_debit_associe}" in t.get('description', '')) or
                    # Vérification plus générique sur la description
                    (f"Règlement CB {carte.nom}" in t.get('description', ''))
                )
                for t in transactions_du_mois_en_cours
            )

            # Si le règlement a déjà été créé (même s'il n'est pas pointé), on passe à la carte suivante
            if reglement_deja_saisi:
                print(f"INFO (Projection): Le règlement pour '{carte.nom}' est déjà saisi pour ce mois. La simulation est ignorée.")
                continue
            # --- FIN DE LA CORRECTION ---
                
            try:
                # --- DÉBUT DE LA CORRECTION ---
                # On détermine le mois/année de la période de relevé précédente
                annee_debut = annee if mois > 1 else annee - 1
                mois_debut = mois - 1 if mois > 1 else 12

                # On s'assure que les jours sont valides pour les mois concernés
                _, nb_jours_mois_precedent = calendar.monthrange(annee_debut, mois_debut)
                jour_debut_effectif = min(carte.jour_debut_periode, nb_jours_mois_precedent)

                _, nb_jours_mois_en_cours = calendar.monthrange(annee, mois)
                jour_fin_effectif = min(carte.jour_fin_periode, nb_jours_mois_en_cours)

                # On crée les dates avec les jours corrigés et valides
                date_fin_releve = date(annee, mois, jour_fin_effectif)
                date_debut_releve = date(annee_debut, mois_debut, jour_debut_effectif)
                # --- FIN DE LA CORRECTION ---

                transactions_reglement_carte = [
                    t for t in toutes_les_transactions 
                    if t.get('compte_affecte') == carte.nom 
                    and date_debut_releve <= self._parse_date_flexible(t['date']) <= date_fin_releve
                    and t.get('categorie') != '(Virement)'
                    and t.get('pointe', False)
                ]
                
                montant_a_regler = sum(t.get('montant', 0.0) for t in transactions_reglement_carte)
                
                if montant_a_regler != 0 and carte.compte_debit_associe in comptes_suivis_dict:
                    impact_debit = -abs(montant_a_regler)
                    activite_par_compte[carte.compte_debit_associe] += impact_debit
                    lignes_budget_futures.append(f"  Prélèvement {carte.nom} sur {carte.compte_debit_associe}: {format_nombre_fr(impact_debit)} €")

                    impact_credit = abs(montant_a_regler)
                    activite_par_compte[carte.nom] += impact_credit
                    lignes_budget_futures.append(f"  Apurement solde {carte.nom}: +{format_nombre_fr(impact_credit)} €")

            except (ValueError, TypeError) as e:
                print(f"  -> AVERTISSEMENT: Impossible de calculer le règlement pour {carte.nom}. Erreur: {e}")
                continue

        _, nb_jours_mois = calendar.monthrange(annee, mois)
        date_fin_mois_actuel = date(annee, mois, nb_jours_mois)
        
        for t in toutes_les_transactions:
            if not t.get('pointe', False) and self._parse_date_flexible(t['date']) <= date_fin_mois_actuel:
                if t.get('compte_affecte') in comptes_suivis_dict:
                     activite_par_compte[t.get('compte_affecte')] += t.get('montant', 0.0)
        
        for cat in self.budget_data.get(cle_mois_annee, {}).get('categories_prevues', []):
            if cat.get('soldee', False): continue

            compte_prevu = cat.get('compte_prevu')
            if not compte_prevu or compte_prevu not in comptes_suivis_dict: continue
                
            daily_details = cat.get('details')
            realise_pour_cette_cat = realise_par_categorie.get(cat.get('categorie'), 0.0)

            if daily_details:
                transactions_de_la_cat = [t for t in transactions_du_mois_en_cours if t.get('categorie') == cat.get('categorie')]
                jours_avec_transaction_reelle = {self._parse_date_flexible(t['date']).day for t in transactions_de_la_cat}

                impact_detail_reste_a_faire = 0.0
                for detail in daily_details:
                    jour_budget, montant_detail = detail.get('jour'), detail.get('montant')
                    est_neutralise, a_une_transaction = detail.get('neutralise', False), jour_budget in jours_avec_transaction_reelle
                    
                    if not est_neutralise and not a_une_transaction:
                        impact_detail_reste_a_faire += montant_detail

                impact_final = -impact_detail_reste_a_faire if cat.get('type') == 'Dépense' else impact_detail_reste_a_faire
                impact_budget_restant_par_compte[compte_prevu] += impact_final

            else:
                prevu_signe = -cat.get('prevu', 0.0) if cat.get('type') == 'Dépense' else cat.get('prevu', 0.0)
                reste_a_impacter = prevu_signe - realise_pour_cette_cat
                if abs(reste_a_impacter) > 0.01:
                    impact_budget_restant_par_compte[compte_prevu] += reste_a_impacter

        details_pour_affichage = {}
        total_previsionnel_actifs, total_previsionnel_passifs = 0.0, 0.0

        for compte in comptes_suivis:
            est_passif = compte.type_compte == 'Passif'
            nom_display = f"{compte.nom} (-)" if est_passif else compte.nom
            solde_pointe_display = abs(compte.solde)
            activite_mois = activite_par_compte.get(compte.nom, 0.0)
            impact_budget = impact_budget_restant_par_compte.get(compte.nom, 0.0)

            if est_passif:
                solde_virtuel_display = solde_pointe_display - activite_mois
                solde_previsionnel_display = solde_virtuel_display - impact_budget
                total_previsionnel_passifs += solde_previsionnel_display
            else:
                solde_virtuel_display = solde_pointe_display + activite_mois
                solde_previsionnel_display = solde_virtuel_display + impact_budget
                total_previsionnel_actifs += solde_previsionnel_display
            
            details_pour_affichage[nom_display] = {
                'solde_pointe': solde_pointe_display, 'activite_mois': activite_mois,
                'solde_virtuel': solde_virtuel_display, 'impact_budget': impact_budget,
                'solde_previsionnel': solde_previsionnel_display
            }
        
        total_previsionnel_net = total_previsionnel_actifs - total_previsionnel_passifs
        
        dates_graphe = [date(annee, mois, jour) for jour in range(1, nb_jours_mois + 1)]
        evolution_par_compte = {}
        comptes_actifs = [c for c in comptes_suivis if c.type_compte == 'Actif']
        
        for compte in comptes_actifs:
            evolution_par_compte[compte.nom] = []
            solde_courant = compte.solde
            for jour in range(1, nb_jours_mois + 1):
                date_jour = date(annee, mois, jour)
                for t in toutes_les_transactions:
                     if not t.get('pointe') and t.get('compte_affecte') == compte.nom and self._parse_date_flexible(t['date']) == date_jour:
                         solde_courant += t.get('montant', 0.0)
                if jour == nb_jours_mois:
                     solde_courant += impact_budget_restant_par_compte.get(compte.nom, 0.0)
                     for carte in cartes_passives:
                         if carte.compte_debit_associe == compte.nom:
                            # --- DÉBUT DE LA CORRECTION FINALE ---

                            annee_debut_graph = annee if mois > 1 else annee - 1
                            mois_debut_graph = mois - 1 if mois > 1 else 12
                            
                            _, nb_jours_mois_prec_graph = calendar.monthrange(annee_debut_graph, mois_debut_graph)
                            jour_debut_eff_graph = min(carte.jour_debut_periode, nb_jours_mois_prec_graph)
                            
                            _, nb_jours_mois_cours_graph = calendar.monthrange(annee, mois)
                            jour_fin_eff_graph = min(carte.jour_fin_periode, nb_jours_mois_cours_graph)

                            date_fin_releve = date(annee, mois, jour_fin_eff_graph)
                            date_debut_releve = date(annee_debut_graph, mois_debut_graph, jour_debut_eff_graph)
                            # --- FIN DE LA CORRECTION FINALE ---

                            montant_a_regler_graph = sum(t.get('montant', 0.0) for t in toutes_les_transactions if t.get('compte_affecte') == carte.nom and date_debut_releve <= self._parse_date_flexible(t['date']) <= date_fin_releve and t.get('pointe'))
                            solde_courant -= abs(montant_a_regler_graph)
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

if __name__ == "__main__":
    print("INFO: Lancement ...")
    root = tk.Tk()
    app = PatrimoineApp(root)
    print("INFO: Lancement mainloop...")
    root.mainloop()
    print("INFO: Fermé.")
