from flask import Flask, render_template, request, jsonify, send_file, session
import os
import uuid
import json
import pandas as pd
import threading
import time

# Import de vos modules existants
from src.extraction import analyser_pdf_cis
# On importera les autres modules au fur et à mesure (comparator, updater)

app = Flask(__name__)
app.secret_key = "super_secret_key_cis"
app.config['UPLOAD_FOLDER'] = 'uploads'

# Dictionnaire global pour stocker la progression : { "task_id": 50 }
progress_status = {}

def clean_uploads():
    """Nettoyage simple du dossier uploads au démarrage"""
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    for f in os.listdir('uploads'):
        os.remove(os.path.join('uploads', f))

@app.route('/')
def index():
    return render_template('index.html')

# --- 1. EXTRACTION ---

@app.route('/extraction')
def page_extraction():
    return render_template('extraction.html')

@app.route('/api/extract', methods=['POST'])
def process_extraction():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier envoyé'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nom de fichier vide'}), 400

    # ID unique pour suivre la tâche
    task_id = str(uuid.uuid4())
    progress_status[task_id] = 0

    # Sauvegarde temporaire
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}_{file.filename}")
    file.save(filepath)

    def run_analysis(tid, fpath):
        try:
            # Callback pour mettre à jour la variable globale
            def update_progress(p):
                # p est entre 0.0 et 1.0 -> on le met en %
                progress_status[tid] = int(p * 100)

            # src/extraction.py utilise pdfplumber.open(fichier_pdf) qui accepte un path.
            raw_data = analyser_pdf_cis(fpath, progress_callback=update_progress)
            
            # --- LOGIQUE DE DÉDUPLICATION (Sommaire vs Contenu) ---
            # On ne garde que l'occurrence avec le numéro de page le plus élevé
            unique_rules = {}
            for rule in raw_data:
                c_id = rule.get('control_id')
                if c_id:
                    if c_id in unique_rules:
                        old_page = unique_rules[c_id].get('page', 0)
                        new_page = rule.get('page', 0)
                        if new_page > old_page:
                            unique_rules[c_id] = rule
                    else:
                        unique_rules[c_id] = rule
            
            final_data = list(unique_rules.values())

            # TRI OPTIONNEL : Pour que "1.10" soit après "1.9" et pas après "1.1"
            try:
                final_data.sort(key=lambda x: [int(p) if p.isdigit() else p for p in x.get('control_id', '').split('.')])
            except:
                final_data.sort(key=lambda x: x.get('control_id', ''))

            # Sauvegarde du résultat JSON
            json_path = fpath + ".json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, indent=4, ensure_ascii=False)
            
            # Fin de tâche
            progress_status[tid] = 100
        except Exception as e:
            print(f"Erreur extraction: {e}")
            progress_status[tid] = -1 # Code erreur

    # Lancement en arrière-plan (Thread) pour ne pas bloquer le serveur
    thread = threading.Thread(target=run_analysis, args=(task_id, filepath))
    thread.start()

    return jsonify({'task_id': task_id})

@app.route('/api/progress/<task_id>')
def get_progress(task_id):
    """L'interface JS appelle cette URL toutes les secondes"""
    prog = progress_status.get(task_id)
    if prog is None:
        return jsonify({'status': 'not_found'}), 404
    
    # Si fini, on renvoie aussi l'URL de téléchargement
    result = {'progress': prog}
    if prog == 100:
        result['redirect'] = f"/result/extraction/{task_id}"
    elif prog == -1:
        result['error'] = "Erreur lors du traitement"
        
    return jsonify(result)

@app.route('/result/extraction/<task_id>')
def result_extraction(task_id):
    # Récupération du JSON généré
    # On cherche le fichier qui commence par task_id dans uploads
    target_file = None
    for f in os.listdir('uploads'):
        if f.startswith(task_id) and f.endswith(".json"):
            target_file = os.path.join('uploads', f)
            break
            
    if not target_file:
        return "Résultat introuvable (peut-être expiré ?)"

    with open(target_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    return render_template('result_extraction.html', rules=data, task_id=task_id)

@app.route('/download/json/<task_id>')
def download_json(task_id):
    for f in os.listdir('uploads'):
        if f.startswith(task_id) and f.endswith(".json"):
            return send_file(os.path.join('uploads', f), as_attachment=True, download_name=f"cis_export_{task_id}.json")
    return "Fichier introuvable", 404

if __name__ == '__main__':
    clean_uploads()
    # Debug=True permet le rechargement auto
    app.run(debug=True, port=5000)
