# -*- coding: utf-8 -*-

import tkinter as tk
import os
import sys

from app import PatrimoineApp  # On importe notre classe depuis le nouveau fichier

# Point d'entrée de l'application
if __name__ == "__main__":
    print("INFO: Lancement ...")
    
    # On détermine le répertoire de base de l'application
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    # On crée la fenêtre principale
    root = tk.Tk()
    
    # On crée une instance de notre application en lui passant la fenêtre et le répertoire
    app = PatrimoineApp(root, base_dir)
    
    # On lance la boucle principale de l'interface graphique
    print("INFO: Lancement mainloop...")
    root.mainloop()
    print("INFO: Fermé.")