import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from datetime import date, datetime, timedelta
import calendar
import uuid
from collections import defaultdict

# Importer les dépendances depuis vos autres modules
from utils import format_nombre_fr
from models import Compte

class ConflictStrategyDialog(simpledialog.Dialog):
    def __init__(self, parent, title=None, potential_conflicts=0):
        self.strategy = None
        self.potential_conflicts = potential_conflicts
        super().__init__(parent, title)

    def body(self, master):
        if self.potential_conflicts > 0:
            ttk.Label(master, text=f"{self.potential_conflicts} conflit(s) potentiel(s) détecté(s).").pack(pady=5)
            ttk.Label(master, text="Comment procéder pour ces éléments ?").pack(pady=5)
        else:
            ttk.Label(master, text="Aucun conflit direct détecté.").pack(pady=5)
        
        self.strategy_var = tk.StringVar(value="ask_each")
        ttk.Radiobutton(master, text="Me demander pour chaque élément", variable=self.strategy_var, value="ask_each").pack(anchor=tk.W)
        if self.potential_conflicts > 0:
            ttk.Radiobutton(master, text="Tout mettre à jour", variable=self.strategy_var, value="update_all").pack(anchor=tk.W)
            ttk.Radiobutton(master, text="Tout ignorer (ne pas mettre à jour)", variable=self.strategy_var, value="skip_all").pack(anchor=tk.W)
        return None

    def buttonbox(self):
        box = ttk.Frame(self)
        ttk.Button(box, text="OK", width=10, command=self.ok, default=tk.ACTIVE).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(box, text="Annuler", width=10, command=self.cancel).pack(side=tk.LEFT, padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()

    def apply(self):
        self.result = self.strategy_var.get()

class TemplateManagerWindow(tk.Toplevel):
    def __init__(self, parent_app):
        super().__init__(parent_app.root)
        self.transient(parent_app.root)
        self.parent_app = parent_app
        self.title("Gestion des Modèles de Budget")
        self.geometry("750x400")
        self.resizable(False, False)
        self.templates_key = "_templates"
        if self.templates_key not in self.parent_app.budget_data:
            self.parent_app.budget_data[self.templates_key] = {}
        self.templates = self.parent_app.budget_data[self.templates_key]
        self.selected_template_name = tk.StringVar()
        self.create_widgets()
        self.populate_templates_list()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.grab_set()
        self.wait_window(self)

    def create_widgets(self):
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        left_frame = ttk.Frame(main_pane, padding=5)
        main_pane.add(left_frame, weight=1)
        ttk.Label(left_frame, text="Modèles de Budget", font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W)
        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.templates_listbox = tk.Listbox(list_frame, exportselection=False, selectmode=tk.EXTENDED)
        self.templates_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.templates_listbox.yview)
        self.templates_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.templates_listbox.bind("<<ListboxSelect>>", self.on_template_select)
        template_buttons = ttk.Frame(left_frame)
        template_buttons.pack(fill=tk.X, pady=5)
        ttk.Button(template_buttons, text="Nouveau", command=self.new_template).pack(side=tk.LEFT)
        ttk.Button(template_buttons, text="Renommer", command=self.rename_template).pack(side=tk.LEFT, padx=5)
        ttk.Button(template_buttons, text="Supprimer", command=self.delete_template).pack(side=tk.LEFT)
        right_frame = ttk.Frame(main_pane, padding=5)
        main_pane.add(right_frame, weight=3)
        self.label_categories = ttk.Label(right_frame, text="Catégories du Modèle : (aucun sélectionné)", font=('TkDefaultFont', 10, 'bold'))
        self.label_categories.pack(anchor=tk.W)
        cols = ('categorie', 'type', 'prevu', 'compte_prevu')
        self.categories_tree = ttk.Treeview(right_frame, columns=cols, show='headings', selectmode=tk.EXTENDED)
        self.categories_tree.heading('categorie', text='Catégorie')
        self.categories_tree.heading('type', text='Type')
        self.categories_tree.heading('prevu', text='Montant (€)')
        self.categories_tree.heading('compte_prevu', text='Compte par Défaut')
        self.categories_tree.column('categorie', width=150)
        self.categories_tree.column('type', width=80)
        self.categories_tree.column('prevu', width=100, anchor=tk.E)
        self.categories_tree.column('compte_prevu', width=120)
        self.categories_tree.pack(fill=tk.BOTH, expand=True, pady=5)
        self.categories_tree.bind("<Double-1>", self.edit_category)
        category_buttons = ttk.Frame(right_frame)
        category_buttons.pack(fill=tk.X, pady=5)
        self.add_cat_button = ttk.Button(category_buttons, text="Ajouter", command=self.add_category, state=tk.DISABLED)
        self.add_cat_button.pack(side=tk.LEFT)
        self.edit_cat_button = ttk.Button(category_buttons, text="Modifier", command=self.edit_category, state=tk.DISABLED)
        self.edit_cat_button.pack(side=tk.LEFT, padx=5)
        self.del_cat_button = ttk.Button(category_buttons, text="Supprimer", command=self.delete_category, state=tk.DISABLED)
        self.del_cat_button.pack(side=tk.LEFT)

    def populate_templates_list(self):
        self.templates_listbox.delete(0, tk.END)
        for name in sorted(self.templates.keys()):
            self.templates_listbox.insert(tk.END, name)

    def on_template_select(self, event=None):
        selection_indices = self.templates_listbox.curselection()
        if not selection_indices:
            self.selected_template_name.set("")
            self.update_category_view()
            return
        selected_name = self.templates_listbox.get(selection_indices[0])
        self.selected_template_name.set(selected_name)
        self.update_category_view()

    def update_category_view(self):
        for item in self.categories_tree.get_children():
            self.categories_tree.delete(item)
        name = self.selected_template_name.get()
        if name and name in self.templates:
            self.label_categories.config(text=f"Catégories du Modèle : '{name}'")
            self.add_cat_button.config(state=tk.NORMAL)
            self.edit_cat_button.config(state=tk.NORMAL)
            self.del_cat_button.config(state=tk.NORMAL)
            categories = self.templates[name]
            categories.sort(key=lambda x: x.get('categorie', '').lower())
            for cat in categories:
                self.categories_tree.insert('', 'end', values=(cat['categorie'], cat.get('type', 'Dépense'), format_nombre_fr(cat['prevu']), cat.get('compte_prevu', '')))
        else:
            self.label_categories.config(text="Catégories du Modèle : (aucun sélectionné)")
            self.add_cat_button.config(state=tk.DISABLED)
            self.edit_cat_button.config(state=tk.DISABLED)
            self.del_cat_button.config(state=tk.DISABLED)

    def new_template(self):
        name = simpledialog.askstring("Nouveau Modèle", "Nom du nouveau modèle :", parent=self)
        if name and name.strip():
            name = name.strip()
            if name in self.templates:
                messagebox.showwarning("Erreur", "Un modèle avec ce nom existe déjà.", parent=self)
                return
            self.templates[name] = []
            self.populate_templates_list()
            self.templates_listbox.selection_set(sorted(self.templates.keys()).index(name))
            self.on_template_select()

    def rename_template(self):
        selection_indices = self.templates_listbox.curselection()
        if not selection_indices:
            return
        old_name = self.templates_listbox.get(selection_indices[0])
        new_name = simpledialog.askstring("Renommer Modèle", f"Nouveau nom pour '{old_name}' :", parent=self)
        if new_name and new_name.strip() and new_name != old_name:
            new_name = new_name.strip()
            if new_name in self.templates:
                messagebox.showwarning("Erreur", "Un modèle avec ce nom existe déjà.", parent=self)
                return
            self.templates[new_name] = self.templates.pop(old_name)
            self.populate_templates_list()
            self.templates_listbox.selection_set(sorted(self.templates.keys()).index(new_name))
            self.on_template_select()

    def delete_template(self):
        selection_indices = self.templates_listbox.curselection()
        if not selection_indices:
            return
        noms_a_suppr = [self.templates_listbox.get(i) for i in selection_indices]
        if messagebox.askyesno("Confirmer", f"Êtes-vous sûr de vouloir supprimer {len(noms_a_suppr)} modèle(s) ?", parent=self):
            for name in noms_a_suppr:
                if name in self.templates:
                    del self.templates[name]
            self.populate_templates_list()
            self.on_template_select()

    def add_category(self):
        name = self.selected_template_name.get()
        if not name:
            return
        result = self.parent_app._ouvrir_fenetre_gestion_categorie()
        if result:
            categories = self.templates[name]
            if any(cat['categorie'].lower() == result['categorie'].lower() for cat in categories):
                messagebox.showwarning("Catégorie Existante", "Cette catégorie existe déjà.", parent=self)
                return
            categories.append(result)
            self.update_category_view()

    def edit_category(self, event=None):
        name = self.selected_template_name.get()
        selection = self.categories_tree.selection()
        if not name or not selection:
            return
        nom_categorie_actuel = self.categories_tree.item(selection[0])['values'][0]
        categories = self.templates[name]
        cat_a_modifier = next((cat for cat in categories if cat['categorie'] == nom_categorie_actuel), None)
        if cat_a_modifier:
            result = self.parent_app._ouvrir_fenetre_gestion_categorie(cat_a_modifier)
            if result:
                nom_deja_pris = any(cat['categorie'].lower() == result['categorie'].lower() and cat['categorie'] != nom_categorie_actuel for cat in categories)
                if nom_deja_pris:
                    messagebox.showwarning("Nom Existant", "Une catégorie avec ce nom existe déjà.", parent=self)
                    return
                cat_a_modifier.update(result)
                self.update_category_view()

    def delete_category(self):
        name = self.selected_template_name.get()
        selection = self.categories_tree.selection()
        if not name or not selection:
            return
        noms_a_suppr = [self.categories_tree.item(item_id)['values'][0] for item_id in selection]
        if messagebox.askyesno("Confirmer", f"Supprimer {len(noms_a_suppr)} catégorie(s) de ce modèle ?", parent=self):
            self.templates[name][:] = [cat for cat in self.templates[name] if cat['categorie'] not in noms_a_suppr]
            self.update_category_view()

    def on_close(self):
        self.parent_app.sauvegarder_budget_donnees()
        self.destroy()

class ApplyTemplateDialog(simpledialog.Dialog):
    def __init__(self, parent, templates):
        self.templates = templates
        self.result = None
        super().__init__(parent, "Appliquer un Modèle de Budget")

    def body(self, master):
        ttk.Label(master, text="Veuillez choisir un modèle à appliquer :").pack(pady=5)
        self.template_var = tk.StringVar()
        template_names = [name for name, cats in self.templates.items() if cats]
        if not template_names:
            ttk.Label(master, text="Aucun modèle avec des catégories n'a été trouvé.").pack()
            return None
        self.template_combo = ttk.Combobox(master, textvariable=self.template_var, values=sorted(template_names), state="readonly")
        self.template_combo.pack(padx=10, pady=5)
        if template_names:
            self.template_combo.current(0)
        return self.template_combo

    def apply(self):
        self.result = self.template_var.get()

class VirementDialog(simpledialog.Dialog):
    def __init__(self, parent, all_accounts):
        self.all_accounts_names = sorted([c.nom for c in all_accounts])
        self.result = None
        super().__init__(parent, "Effectuer un Virement Interne")

    def body(self, master):
        ttk.Label(master, text="Date (AAAA-MM-JJ):").grid(row=0, column=0, sticky=tk.W, pady=3)
        self.date_entry = ttk.Entry(master, width=25)
        self.date_entry.grid(row=0, column=1, sticky=tk.EW, pady=3)
        self.date_entry.insert(0, date.today().strftime("%Y-%m-%d"))
        ttk.Label(master, text="Description:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.desc_entry = ttk.Entry(master)
        self.desc_entry.grid(row=1, column=1, sticky=tk.EW, pady=3)
        self.desc_entry.insert(0, "Virement interne")
        ttk.Label(master, text="Montant (€):").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.montant_entry = ttk.Entry(master)
        self.montant_entry.grid(row=2, column=1, sticky=tk.EW, pady=3)
        ttk.Label(master, text="Depuis le compte:").grid(row=3, column=0, sticky=tk.W, pady=3)
        self.source_var = tk.StringVar()
        self.source_combo = ttk.Combobox(master, textvariable=self.source_var, values=self.all_accounts_names, state="readonly")
        self.source_combo.grid(row=3, column=1, sticky=tk.EW, pady=3)
        ttk.Label(master, text="Vers le compte:").grid(row=4, column=0, sticky=tk.W, pady=3)
        self.dest_var = tk.StringVar()
        self.dest_combo = ttk.Combobox(master, textvariable=self.dest_var, values=self.all_accounts_names, state="readonly")
        self.dest_combo.grid(row=4, column=1, sticky=tk.EW, pady=3)
        master.columnconfigure(1, weight=1)
        return self.date_entry

    def validate(self):
        source = self.source_var.get()
        destination = self.dest_var.get()
        if not source or not destination:
            messagebox.showwarning("Erreur de saisie", "Veuillez sélectionner un compte source et un compte de destination.", parent=self)
            return 0
        if source == destination:
            messagebox.showwarning("Erreur de saisie", "Le compte source et le compte de destination ne peuvent pas être identiques.", parent=self)
            return 0
        try:
            montant = float(self.montant_entry.get().strip().replace(' ', '').replace(',', '.'))
            if montant <= 0:
                messagebox.showwarning("Erreur de saisie", "Le montant doit être un nombre positif.", parent=self)
                return 0
        except ValueError:
            messagebox.showwarning("Erreur de saisie", "Le montant est invalide.", parent=self)
            return 0
        return 1

    def apply(self):
        try:
            self.result = {
                "date": datetime.strptime(self.date_entry.get(), "%Y-%m-%d").strftime("%Y-%m-%d"),
                "description": self.desc_entry.get().strip(),
                "montant": float(self.montant_entry.get().strip().replace(' ', '').replace(',', '.')),
                "source": self.source_var.get(),
                "destination": self.dest_var.get()
            }
        except (ValueError, TypeError):
            self.result = None

class RecurrentTransactionManager(tk.Toplevel):
    """Fenêtre pour gérer les transactions récurrentes."""
    def __init__(self, parent_app):
        super().__init__(parent_app.root)
        self.transient(parent_app.root)
        self.parent_app = parent_app
        self.title("Gestion des Transactions Récurrentes")
        self.geometry("800x400")

        if 'transactions_recurrentes' not in self.parent_app.budget_data:
            self.parent_app.budget_data['transactions_recurrentes'] = []
        self.trans_recurrentes = self.parent_app.budget_data['transactions_recurrentes']

        self.create_widgets()
        self.populate_list()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.grab_set()
        self.wait_window(self)

    def create_widgets(self):
        top_frame = ttk.Frame(self, padding=10)
        top_frame.pack(fill=tk.X)
        ttk.Label(top_frame, text="Configurez ici vos dépenses et revenus qui reviennent chaque mois.").pack(anchor=tk.W)

        tree_frame = ttk.Frame(self, padding=(10, 0, 10, 10))
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ('actif', 'jour', 'desc', 'cat', 'montant', 'compte')
        self.tree = ttk.Treeview(tree_frame, columns=cols, show='headings', selectmode=tk.EXTENDED)
        self.tree.heading('actif', text='Actif')
        self.tree.column('actif', width=40, anchor=tk.CENTER)
        self.tree.heading('jour', text='Jour')
        self.tree.column('jour', width=40, anchor=tk.CENTER)
        self.tree.heading('desc', text='Description')
        self.tree.column('desc', width=200)
        self.tree.heading('cat', text='Catégorie')
        self.tree.column('cat', width=120)
        self.tree.heading('montant', text='Montant (€)')
        self.tree.column('montant', width=100, anchor=tk.E)
        self.tree.heading('compte', text='Compte')
        self.tree.column('compte', width=120)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self.edit_transaction)

        buttons_frame = ttk.Frame(self, padding=10)
        buttons_frame.pack(fill=tk.X)
        ttk.Button(buttons_frame, text="Ajouter", command=self.add_transaction).pack(side=tk.LEFT)
        ttk.Button(buttons_frame, text="Modifier", command=self.edit_transaction).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Supprimer", command=self.delete_transaction).pack(side=tk.LEFT)
        ttk.Button(buttons_frame, text="Fermer", command=self.on_close).pack(side=tk.RIGHT)

    def populate_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.trans_recurrentes.sort(key=lambda x: x.get('jour_du_mois', 0))
        for trans in self.trans_recurrentes:
            actif_str = "✔️" if trans.get('active', True) else "❌"
            montant = trans.get('montant', 0.0)
            
            compte_str = trans.get('compte_affecte', '')
            if trans.get('type') == 'Virement':
                montant_str = f"{format_nombre_fr(montant)}"
                compte_str = f"{trans.get('source')} -> {trans.get('destination')}"
            else:
                montant_str = f"+{format_nombre_fr(montant)}" if montant > 0 else format_nombre_fr(montant)

            self.tree.insert('', 'end', iid=trans['id'], values=(
                actif_str, trans['jour_du_mois'], trans['description'],
                trans['categorie'], f"{montant_str} €", compte_str
            ))

    def add_transaction(self):
        result = self._dialog_edit_recurrent_transaction()
        if result:
            result['id'] = uuid.uuid4().hex
            self.trans_recurrentes.append(result)
            self.populate_list()

    def edit_transaction(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        trans_id = selection[0]
        trans_existante = next((t for t in self.trans_recurrentes if t['id'] == trans_id), None)
        if trans_existante:
            result = self._dialog_edit_recurrent_transaction(trans_existante)
            if result:
                trans_existante.update(result)
                self.populate_list()

    def delete_transaction(self):
        selection = self.tree.selection()
        if not selection:
            return
        
        ids_a_suppr = set(selection)
        if messagebox.askyesno("Confirmer", f"Supprimer {len(ids_a_suppr)} transaction(s) récurrente(s) ?", parent=self):
            self.trans_recurrentes[:] = [t for t in self.trans_recurrentes if t['id'] not in ids_a_suppr]
            self.populate_list()

    def on_close(self):
        self.parent_app.sauvegarder_budget_donnees()
        self.destroy()

    def _dialog_edit_recurrent_transaction(self, trans_existante=None):
        dialog = tk.Toplevel(self)
        dialog.transient(self)
        titre = "Modifier Transaction Récurrente" if trans_existante else "Ajouter Transaction Récurrente"
        dialog.title(titre)
        dialog.geometry("500x420")
        dialog.resizable(False, False)
        dialog.grab_set()

        form_frame = ttk.Frame(dialog, padding="15")
        form_frame.pack(fill=tk.BOTH, expand=True)
        resultat = {}

        comptes_pour_budget = sorted([c.nom for c in self.parent_app.comptes if c.suivi_budget])
        tous_les_comptes = sorted([c.nom for c in self.parent_app.comptes])
        categories_budget = self.parent_app.get_all_budget_categories()
        
        type_var = tk.StringVar()
        periodicite_var = tk.StringVar()
        jour_echeance_var = tk.StringVar()

        row = 0
        ttk.Label(form_frame, text="Type:").grid(row=row, column=0, sticky=tk.W, pady=3)
        type_combo = ttk.Combobox(form_frame, textvariable=type_var, values=["Dépense", "Revenu", "Virement"], state="readonly")
        type_combo.grid(row=row, column=1, columnspan=2, sticky=tk.EW)
        row += 1
        
        ttk.Label(form_frame, text="Description:").grid(row=row, column=0, sticky=tk.W, pady=3)
        desc_entry = ttk.Entry(form_frame)
        desc_entry.grid(row=row, column=1, columnspan=2, sticky=tk.EW)
        row += 1

        ttk.Label(form_frame, text="Montant (€):").grid(row=row, column=0, sticky=tk.W, pady=3)
        montant_entry = ttk.Entry(form_frame)
        montant_entry.grid(row=row, column=1, columnspan=2, sticky=tk.EW)
        row += 1

        ttk.Label(form_frame, text="Date de début (AAAA-MM-JJ):").grid(row=row, column=0, sticky=tk.W, pady=3)
        date_debut_entry = ttk.Entry(form_frame)
        date_debut_entry.grid(row=row, column=1, columnspan=2, sticky=tk.EW)
        row += 1
        
        ttk.Label(form_frame, text="Date de fin (optionnel):").grid(row=row, column=0, sticky=tk.W, pady=3)
        date_fin_entry = ttk.Entry(form_frame)
        date_fin_entry.grid(row=row, column=1, columnspan=2, sticky=tk.EW)
        row += 1

        ttk.Label(form_frame, text="Périodicité:").grid(row=row, column=0, sticky=tk.W, pady=3)
        periodicite_combo = ttk.Combobox(form_frame, textvariable=periodicite_var, 
                                         values=["Mensuelle", "Bi-mensuelle", "Trimestrielle", "Tous les 4 mois", "Semestrielle", "Annuelle", "Hebdomadaire"], 
                                         state="readonly")
        periodicite_combo.grid(row=row, column=1, columnspan=2, sticky=tk.EW)
        row += 1

        jour_label = ttk.Label(form_frame, text="Jour de l'échéance:")
        jour_label.grid(row=row, column=0, sticky=tk.W, pady=3)
        jour_echeance_entry = ttk.Entry(form_frame, textvariable=jour_echeance_var)
        jour_echeance_entry.grid(row=row, column=1, sticky=tk.W)
        row += 1
        
        dynamic_row_start = row
        cat_label = ttk.Label(form_frame, text="Catégorie:")
        cat_var = tk.StringVar()
        cat_combo = ttk.Combobox(form_frame, textvariable=cat_var, values=categories_budget, state="readonly")
        compte_label = ttk.Label(form_frame, text="Compte:")
        compte_var = tk.StringVar()
        compte_combo = ttk.Combobox(form_frame, textvariable=compte_var, values=comptes_pour_budget, state="readonly")
        source_label = ttk.Label(form_frame, text="Compte Source:")
        source_var = tk.StringVar()
        source_combo = ttk.Combobox(form_frame, textvariable=source_var, values=tous_les_comptes, state="readonly")
        dest_label = ttk.Label(form_frame, text="Compte Destination:")
        dest_var = tk.StringVar()
        dest_combo = ttk.Combobox(form_frame, textvariable=dest_var, values=tous_les_comptes, state="readonly")
        
        actif_var = tk.BooleanVar(value=True)
        actif_check = ttk.Checkbutton(form_frame, text="Activée", variable=actif_var)
        button_frame = ttk.Frame(form_frame)

        def on_validate():
            try:
                type_final = type_var.get()
                if not type_final:
                    messagebox.showerror("Erreur de Saisie", "Veuillez sélectionner un type.", parent=dialog)
                    return

                desc_val = desc_entry.get().strip()
                if not desc_val:
                    messagebox.showerror("Erreur de Saisie", "Veuillez saisir une description.", parent=dialog)
                    return

                montant_val = abs(float(montant_entry.get().strip().replace(' ', '').replace(',', '.')))
                if montant_val <= 0:
                    messagebox.showerror("Erreur de Saisie", "Le montant doit être supérieur à zéro.", parent=dialog)
                    return

                date_debut_val = datetime.strptime(date_debut_entry.get().strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
                date_fin_val_str = date_fin_entry.get().strip()
                date_fin_val = datetime.strptime(date_fin_val_str, "%Y-%m-%d").strftime("%Y-%m-%d") if date_fin_val_str else None

                periodicite_val = periodicite_var.get()
                jour_val_str = jour_echeance_var.get().strip()
                if not jour_val_str:
                    messagebox.showerror("Erreur de Saisie", "Le champ 'Jour de l'échéance' est obligatoire.", parent=dialog)
                    return

                if periodicite_val == "Bi-mensuelle":
                    jours_parts = [j.strip() for j in jour_val_str.split(',')]
                    if len(jours_parts) != 2 or not all(j.isdigit() for j in jours_parts) or not all(1 <= int(j) <= 31 for j in jours_parts):
                        messagebox.showerror("Erreur de Saisie", "Pour bi-mensuel, entrez deux jours (1-31) séparés par une virgule.", parent=dialog)
                        return
                elif periodicite_val == "Hebdomadaire":
                    if not jour_val_str.isdigit() or not (1 <= int(jour_val_str) <= 7):
                        messagebox.showerror("Erreur de Saisie", "Pour hebdomadaire, entrez un jour de 1 (Lundi) à 7 (Dimanche).", parent=dialog)
                        return
                else:
                    if not jour_val_str.isdigit() or not (1 <= int(jour_val_str) <= 31):
                        messagebox.showerror("Erreur de Saisie", "Le jour du mois doit être entre 1 et 31.", parent=dialog)
                        return

                resultat['ok'] = True
                resultat['valeurs'] = {
                    "type": type_final, "description": desc_val, "active": actif_var.get(),
                    "date_debut": date_debut_val, "date_fin": date_fin_val,
                    "periodicite": periodicite_val, "jour_echeance": jour_val_str,
                    "jour_du_mois": int(jour_val_str.split(',')[0])
                }
                
                if type_final == 'Virement':
                    source = source_var.get()
                    destination = dest_var.get()
                    if not source or not destination or source == destination:
                        messagebox.showerror("Erreur de Saisie", "Pour un virement, sélectionnez deux comptes différents.", parent=dialog)
                        return
                    resultat['valeurs'].update({"montant": montant_val, "source": source, "destination": destination, "categorie": "(Virement)", "compte_affecte": None})
                else:
                    compte = compte_var.get()
                    categorie = cat_var.get()
                    if not compte or not categorie:
                        messagebox.showerror("Erreur de Saisie", "Veuillez sélectionner un compte et une catégorie.", parent=dialog)
                        return
                    montant_final = -montant_val if type_final == "Dépense" else montant_val
                    resultat['valeurs'].update({"montant": montant_final, "categorie": categorie, "compte_affecte": compte})
                
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Erreur de Format", f"Valeur incorrecte. Vérifiez les formats.\n(Détail: {e})", parent=dialog)
            except Exception as e:
                messagebox.showerror("Erreur Inattendue", f"Une erreur est survenue : {e}", parent=dialog)
        
        ttk.Button(button_frame, text="Valider", command=on_validate).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Annuler", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

        def update_ui_fields(event=None):
            current_row = dynamic_row_start
            for w in [cat_label, cat_combo, compte_label, compte_combo, source_label, source_combo, dest_label, dest_combo]:
                w.grid_remove()
            if type_var.get() == "Virement":
                source_label.grid(row=current_row, column=0, sticky=tk.W, pady=3)
                source_combo.grid(row=current_row, column=1, columnspan=2, sticky=tk.EW)
                current_row += 1
                dest_label.grid(row=current_row, column=0, sticky=tk.W, pady=3)
                dest_combo.grid(row=current_row, column=1, columnspan=2, sticky=tk.EW)
                current_row += 1
                cat_combo.set("(Virement)")
            else:
                cat_label.grid(row=current_row, column=0, sticky=tk.W, pady=3)
                cat_combo.grid(row=current_row, column=1, columnspan=2, sticky=tk.EW)
                current_row += 1
                compte_label.grid(row=current_row, column=0, sticky=tk.W, pady=3)
                compte_combo.grid(row=current_row, column=1, columnspan=2, sticky=tk.EW)
                current_row += 1

            p = periodicite_var.get()
            if p == "Hebdomadaire":
                jour_label.config(text="Jour (1=Lun, 7=Dim):")
            elif p == "Bi-mensuelle":
                jour_label.config(text="Jours (ex: 1,15):")
            else:
                jour_label.config(text="Jour du mois (1-31):")
            
            actif_check.grid(row=current_row, column=1, sticky=tk.W, pady=5)
            current_row += 1
            button_frame.grid(row=current_row, column=0, columnspan=3, pady=10, sticky=tk.E)

        type_combo.bind("<<ComboboxSelected>>", update_ui_fields)
        periodicite_combo.bind("<<ComboboxSelected>>", update_ui_fields)
        
        if trans_existante:
            type_var.set(trans_existante.get('type', 'Dépense'))
            desc_entry.insert(0, trans_existante.get('description') or '')
            montant = trans_existante.get('montant', 0.0)
            montant_entry.insert(0, str(abs(montant)).replace('.', ','))
            date_debut_val = trans_existante.get('date_debut') or date.today().strftime("%Y-%m-%d")
            date_debut_entry.insert(0, date_debut_val)
            date_fin_entry.insert(0, trans_existante.get('date_fin') or '')
            periodicite_var.set(trans_existante.get('periodicite', 'Mensuelle'))
            jour_echeance_var.set(str(trans_existante.get('jour_echeance', '1')))
            actif_var.set(trans_existante.get('active', True))
            if type_var.get() == "Virement":
                source_var.set(trans_existante.get('source', '') or '')
                dest_var.set(trans_existante.get('destination', '') or '')
            else:
                cat_var.set(trans_existante.get('categorie', '') or '')
                compte_var.set(trans_existante.get('compte_affecte', '') or '')
        else: 
            type_var.set("Dépense")
            periodicite_var.set("Mensuelle")
            date_debut_entry.insert(0, date.today().strftime("%Y-%m-%d"))
        
        update_ui_fields()
        self.parent_app.root.wait_window(dialog)
        return resultat.get('valeurs')

class DetailPrevisionnelWindow(tk.Toplevel):
    def __init__(self, parent, data_comptes, lignes_futures, total_actifs, total_passifs, total_net):
        super().__init__(parent)
        self.transient(parent)
        self.title("Détail du Solde Prévisionnel")
        self.geometry("950x500")
        self.resizable(True, True)

        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        compte_frame = ttk.LabelFrame(main_frame, text="Décomposition par Compte", padding=5)
        compte_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        cols_comptes = ('compte', 'solde_p', 'activite_mois', 'solde_v', 'impact_budget', 'solde_prev')
        tree_comptes = ttk.Treeview(compte_frame, columns=cols_comptes, show='headings')
        
        tree_comptes.heading('compte', text='Compte')
        tree_comptes.heading('solde_p', text='Solde Pointé (€)')
        tree_comptes.heading('activite_mois', text='Activité (€)')
        tree_comptes.heading('solde_v', text='Solde Virtuel (€)')
        tree_comptes.heading('impact_budget', text='Impact Budget (€)')
        tree_comptes.heading('solde_prev', text='Solde Prévisionnel (€)')

        for col in cols_comptes:
            tree_comptes.column(col, anchor=tk.E, width=140)
        tree_comptes.column('compte', anchor=tk.W, width=180)

        tree_comptes.pack(fill=tk.BOTH, expand=True)

        for nom_compte, data in sorted(data_comptes.items()):
            tree_comptes.insert('', tk.END, values=(
                nom_compte,
                format_nombre_fr(data.get('solde_pointe')),
                format_nombre_fr(data.get('activite_mois')),
                format_nombre_fr(data.get('solde_virtuel')),
                format_nombre_fr(data.get('impact_budget')),
                format_nombre_fr(data.get('solde_previsionnel'))
            ))

        if lignes_futures:
            impact_frame = ttk.LabelFrame(main_frame, text="Opérations Futures Simulées", padding=5)
            impact_frame.pack(fill=tk.X, pady=5, anchor=tk.W)
            for ligne in sorted(lignes_futures):
                ttk.Label(impact_frame, text=ligne).pack(anchor=tk.W)

        total_frame = ttk.LabelFrame(main_frame, text="Synthèse Prévisionnelle", padding=10)
        total_frame.pack(fill=tk.X, pady=5)

        style = ttk.Style(self)
        style.configure("Total.TLabel", font=('TkDefaultFont', 10))
        style.configure("Total.Bold.TLabel", font=('TkDefaultFont', 11, 'bold'))

        actif_frame = ttk.Frame(total_frame)
        actif_frame.pack(fill=tk.X)
        ttk.Label(actif_frame, text="Total Actifs Prévisionnels :", style="Total.TLabel").pack(side=tk.LEFT)
        ttk.Label(actif_frame, text=f"{format_nombre_fr(total_actifs)} €", style="Total.TLabel", foreground="green").pack(side=tk.RIGHT)
        
        passif_frame = ttk.Frame(total_frame)
        passif_frame.pack(fill=tk.X)
        ttk.Label(passif_frame, text="Total Passifs Prévisionnels :", style="Total.TLabel").pack(side=tk.LEFT)
        ttk.Label(passif_frame, text=f"{format_nombre_fr(total_passifs)} €", style="Total.TLabel", foreground="red").pack(side=tk.RIGHT)
        
        net_frame = ttk.Frame(total_frame)
        net_frame.pack(fill=tk.X, pady=(5,0))
        ttk.Separator(net_frame).pack(fill=tk.X, expand=True, pady=5)
        ttk.Label(net_frame, text="PATRIMOINE NET PRÉVISIONNEL :", style="Total.Bold.TLabel").pack(side=tk.LEFT)
        ttk.Label(net_frame, text=f"{format_nombre_fr(total_net)} €", style="Total.Bold.TLabel").pack(side=tk.RIGHT)

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()
        self.wait_window(self)
        
class SelectFromListDialog(simpledialog.Dialog):
    def __init__(self, parent, title, prompt, item_list):
        self.prompt = prompt
        self.item_list = item_list
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text=self.prompt, wraplength=300).pack(pady=5)
        self.var = tk.StringVar()
        if self.item_list:
            self.var.set(self.item_list[0])
        self.combobox = ttk.Combobox(master, textvariable=self.var, values=self.item_list, state="readonly", width=40)
        self.combobox.pack(padx=10, pady=5)
        return self.combobox

    def apply(self):
        self.result = self.var.get()
        
class RapportMensuelWindow(tk.Toplevel):

    def __init__(self, parent, cle_mois_annee, transactions_du_mois):
        super().__init__(parent)
        self.transient(parent)
        self.title(f"Rapport Mensuel pour {cle_mois_annee}")
        self.geometry("850x650")

        # On utilise directement la liste de transactions déjà filtrée par app.py
        transactions = transactions_du_mois
        
        total_recettes = sum(t['montant'] for t in transactions if t['montant'] > 0 and t['categorie'] != "(Virement)")
        total_depenses = sum(t['montant'] for t in transactions if t['montant'] < 0 and t['categorie'] != "(Virement)")
        
        solde_mois = total_recettes + total_depenses
        
        recettes_par_cat = defaultdict(float)
        depenses_par_cat = defaultdict(float)
        for t in transactions:
            if t['montant'] > 0 and t['categorie'] != "(Virement)":
                recettes_par_cat[t['categorie']] += t['montant']
            elif t['montant'] < 0 and t['categorie'] != "(Virement)":
                depenses_par_cat[t['categorie']] += abs(t['montant'])
        
        taux_epargne_str = "N/A"
        if total_recettes > 0:
            taux_epargne = (solde_mois / total_recettes) * 100
            taux_epargne_str = f"{taux_epargne:.2f} %"

        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        summary_frame = ttk.LabelFrame(main_frame, text="Synthèse du Mois", padding=10)
        summary_frame.pack(fill=tk.X, pady=5)
        ttk.Label(summary_frame, text=f"Total Recettes : +{format_nombre_fr(total_recettes)} €").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(summary_frame, text=f"Total Dépenses : {format_nombre_fr(total_depenses)} €").grid(row=1, column=0, sticky=tk.W)
        ttk.Label(summary_frame, text=f"Cash-Flow (Solde) : {format_nombre_fr(solde_mois)} €", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=1, padx=20)
        ttk.Label(summary_frame, text=f"Taux d'Épargne : {taux_epargne_str}", font=('TkDefaultFont', 10, 'bold')).grid(row=1, column=1, padx=20)

        details_pane = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        details_pane.pack(fill=tk.BOTH, expand=True, pady=10)

        depenses_frame = ttk.Frame(details_pane)
        details_pane.add(depenses_frame, weight=1)
        ttk.Label(depenses_frame, text="Détail des Dépenses").pack(anchor=tk.W)
        tree_dep = ttk.Treeview(depenses_frame, columns=('cat', 'montant'), show='headings')
        tree_dep.heading('cat', text="Catégorie")
        tree_dep.heading('montant', text="Montant (€)")
        tree_dep.column('montant', anchor=tk.E)
        tree_dep.pack(fill=tk.BOTH, expand=True)
        for cat, montant in sorted(depenses_par_cat.items(), key=lambda item: item[1], reverse=True):
            tree_dep.insert('', 'end', values=(cat, format_nombre_fr(montant)))

        recettes_frame = ttk.Frame(details_pane)
        details_pane.add(recettes_frame, weight=1)
        ttk.Label(recettes_frame, text="Détail des Recettes").pack(anchor=tk.W)
        tree_rec = ttk.Treeview(recettes_frame, columns=('cat', 'montant'), show='headings')
        tree_rec.heading('cat', text="Catégorie")
        tree_rec.heading('montant', text="Montant (€)")
        tree_rec.column('montant', anchor=tk.E)
        tree_rec.pack(fill=tk.BOTH, expand=True)
        for cat, montant in sorted(recettes_par_cat.items(), key=lambda item: item[1], reverse=True):
            tree_rec.insert('', 'end', values=(cat, format_nombre_fr(montant)))
            
        self.protocol("WM_DELETE_WINDOW", self.destroy) 
        self.grab_set()
        self.wait_window(self)

class DailyBudgetCalendarDialog(tk.Toplevel):
    def __init__(self, parent, title, year, month, details=None):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.geometry("680x580")
        self.resizable(False, False)

        self.year = year
        self.month = month
        self.result = None
        self.calculated_total = 0.0

        main_container = ttk.Frame(self, padding=10)
        main_container.pack(fill=tk.BOTH, expand=True)
        button_frame = ttk.Frame(main_container)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        total_frame = ttk.Frame(main_container)
        total_frame.pack(side=tk.BOTTOM, fill=tk.X)
        calendar_frame = ttk.Frame(main_container)
        calendar_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._create_calendar(calendar_frame)
        self._create_total_display(total_frame)
        self._create_buttons(button_frame)

        if details:
            for detail in details:
                jour = detail.get('jour')
                if jour in self.daily_vars:
                    self.daily_vars[jour].set(format_nombre_fr(detail.get('montant')))
                    self.neutralise_vars[jour].set(detail.get('neutralise', False))

        self._update_total()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.grab_set()
        self.wait_window(self)
        
    def _create_calendar(self, master):
        days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
        for i, day in enumerate(days):
            ttk.Label(master, text=day, font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=i, sticky=tk.NSEW, pady=(0, 5))

        self.daily_vars = {}
        self.neutralise_vars = {}
        cal = calendar.monthcalendar(self.year, self.month)

        for row_idx, week in enumerate(cal, start=1):
            for col_idx, day_num in enumerate(week):
                day_frame = ttk.Frame(master, borderwidth=1, relief="solid")
                day_frame.grid(row=row_idx, column=col_idx, sticky=tk.NSEW, ipadx=2, ipady=2)
                if day_num != 0:
                    ttk.Label(day_frame, text=str(day_num)).pack(anchor=tk.NW, padx=2)
                    
                    neutralise_var = tk.BooleanVar(value=False)
                    check = ttk.Checkbutton(day_frame, variable=neutralise_var)
                    check.pack(side=tk.LEFT, padx=(0,2))
                    self.neutralise_vars[day_num] = neutralise_var

                    var = tk.StringVar()
                    entry = ttk.Entry(day_frame, textvariable=var, width=6, justify=tk.RIGHT)
                    entry.pack(expand=True, fill=tk.X, padx=2, pady=(0, 2))
                    var.trace_add("write", self._update_total)
                    self.daily_vars[day_num] = var

        for i in range(7): master.columnconfigure(i, weight=1)
        for i in range(len(cal) + 2): master.rowconfigure(i, weight=1)

    def _create_total_display(self, master):
        ttk.Label(master, text="Total Prévisionnel :", font=('TkDefaultFont', 10, 'bold')).pack(side=tk.LEFT)
        self.total_label = ttk.Label(master, text="0,00 €", font=('TkDefaultFont', 10, 'bold'))
        self.total_label.pack(side=tk.LEFT, padx=5)

    def _create_buttons(self, master):
        ttk.Button(master, text="Annuler", command=self._on_cancel).pack(side=tk.RIGHT)
        ttk.Button(master, text="Valider", command=self._on_ok, default=tk.ACTIVE).pack(side=tk.RIGHT, padx=5)

    def _update_total(self, *args):
        total = 0.0
        for var in self.daily_vars.values():
            try:
                val_str = var.get().strip().replace(',', '.')
                if val_str: total += float(val_str)
            except (ValueError, TypeError): pass
        
        if self.total_label.winfo_exists():
            self.total_label.config(text=f"{format_nombre_fr(total)} €")
        self.calculated_total = total

    def _on_ok(self, event=None):
        final_details = []
        for jour, var in self.daily_vars.items():
            try:
                val_str = var.get().strip().replace(',', '.')
                if val_str:
                    montant = float(val_str)
                    if montant != 0:
                        final_details.append({
                            'jour': jour, 
                            'montant': montant,
                            'neutralise': self.neutralise_vars[jour].get()
                        })
            except (ValueError, TypeError):
                pass

        self.result = {
            'total': self.calculated_total,
            'details': final_details
        }
        self.destroy()

    def _on_cancel(self, event=None):
        self.result = None
        self.destroy()
        
class HoldingEditDialog(simpledialog.Dialog):
    """Boîte de dialogue pour saisir les détails d'une ligne de portefeuille."""
    def __init__(self, parent, title, holding=None):
        self.holding = holding
        super().__init__(parent, title)

    def body(self, master):
        ttk.Label(master, text="Nom:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.nom_entry = ttk.Entry(master, width=40)
        self.nom_entry.grid(row=0, column=1, sticky=tk.EW)
        
        ttk.Label(master, text="Ticker/Symbole:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.ticker_entry = ttk.Entry(master, width=40)
        self.ticker_entry.grid(row=1, column=1, sticky=tk.EW)

        ttk.Label(master, text="Quantité:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.quantite_entry = ttk.Entry(master, width=40)
        self.quantite_entry.grid(row=2, column=1, sticky=tk.EW)

        ttk.Label(master, text="Prix de Revient Unitaire (PRU):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.pru_entry = ttk.Entry(master, width=40)
        self.pru_entry.grid(row=3, column=1, sticky=tk.EW)

        if self.holding:
            self.nom_entry.insert(0, self.holding.nom)
            self.ticker_entry.insert(0, self.holding.ticker)
            self.quantite_entry.insert(0, str(self.holding.quantite).replace('.',','))
            self.pru_entry.insert(0, str(self.holding.pru).replace('.',','))
            
        return self.nom_entry

        def validate(self):
            try:
                float(self.quantite_entry.get().replace(',', '.'))
                float(self.pru_entry.get().replace(',', '.'))
            except ValueError:
                messagebox.showerror("Erreur", "La quantité et le PRU doivent être des nombres.", parent=self)
                return 0
        
            # CORRECTION : On ne vérifie plus que le ticker est obligatoire, seul le nom l'est.
            if not self.nom_entry.get().strip():
                messagebox.showerror("Erreur", "Le nom est obligatoire.", parent=self)
                return 0
            return 1



    def apply(self):
        self.result = {
            'nom': self.nom_entry.get().strip(),
            'ticker': self.ticker_entry.get().strip().upper(),
            'quantite': float(self.quantite_entry.get().replace(',', '.')),
            'pru': float(self.pru_entry.get().replace(',', '.'))
        }

class PortfolioManagerWindow(tk.Toplevel):
    """Fenêtre pour gérer les lignes d'un compte de portefeuille."""
    def __init__(self, parent_app, compte, market_service):
        super().__init__(parent_app.root)
        self.transient(parent_app.root)
        self.parent_app = parent_app
        self.compte = compte
        self.market_service = market_service
        
        self.title(f"Gestion du Portefeuille - {self.compte.nom}")
        self.geometry("950x500")
        self.grab_set()

        self.solde_especes_var = tk.StringVar()
        
        self.create_widgets()
        self.populate_holdings_list()
        self.protocol("WM_DELETE_WINDOW", self.save_and_close)

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        cols = ('nom', 'ticker', 'quantite', 'pru', 'cours_actuel', 'valeur_actuelle', 'plus_value')
        self.tree = ttk.Treeview(main_frame, columns=cols, show='headings')
        self.tree.heading('nom', text='Nom')
        self.tree.column('nom', width=200)
        self.tree.heading('ticker', text='Ticker')
        self.tree.column('ticker', width=80)
        self.tree.heading('quantite', text='Quantité')
        self.tree.column('quantite', anchor=tk.E, width=80)
        self.tree.heading('pru', text='PRU (€)')
        self.tree.column('pru', anchor=tk.E, width=80)
        self.tree.heading('cours_actuel', text='Cours (€)')
        self.tree.column('cours_actuel', anchor=tk.E, width=80)
        self.tree.heading('valeur_actuelle', text='Valeur Actuelle (€)')
        self.tree.column('valeur_actuelle', anchor=tk.E, width=120)
        self.tree.heading('plus_value', text='+/- Value (%)')
        self.tree.column('plus_value', anchor=tk.E, width=100)
        self.tree.pack(fill=tk.BOTH, expand=True)
        especes_frame = ttk.Frame(main_frame, padding=(0, 5))
        especes_frame.pack(fill=tk.X)
        ttk.Label(especes_frame, text="Solde Espèces (€):").pack(side=tk.LEFT)
        especes_entry = ttk.Entry(especes_frame, textvariable=self.solde_especes_var, width=15, justify=tk.RIGHT)
        especes_entry.pack(side=tk.LEFT, padx=5)
        button_frame = ttk.Frame(main_frame, padding=(0, 10, 0, 0))
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="Ajouter", command=self.add_holding).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Modifier", command=self.edit_holding).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Supprimer", command=self.delete_holding).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Mettre à jour les cours", command=self.update_market_prices).pack(side=tk.LEFT, padx=20)
        ttk.Button(button_frame, text="Enregistrer et Fermer", command=self.save_and_close).pack(side=tk.RIGHT)
        self.total_label = ttk.Label(button_frame, text="Total : ...", font=('TkDefaultFont', 10, 'bold'))
        self.total_label.pack(side=tk.RIGHT, padx=20)

    def populate_holdings_list(self):
        """Met à jour l'affichage en utilisant le dernier cours sauvegardé."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        valeur_titres = 0
        for holding in self.compte.lignes_portefeuille:
            cours_actuel = holding.dernier_cours if holding.dernier_cours > 0 else holding.pru
            valeur_ligne = holding.quantite * cours_actuel
            valeur_titres += valeur_ligne
            
            plus_value_pct = ((cours_actuel / holding.pru) - 1) * 100 if holding.pru > 0 else 0
            
            self.tree.insert('', 'end', iid=holding.id, values=(
                holding.nom, holding.ticker, holding.quantite,
                format_nombre_fr(holding.pru),
                format_nombre_fr(cours_actuel),
                format_nombre_fr(valeur_ligne),
                f"{plus_value_pct:+.2f}%".replace('.',',')
            ))
        
        self.solde_especes_var.set(format_nombre_fr(self.compte.solde_especes))
        try:
            solde_especes_val = float(self.solde_especes_var.get().replace(',', '.'))
        except (ValueError, tk.TclError):
            solde_especes_val = 0.0

        valeur_totale = valeur_titres + solde_especes_val
        self.total_label.config(text=f"Total Portefeuille : {format_nombre_fr(valeur_totale)} €")
        self.compte.solde = valeur_totale

    def update_market_prices(self):
        """Récupère les prix du marché et met à jour l'attribut 'dernier_cours'."""
        self.total_label.config(text="Mise à jour en cours...")
        self.update()

        for holding in self.compte.lignes_portefeuille:
            prix_eur = self.market_service.get_price_in_eur(holding.ticker)
            if prix_eur is not None:
                holding.dernier_cours = prix_eur
            else:
                print(f"Impossible de trouver le prix pour {holding.ticker}")
        
        self.populate_holdings_list()
        messagebox.showinfo("Succès", "Les cours du portefeuille ont été mis à jour.", parent=self)

    def save_and_close(self):
        """Sauvegarde les dernières modifications et ferme la fenêtre."""
        try:
            self.compte.solde_especes = float(self.solde_especes_var.get().replace(',', '.'))
            
            valeur_titres = 0
            for h in self.compte.lignes_portefeuille:
                cours = h.dernier_cours if h.dernier_cours > 0 else h.pru
                valeur_titres += h.quantite * cours
            
            self.compte.solde = round(valeur_titres + self.compte.solde_especes, 2)
            
            self.parent_app.sauvegarder_donnees()
            self.parent_app.mettre_a_jour_toutes_les_vues()
            self.destroy()
        except (ValueError, tk.TclError):
            messagebox.showerror("Erreur", "Le solde espèces doit être un nombre valide.", parent=self)
            
    def add_holding(self):
        dialog = HoldingEditDialog(self, "Ajouter une Ligne")
        if dialog.result:
            new_holding = self.parent_app.LignePortefeuille(**dialog.result)
            self.compte.lignes_portefeuille.append(new_holding)
            self.parent_app.sauvegarder_donnees()
            self.populate_holdings_list()
            self.parent_app.mettre_a_jour_liste()

    def edit_holding(self):
        selection = self.tree.selection()
        if not selection: return
        holding_id = int(selection[0])
        holding_to_edit = next((h for h in self.compte.lignes_portefeuille if h.id == holding_id), None)
        if holding_to_edit:
            dialog = HoldingEditDialog(self, "Modifier la Ligne", holding=holding_to_edit)
            if dialog.result:
                holding_to_edit.nom = dialog.result['nom']
                holding_to_edit.ticker = dialog.result['ticker']
                holding_to_edit.quantite = dialog.result['quantite']
                holding_to_edit.pru = dialog.result['pru']
                self.parent_app.sauvegarder_donnees()
                self.populate_holdings_list()
                self.parent_app.mettre_a_jour_liste()

    def delete_holding(self):
        selection = self.tree.selection()
        if not selection: return
        holding_id = int(selection[0])
        if messagebox.askyesno("Confirmer", "Supprimer cette ligne du portefeuille ?", parent=self):
            self.compte.lignes_portefeuille = [h for h in self.compte.lignes_portefeuille if h.id != holding_id]
            self.parent_app.sauvegarder_donnees()
            self.populate_holdings_list()
            self.parent_app.mettre_a_jour_liste()

class TransactionDialog(tk.Toplevel):
    """Boîte de dialogue pour ajouter ou modifier une transaction."""
    def __init__(self, parent, title, all_accounts, all_categories, ai_service, trans_existante=None):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.geometry("400x290")
        self.resizable(False, False)

        self.all_accounts = sorted([c.nom for c in all_accounts if c.suivi_budget])
        self.all_categories = sorted(list(all_categories))
        self.ai_service = ai_service
        self.trans_existante = trans_existante
        self.result = None

        self.date_var = tk.StringVar()
        self.desc_var = tk.StringVar()
        self.montant_var = tk.StringVar()
        self.cat_var = tk.StringVar()
        self.compte_var = tk.StringVar()
        self.pointe_var = tk.BooleanVar()
        self.type_var = tk.StringVar(value="Dépense")
        self.date_budgetaire_var = tk.StringVar()

        self._create_widgets()
        if self.trans_existante:
            self._populate_fields()
        else:
            self.date_var.set(date.today().strftime("%Y-%m-%d"))

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.grab_set()
        self.wait_window(self)

    def _create_widgets(self):
        # On dit au conteneur principal que sa colonne 1 et sa ligne 1 vont s'étirer
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        form_frame = ttk.Frame(self, padding="15")
        # Le sticky='nsew' fait en sorte que le frame remplisse toute la fenêtre
        form_frame.grid(row=0, column=0, sticky='nsew')

        # On dit au frame du formulaire que sa colonne 1 (celle des champs) doit s'étirer
        form_frame.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(form_frame, text="Type:").grid(row=row, column=0, sticky=tk.W, pady=3)
        type_combo = ttk.Combobox(form_frame, textvariable=self.type_var, values=["Dépense", "Revenu"], state="readonly")
        type_combo.grid(row=row, column=1, sticky=tk.EW)
        row += 1

        ttk.Label(form_frame, text="Date (AAAA-MM-JJ):").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Entry(form_frame, textvariable=self.date_var).grid(row=row, column=1, sticky=tk.EW)
        row += 1

        ttk.Label(form_frame, text="Description:").grid(row=row, column=0, sticky=tk.W, pady=3)
        desc_entry = ttk.Entry(form_frame, textvariable=self.desc_var)
        desc_entry.grid(row=row, column=1, sticky=tk.EW)
        desc_entry.bind("<FocusOut>", self._on_suggest_category)
        row += 1

        ttk.Label(form_frame, text="Date Budgétaire (optionnel):").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Entry(form_frame, textvariable=self.date_budgetaire_var).grid(row=row, column=1, sticky=tk.EW)
        row += 1

        ttk.Label(form_frame, text="Montant (€):").grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Entry(form_frame, textvariable=self.montant_var).grid(row=row, column=1, sticky=tk.EW)
        row += 1

        ttk.Label(form_frame, text="Catégorie:").grid(row=row, column=0, sticky=tk.W, pady=3)
        cat_combo = ttk.Combobox(form_frame, textvariable=self.cat_var, values=self.all_categories)
        cat_combo.grid(row=row, column=1, sticky=tk.EW)
        row += 1
        
        ttk.Label(form_frame, text="Compte:").grid(row=row, column=0, sticky=tk.W, pady=3)
        compte_combo = ttk.Combobox(form_frame, textvariable=self.compte_var, values=self.all_accounts, state="readonly")
        compte_combo.grid(row=row, column=1, sticky=tk.EW)
        row += 1

        ttk.Checkbutton(form_frame, text="Transaction Pointée", variable=self.pointe_var).grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1

        # On ajoute un "ressort" vertical pour pousser les boutons vers le bas
        form_frame.rowconfigure(row, weight=1)

        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=row+1, column=0, columnspan=2, sticky=tk.E, pady=(10,0))
        ttk.Button(button_frame, text="Valider", command=self._on_ok).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Annuler", command=self._on_cancel).pack(side=tk.LEFT, padx=5)
    def _populate_fields(self):
        montant = self.trans_existante.get('montant', 0.0)
        self.type_var.set("Dépense" if montant < 0 else "Revenu")
        self.montant_var.set(format_nombre_fr(abs(montant)))
        self.date_var.set(self.trans_existante.get('date', ''))
        self.desc_var.set(self.trans_existante.get('description', ''))
        self.cat_var.set(self.trans_existante.get('categorie', ''))
        self.compte_var.set(self.trans_existante.get('compte_affecte', ''))
        self.pointe_var.set(self.trans_existante.get('pointe', False))
        self.date_budgetaire_var.set(self.trans_existante.get('date_budgetaire', '')) # AJOUTER CETTE LIGNE

    
    def _on_suggest_category(self, event=None):
        if self.cat_var.get():
            return
            
        description = self.desc_var.get()
        if not description:
            return
        
        suggestion = self.ai_service.suggest_category(description)
        if suggestion:
            self.cat_var.set(suggestion)

    def _on_ok(self):
        try:
            date_val = datetime.strptime(self.date_var.get().strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
            desc_val = self.desc_var.get().strip()
            cat_val = self.cat_var.get().strip()
            compte_val = self.compte_var.get().strip()
            
            montant_brut = abs(float(self.montant_var.get().strip().replace(' ', '').replace(',', '.')))
            montant_val = -montant_brut if self.type_var.get() == "Dépense" else montant_brut

            date_budgetaire_val = self.date_budgetaire_var.get().strip()
            if date_budgetaire_val:
                # On valide le format si la date est saisie
                datetime.strptime(date_budgetaire_val, "%Y-%m-%d")
            
            if not all([date_val, desc_val, cat_val, compte_val]):
                raise ValueError("Tous les champs doivent être remplis.")

            self.result = {
                'id': self.trans_existante['id'] if self.trans_existante else None,
                'date': date_val, 'description': desc_val, 'montant': montant_val,
                'categorie': cat_val, 'compte_affecte': compte_val,
                'pointe': self.pointe_var.get(),
                'date_budgetaire': date_budgetaire_val or None 
            }
            self.destroy()

        except (ValueError, TypeError) as e:
            messagebox.showerror("Erreur de Saisie", f"Veuillez vérifier les champs.\n(Détail de l'erreur: {e})", parent=self)
            return

    def _on_cancel(self):
        self.result = None
        self.destroy()

class RapportVariationPatrimoineWindow(tk.Toplevel):
    def __init__(self, parent, cle_mois_annee, snapshot_debut, snapshot_fin, tous_les_comptes, transactions_du_mois):
        super().__init__(parent)
        self.transient(parent)
        self.title(f"Analyse Détaillée pour {cle_mois_annee}")
        self.geometry("950x800")
        self.minsize(800, 600)

        # --- ÉTAPE 1 : Logique de calcul (inchangée) ---
        soldes_debut = snapshot_debut.get('soldes_comptes', {})
        soldes_fin = snapshot_fin.get('soldes_comptes', {})
        noms_comptes_uniques = sorted(list(set(soldes_debut.keys()) | set(soldes_fin.keys())))
        compte_props = {c.nom: {'type': c.type_compte, 'classe_actif': c.classe_actif} for c in tous_les_comptes}
        augmentations_patrimoine = []
        diminutions_patrimoine = []
        for nom in noms_comptes_uniques:
            solde_d = soldes_debut.get(nom, 0.0)
            solde_f = soldes_fin.get(nom, 0.0)
            variation = solde_f - solde_d
            is_passif = compte_props.get(nom, {}).get('type') == 'Passif'
            impact = -variation if is_passif else variation
            item = {'nom': nom, 'solde_debut': solde_d, 'solde_fin': solde_f, 'impact': impact, 'type': 'Passif' if is_passif else 'Actif'}
            if impact > 0.01: augmentations_patrimoine.append(item)
            elif impact < -0.01: diminutions_patrimoine.append(item)
        soustotal_aug = sum(item['impact'] for item in augmentations_patrimoine)
        soustotal_dim = sum(item['impact'] for item in diminutions_patrimoine)
        total_variation_nette = soustotal_aug + soustotal_dim
        ventilation = defaultdict(float)
        for item in augmentations_patrimoine + diminutions_patrimoine:
            if item['type'] == 'Actif':
                classe = compte_props.get(item['nom'], {}).get('classe_actif', 'Non Renseigné')
                ventilation[classe] += item['impact']
            elif item['type'] == 'Passif':
                if item['impact'] > 0: ventilation["Réduction de Passif"] += item['impact']
                else: ventilation["Augmentation de Passif"] += item['impact']
        cash_flow_par_compte = defaultdict(float)
        for t in transactions_du_mois:
            compte = t.get('compte_affecte')
            if compte: cash_flow_par_compte[compte] += t.get('montant', 0.0)
        total_cash_flow = sum(cash_flow_par_compte.values())
        valeur_latente_et_autres = total_variation_nette - total_cash_flow

        # --- ÉTAPE 2 : NOUVEAU LAYOUT AVEC GRID ---
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1) # Le notebook s'étirera

        # Notebook (devient l'élément principal)
        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky='nsew', padx=10, pady=(10,5))
        
        # Cadre de réconciliation (en bas, ne s'étire pas)
        reconciliation_frame = ttk.LabelFrame(self, text="Explication de la Variation du Patrimoine Net", padding=10)
        reconciliation_frame.grid(row=1, column=0, sticky='ew', padx=10, pady=(5,10))
        reconciliation_frame.columnconfigure(1, weight=1)
        
        # --- DÉBUT DE LA NOUVELLE PRÉSENTATION ---
        style = ttk.Style(self)
        style.configure("Cadrage.TLabel", font=('TkDefaultFont', 10))
        style.configure("Cadrage.Bold.TLabel", font=('TkDefaultFont', 10, 'bold'))

        ttk.Label(reconciliation_frame, text="1. Votre activité du mois (cash-flow) a généré une épargne de :", style="Cadrage.TLabel").grid(row=0, column=0, columnspan=2, sticky='w')
        ttk.Label(reconciliation_frame, text=f"{total_cash_flow:+.2f} €".replace('.', ','), style="Cadrage.Bold.TLabel", foreground="green" if total_cash_flow >= 0 else "red").grid(row=0, column=2, sticky='e')
        
        ttk.Label(reconciliation_frame, text="2. En parallèle, vos actifs ont varié (plus/moins-values, etc.) de :", style="Cadrage.TLabel").grid(row=1, column=0, columnspan=2, sticky='w')
        ttk.Label(reconciliation_frame, text=f"{valeur_latente_et_autres:+.2f} €".replace('.', ','), style="Cadrage.Bold.TLabel", foreground="green" if valeur_latente_et_autres >= 0 else "red").grid(row=1, column=2, sticky='e')
        
        ttk.Separator(reconciliation_frame).grid(row=2, column=0, columnspan=3, sticky='ew', pady=5)

        ttk.Label(reconciliation_frame, text="3. Résultat : Votre patrimoine net a donc bien varié de :", style="Cadrage.TLabel").grid(row=3, column=0, columnspan=2, sticky='w')
        ttk.Label(reconciliation_frame, text=f"{total_variation_nette:+.2f} €".replace('.', ','), style="Cadrage.Bold.TLabel", foreground="green" if total_variation_nette >= 0 else "red").grid(row=3, column=2, sticky='e')
        # --- FIN DE LA NOUVELLE PRÉSENTATION ---

        # --- Onglet 1 : Analyse du Patrimoine ---
        # (Le code de cet onglet est identique à la version précédente)
        tab_patrimoine = ttk.Frame(notebook)
        notebook.add(tab_patrimoine, text="Analyse du Patrimoine")
        tab_patrimoine.columnconfigure(0, weight=1); tab_patrimoine.rowconfigure(0, weight=1)
        pane_patrimoine = ttk.PanedWindow(tab_patrimoine, orient=tk.VERTICAL); pane_patrimoine.grid(row=0, column=0, sticky='nsew', pady=5)
        frame_detail = ttk.Frame(pane_patrimoine); pane_patrimoine.add(frame_detail, weight=3)
        ttk.Label(frame_detail, text="Détail de la Variation par Compte", font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W, pady=(0,5))
        tree_patrimoine = ttk.Treeview(frame_detail, columns=('compte', 'var'), show='headings')
        tree_patrimoine.heading('compte', text="Compte"); tree_patrimoine.heading('var', text="Impact sur Patrimoine (€)")
        tree_patrimoine.column('compte', width=300); tree_patrimoine.column('var', anchor=tk.E)
        tree_patrimoine.pack(fill=tk.BOTH, expand=True)
        tree_patrimoine.tag_configure('gain', foreground='green'); tree_patrimoine.tag_configure('perte', foreground='red'); tree_patrimoine.tag_configure('total', font=('TkDefaultFont', 9, 'bold'))
        for item in sorted(augmentations_patrimoine, key=lambda x: x['impact'], reverse=True): tree_patrimoine.insert('', 'end', values=(item['nom'], f"{item['impact']:+.2f}".replace('.', ',')), tags=('gain',))
        tree_patrimoine.insert('', 'end', values=("SOUS-TOTAL DES AUGMENTATIONS", f"{soustotal_aug:+.2f}".replace('.', ',')), tags=('total', 'gain'))
        for item in sorted(diminutions_patrimoine, key=lambda x: x['impact']): tree_patrimoine.insert('', 'end', values=(item['nom'], f"{item['impact']:+.2f}".replace('.', ',')), tags=('perte',))
        tree_patrimoine.insert('', 'end', values=("SOUS-TOTAL DES DIMINUTIONS", f"{soustotal_dim:+.2f}".replace('.', ',')), tags=('total', 'perte'))
        tree_patrimoine.insert('', 'end', values=("TOTAL VARIATION NETTE", f"{total_variation_nette:+.2f}".replace('.', ',')), tags=('total',))
        frame_synthese = ttk.Frame(pane_patrimoine); pane_patrimoine.add(frame_synthese, weight=1)
        ttk.Label(frame_synthese, text="Synthèse par Classe d'Actif / Passif", font=('TkDefaultFont', 10, 'bold')).pack(anchor=tk.W, pady=(5,5))
        tree_synthese = ttk.Treeview(frame_synthese, columns=('classe', 'affectation'), show='headings')
        tree_synthese.heading('classe', text="Classe d'Actif / Passif"); tree_synthese.heading('affectation', text="Variation Nette (€)")
        tree_synthese.column('affectation', anchor=tk.E); tree_synthese.pack(fill=tk.BOTH, expand=True)
        tree_synthese.tag_configure('gain', foreground='green'); tree_synthese.tag_configure('perte', foreground='red'); tree_synthese.tag_configure('total', font=('TkDefaultFont', 9, 'bold'))
        for classe, montant in sorted(ventilation.items(), key=lambda x: x[1], reverse=True):
            if classe is None or montant is None: continue
            tag = 'gain' if montant > 0 else 'perte' if montant < 0 else ''
            tree_synthese.insert('', 'end', values=(classe, f"{montant:+.2f}".replace('.', ',')), tags=(tag,))
        tree_synthese.insert('', 'end', values=("TOTAL", f"{total_variation_nette:+.2f}".replace('.', ',')), tags=('total',))

        # --- Onglet 2 : Analyse du Cash-Flow ---
        # (Le code de cet onglet est identique à la version précédente)
        tab_cashflow = ttk.Frame(notebook); notebook.add(tab_cashflow, text="Analyse du Cash-Flow par Compte")
        tab_cashflow.columnconfigure(0, weight=1); tab_cashflow.rowconfigure(0, weight=1)
        tree_cashflow = ttk.Treeview(tab_cashflow, columns=('compte', 'flux'), show='headings')
        tree_cashflow.heading('compte', text="Compte"); tree_cashflow.heading('flux', text="Flux de Trésorerie Net (€)")
        tree_cashflow.column('compte', width=300); tree_cashflow.column('flux', anchor=tk.E)
        tree_cashflow.grid(row=0, column=0, sticky='nsew', pady=5)
        tree_cashflow.tag_configure('gain', foreground='green'); tree_cashflow.tag_configure('perte', foreground='red'); tree_cashflow.tag_configure('total', font=('TkDefaultFont', 9, 'bold'))
        flux_entrants = {c: m for c, m in cash_flow_par_compte.items() if m > 0}
        flux_sortants = {c: m for c, m in cash_flow_par_compte.items() if m < 0}
        soustotal_entrants = sum(flux_entrants.values())
        for compte, montant in sorted(flux_entrants.items(), key=lambda x: x[1], reverse=True): tree_cashflow.insert('', 'end', values=(compte, f"{montant:+.2f}".replace('.', ',')), tags=('gain',))
        tree_cashflow.insert('', 'end', values=("SOUS-TOTAL FLUX ENTRANTS", f"{soustotal_entrants:+.2f}".replace('.', ',')), tags=('total', 'gain'))
        soustotal_sortants = sum(flux_sortants.values())
        for compte, montant in sorted(flux_sortants.items(), key=lambda x: x[1]): tree_cashflow.insert('', 'end', values=(compte, f"{montant:+.2f}".replace('.', ',')), tags=('perte',))
        tree_cashflow.insert('', 'end', values=("SOUS-TOTAL FLUX SORTANTS", f"{soustotal_sortants:+.2f}".replace('.', ',')), tags=('total', 'perte'))
        tree_cashflow.insert('', 'end', values=("CASH-FLOW NET TOTAL", f"{total_cash_flow:+.2f}".replace('.', ',')), tags=('total',))

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()
        self.wait_window(self)