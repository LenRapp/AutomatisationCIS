 # 🛡️ Automatisation CIS et Upload Fichier
   
Outil professionnel d'extraction et de structuration des règles de sécurité CIS (Center for Internet Security) à partir de fichiers PDF.
   
## 🚀 Installation rapide

Création de l'environnement virtuel (.venv)
```bash
python3 -m venv .venv
```
Activation de l'environnement
```bash
source .venv/bin/activate
```
  
Ouvrez un terminal dans le dossier du projet et installez les dépendances :
  ```bash
  pip install -r requirements.txt
  ```
 Lancer l'application :
```bash
streamlit run app.py
```
## 📂 Structure du projet

```text
Projet/
│
├── requirements.txt        # Liste des dépendances Python nécessaires au projet
├── config.json             # Fichier de configuration central (mots-clés, règles et paramètres d’extraction)
├── app.py                  # Interface utilisateur développée avec Streamlit
├── .gitignore              # Fichiers à ignorer par Git (ex: dossiers temporaires, environnements virtuels)
│
└── src/
    ├── __init__.py         # Initialisation du module src
    ├── extraction.py       # Moteur d’analyse des fichiers PDF et logique métier principale
    └── consolidation.py   # Module de regroupement et de consolidation des fichiers JSON (pivot des données)
    └── updater.py          # Module de mise à jour : applique les changements et remplace les années (ex: 2025 -> 2026) pour le rendu final
```

  
