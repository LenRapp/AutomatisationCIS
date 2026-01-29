from flask import Flask, render_template, request, jsonify, send_file, session
import os
import uuid
import json
import pandas as pd
import threading
import time

# Import de vos modules existants
from src.extraction import analyser_pdf_cis
try:
    from src.comparator import compare_rules
except ImportError:
    compare_rules = None

try:
    from src.updater import run_dynamic_update
except ImportError:
    run_dynamic_update = None

# On importera les autres modules au fur et à mesure (comparator, updater)

app = Flask(__name__)
app.secret_key = "super_secret_key_cis"
app.config['UPLOAD_FOLDER'] = 'uploads'

# Dictionnaire global pour stocker la progression : { "task_id": {"progress": 50, "type": "extraction"} }
progress_status = {}

def clean_uploads():
    """Nettoyage simple du dossier uploads au démarrage"""
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    for f in os.listdir('uploads'):
        os.remove(os.path.join('uploads', f))

def convert_json_to_excel_flask(json_path, excel_path):
    """Génération Excel avec XlsxWriter (Version Flask)"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        items = data if isinstance(data, list) else data.get('items', [])
        if not items: return False

        df = pd.DataFrame(items)
        priority_cols = ['control_id', 'title', 'severity', 'description', 'rationale', 'impact', 'remediation']
        cols = [c for c in priority_cols if c in df.columns] + [c for c in df.columns if c not in priority_cols]
        df = df[cols]

        with pd.ExcelWriter(excel_path, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Benchmark')
            workbook = writer.book
            worksheet = writer.sheets['Benchmark']
            
            header_fmt = workbook.add_format({'bold': True, 'text_wrap': True, 'valign': 'top', 'fg_color': '#4F81BD', 'font_color': 'white', 'border': 1})
            text_fmt = workbook.add_format({'text_wrap': True, 'valign': 'top', 'border': 1})
            
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_fmt)
                if value in ['control_id', 'severity']: width = 15
                elif value == 'title': width = 40
                elif value in ['description', 'rationale', 'remediation']: width = 60
                elif value in ['audit', 'check', 'verification']: width = 80
                else: width = 25
                worksheet.set_column(col_num, col_num, width, text_fmt)
            
            worksheet.freeze_panes(1, 0)
        return True
    except Exception as e:
        print(f"Excel Error: {e}")
        return False

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
    progress_status[task_id] = {"progress": 0, "type": "extraction"}

    # Sauvegarde temporaire
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}_{file.filename}")
    file.save(filepath)

    def run_analysis(tid, fpath):
        try:
            # Callback pour mettre à jour la variable globale
            def update_progress(p):
                # p est entre 0.0 et 1.0 -> on le met en %
                if tid in progress_status:
                    progress_status[tid]["progress"] = int(p * 100)

            raw_data = analyser_pdf_cis(fpath, progress_callback=update_progress)
            
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

            # Pour que "1.10" soit après "1.9" et pas après "1.1"
            try:
                final_data.sort(key=lambda x: [int(p) if p.isdigit() else p for p in x.get('control_id', '').split('.')])
            except:
                final_data.sort(key=lambda x: x.get('control_id', ''))

            # Sauvegarde du résultat JSON
            json_path = fpath + ".json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, indent=4, ensure_ascii=False)
            
            # Fin de tâche
            if tid in progress_status:
                progress_status[tid]["progress"] = 100
        except Exception as e:
            print(f"Erreur extraction: {e}")
            if tid in progress_status:
                progress_status[tid]["progress"] = -1 # Code erreur

    # Lancement en arrière-plan (Thread) pour ne pas bloquer le serveur
    thread = threading.Thread(target=run_analysis, args=(task_id, filepath))
    thread.start()

    return jsonify({'task_id': task_id})

@app.route('/api/progress/<task_id>')
def get_progress(task_id):
    """L'interface JS appelle cette URL toutes les secondes"""
    task_info = progress_status.get(task_id)
    if task_info is None:
        return jsonify({'status': 'not_found'}), 404
    
    prog = task_info.get("progress", 0)
    task_type = task_info.get("type", "extraction")

    # Si fini, on renvoie aussi l'URL de téléchargement
    result = {'progress': prog}
    
    if prog == 100:
        if task_type == "comparaison":
            result['redirect'] = f"/result/comparaison/{task_id}"
        elif task_type == "update":
            result['redirect'] = f"/result/update/{task_id}"
        else:
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

@app.route('/download/diff/<task_id>')
def download_diff(task_id):
    filename = f"{task_id}_diff.json"
    path = os.path.join('uploads', filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name=f"cis_diff_{task_id}.json")
    return "Fichier introuvable", 404


# COMPARAISON

@app.route('/comparaison')
def page_comparaison():
    return render_template('comparaison.html')

@app.route('/api/compare', methods=['POST'])
def process_comparaison():
    if 'file1' not in request.files or 'file2' not in request.files:
        return jsonify({'error': 'Deux fichiers sont requis'}), 400
    
    file1 = request.files['file1']
    file2 = request.files['file2']

    if file1.filename == '' or file2.filename == '':
        return jsonify({'error': 'Noms de fichiers vides'}), 400

    task_id = str(uuid.uuid4())
    progress_status[task_id] = {"progress": 0, "type": "comparaison"}

    path1 = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}_1_{file1.filename}")
    path2 = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}_2_{file2.filename}")
    file1.save(path1)
    file2.save(path2)

    def run_compare(tid, p1, p2):
        try:
            # Extraction Fichier 1 (0% -> 50%)
            def update_p1(p):
                if tid in progress_status:
                    progress_status[tid]["progress"] = int(p * 50)
            
            raw1 = analyser_pdf_cis(p1, progress_callback=update_p1)
            # Déduplication
            d1 = {}
            for r in raw1:
                cid = r.get('control_id')
                if cid:
                    if cid not in d1 or r.get('page', 0) > d1[cid].get('page', 0):
                        d1[cid] = r
            list1 = list(d1.values())

            # Extraction Fichier 2 (50% -> 100%)
            def update_p2(p):
                # On sature à 99 pour laisser un peu de place au calcul final si besoin, 
                # ou on va jusqu'à 100 si on finit ici.
                if tid in progress_status:
                    progress_status[tid]["progress"] = 50 + int(p * 49) 

            raw2 = analyser_pdf_cis(p2, progress_callback=update_p2)
            # Déduplication
            d2 = {}
            for r in raw2:
                cid = r.get('control_id')
                if cid:
                    if cid not in d2 or r.get('page', 0) > d2[cid].get('page', 0):
                        d2[cid] = r
            list2 = list(d2.values())

            # Comparaison Finale
            if compare_rules:
                diff = compare_rules(list1, list2)
                
                # Sauvegarde Résultat
                res_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{tid}_diff.json")
                with open(res_path, 'w', encoding='utf-8') as f:
                    json.dump(diff, f, indent=4, ensure_ascii=False)
                
                if tid in progress_status:
                    progress_status[tid]["progress"] = 100
            else:
                 if tid in progress_status:
                    progress_status[tid]["progress"] = -1 

        except Exception as e:
            print(f"Erreur comparaison: {e}")
            if tid in progress_status:
                progress_status[tid]["progress"] = -1

    thread = threading.Thread(target=run_compare, args=(task_id, path1, path2))
    thread.start()

    return jsonify({'task_id': task_id})

@app.route('/result/comparaison/<task_id>')
def result_comparaison(task_id):
    res_path = os.path.join('uploads', f"{task_id}_diff.json")
    if not os.path.exists(res_path):
        return "Résultat introuvable"
    
    with open(res_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Statistiques
    stats = {
        'added': len(data.get('added', [])),
        'deleted': len(data.get('deleted', [])),
        'modified': len(data.get('modified', []))
    }

    return render_template('result_comparaison.html', diff=data, stats=stats, task_id=task_id)


# MISE À JOUR

@app.route('/update')
def page_update():
    return render_template('update.html')

@app.route('/api/update', methods=['POST'])
def process_update():
    # Vérification inputs
    if 'source_file' not in request.files or 'summary_file' not in request.files:
        return jsonify({'error': 'Fichiers manquants'}), 400
    
    src = request.files['source_file']
    summ = request.files['summary_file']
    old_year = request.form.get('old_year', '2025')
    new_year = request.form.get('new_year', '2026')

    task_id = str(uuid.uuid4())
    progress_status[task_id] = {"progress": 0, "type": "update"}

    path_src = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}_src_{src.filename}")
    path_summ = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}_summ.json")
    path_out_json = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}_final.json")
    path_out_xls = os.path.join(app.config['UPLOAD_FOLDER'], f"{task_id}_final.xlsx")

    src.save(path_src)
    summ.save(path_summ)

    def run_update_task(tid, p_src, p_summ, p_out, p_xls, oy, ny):
        try:
            #Conversion Source si PDF (0-25%)
            actual_src_json = p_src
            
            if p_src.lower().endswith('.pdf'):
                def update_p_pdf(p):
                     if tid in progress_status: progress_status[tid]["progress"] = int(p * 25)
                
                raw = analyser_pdf_cis(p_src, progress_callback=update_p_pdf)
                # Déduplication standard
                unique = {}
                for r in raw:
                    cid = r.get('control_id')
                    if cid:
                        if cid not in unique or r.get('page', 0) > unique[cid].get('page', 0):
                            unique[cid] = r
                
                # Sauvegarde JSON intermédiaire
                actual_src_json = p_src + ".json"
                with open(actual_src_json, 'w', encoding='utf-8') as f:
                    json.dump({"items": list(unique.values())}, f, indent=4)
            else:
                 if tid in progress_status: progress_status[tid]["progress"] = 25

            # Mise à jour (25-90%)
            def update_p_upd(p):
                 # p de 0 à 1.0 -> map to 25-90
                 if tid in progress_status: progress_status[tid]["progress"] = 25 + int(p * 65)

            if run_dynamic_update:
                stats = run_dynamic_update(actual_src_json, p_summ, p_out, oy, ny, progress_callback=update_p_upd)
                
                # Sauvegarde stats pour affichage
                with open(p_out + ".stats", 'w', encoding='utf-8') as f:
                    json.dump(stats, f)
            
            # Excel (90-100%)
            if tid in progress_status: progress_status[tid]["progress"] = 95
            convert_json_to_excel_flask(p_out, p_xls)
            
            if tid in progress_status: progress_status[tid]["progress"] = 100

        except Exception as e:
            print(f"Update Error: {e}")
            if tid in progress_status: progress_status[tid]["progress"] = -1

    thread = threading.Thread(target=run_update_task, args=(task_id, path_src, path_summ, path_out_json, path_out_xls, old_year, new_year))
    thread.start()

    return jsonify({'task_id': task_id})

@app.route('/result/update/<task_id>')
def result_update(task_id):
    stats_path = os.path.join('uploads', f"{task_id}_final.json.stats")
    stats = {}
    if os.path.exists(stats_path):
        with open(stats_path, 'r') as f: stats = json.load(f)
    return render_template('result_update.html', stats=stats, task_id=task_id)

@app.route('/download/final_json/<task_id>')
def download_final_json(task_id):
    path = os.path.join('uploads', f"{task_id}_final.json")
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name=f"cis_final_{task_id}.json")
    return "Fichier introuvable", 404

@app.route('/download/excel/<task_id>')
def download_excel(task_id):
    path = os.path.join('uploads', f"{task_id}_final.xlsx")
    if os.path.exists(path):
        return send_file(path, as_attachment=True, download_name=f"cis_final_{task_id}.xlsx")
    return "Fichier introuvable", 404


if __name__ == '__main__':
    clean_uploads()
    # Debug=True permet le rechargement auto
    app.run(debug=True, port=5000)
