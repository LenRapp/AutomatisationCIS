import streamlit as st
import json
import os
import tempfile
import concurrent.futures
import io
import pandas as pd  # <--- AJOUT MAJEUR POUR EXCEL

# --- 1. IMPORTS DES MODULES (Extraction, Comparaison, Updater) ---

from src.extraction import analyser_pdf_cis

# Import Comparator (Gestion des erreurs si le fichier manque)
try:
    from src.comparator import compare_rules

    COMPARATOR_AVAILABLE = True
except ImportError:
    compare_rules = None
    COMPARATOR_AVAILABLE = False

# Import Updater (Gestion des erreurs si le fichier manque)
try:
    from src.updater import load_json_file, save_json_file, update_year_in_text

    UPDATER_AVAILABLE = True
except ImportError:
    load_json_file = None
    UPDATER_AVAILABLE = False

# --- 2. CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Automatisation CIS", page_icon="🛡️", layout="wide")


# --- 3. FONCTIONS UTILITAIRES (Communes) ---

def clean_text(text):
    """Nettoie le texte pour l'affichage."""
    if not isinstance(text, str):
        return str(text)
    return " ".join(text.split())


def save_uploaded_file_temp(uploaded_file):
    """Sauvegarde temporaire pour les fonctions backend nécessitant un chemin de fichier."""
    try:
        suffix = os.path.splitext(uploaded_file.name)[1]
        if not suffix: suffix = ".json"  # Fallback
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getvalue())
            return tmp.name
    except Exception as e:
        st.error(f"Erreur sauvegarde temp: {e}")
        return None


def convert_json_to_excel(json_path, excel_path):
    """Convertit le fichier JSON final en fichier Excel pour téléchargement."""
    try:
        # Lecture du JSON généré
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Normalisation (on récupère la liste des règles)
        items = data if isinstance(data, list) else data.get('items', [])

        if not items:
            return False, "Le JSON est vide."

        # Création DataFrame Pandas
        df = pd.DataFrame(items)

        # Réorganisation des colonnes pour avoir l'ID et le Titre au début (UX)
        priority_cols = ['control_id', 'title', 'severity', 'description', 'rationale', 'impact', 'remediation']
        # On prend les colonnes prioritaires qui existent + le reste
        cols = [c for c in priority_cols if c in df.columns] + [c for c in df.columns if c not in priority_cols]
        df = df[cols]

        # Export Excel (sans l'index pandas)
        df.to_excel(excel_path, index=False)
        return True, "Succès"
    except Exception as e:
        return False, str(e)


# --- 4. LOGIQUE COMPARATEUR ---

def compare_data_adapter(data1, data2):
    """Adapte la sortie de compare_rules pour l'affichage Streamlit."""
    if not compare_rules: return None

    raw = compare_rules(data1, data2)
    adapted_modified = []

    for mod in raw.get('modified', []):
        changes = mod.get('changes', {})
        old_sev = changes.get('severity', {}).get('old', 'Inchangé')
        new_sev = changes.get('severity', {}).get('new', 'Inchangé')
        old_title = changes.get('title', {}).get('old', 'Inchangé')
        new_title = changes.get('title', {}).get('new', mod.get('control_id'))

        adapted_modified.append({
            "control_id": mod.get('control_id'),
            "old": {'severity': old_sev, 'title': old_title},
            "new": {'severity': new_sev, 'title': new_title},
            "changes": changes
        })

    return {
        "added": raw.get('added', []),
        "removed": raw.get('deleted', []),
        "modified": adapted_modified,
        "stats": {
            "count1": len(data1),
            "count2": len(data2),
            "added_count": len(raw.get('added', [])),
            "removed_count": len(raw.get('deleted', [])),
            "modified_count": len(raw.get('modified', []))
        }
    }


# On retire le cache pour permettre la mise à jour de la barre de progression en direct
def get_cached_extraction(file_content, file_name, _progress_callback=None):
    virtual_file = io.BytesIO(file_content)
    virtual_file.name = file_name
    raw_data = analyser_pdf_cis(virtual_file, progress_callback=_progress_callback)
    
    # DÉDUPLICATION INTELLIGENTE (Sommaire vs Contenu)
    # On garde la version avec le numéro de page le plus élevé (le vrai contenu est après le sommaire)
    unique_rules = {}
    for rule in raw_data:
        c_id = rule.get('control_id')
        if c_id:
            # Si on a déjà vu cet ID, on compare les pages
            if c_id in unique_rules:
                old_page = unique_rules[c_id].get('page', 0)
                new_page = rule.get('page', 0)
                if new_page > old_page:
                    unique_rules[c_id] = rule
            else:
                unique_rules[c_id] = rule
    
    # On retourne la liste des valeurs (sans doublons)
    return list(unique_rules.values())


def process_file_wrapper(uploaded_file, progress_callback=None):
    return get_cached_extraction(uploaded_file.getvalue(), uploaded_file.name, _progress_callback=progress_callback)


# --- 5. LOGIQUE UPDATER (Backend) ---

def run_dynamic_update(source_path, summary_path, output_path, old_year, new_year, progress_callback=None):
    """Logique métier de mise à jour utilisant les outils de src/updater.py"""
    data_source = load_json_file(source_path)
    data_summary = load_json_file(summary_path)

    summary_list = data_summary
    if isinstance(data_summary, dict):
        summary_list = data_summary.get("modified", data_summary.get("items", []))

    updates_map = {r.get('control_id'): r for r in summary_list if r.get('control_id')}
    stats = {"updated": 0, "unchanged": 0, "year_replaced": 0}
    new_data = []

    source_items = data_source if isinstance(data_source, list) else data_source.get('items', [])
    fields_to_update = ['title', 'description', 'severity', 'remediation', 'rationale', 'impact']
    
    total_items = len(source_items)
    
    for i, rule in enumerate(source_items):
        if progress_callback:
            progress_callback((i + 1) / total_items)

        rule_id = rule.get('control_id')

        # A. Update fields
        if rule_id in updates_map:
            new_info = updates_map[rule_id]
            changes = new_info.get('changes', new_info)
            for field in fields_to_update:
                val = changes.get(field)
                if isinstance(val, dict) and 'new' in val:
                    rule[field] = val['new']
                elif val:
                    rule[field] = val
            stats["updated"] += 1
        else:
            stats["unchanged"] += 1

        # B. Update Year
        for key, value in rule.items():
            if isinstance(value, str) and old_year in value:
                new_val = update_year_in_text(value, old_year, new_year)
                if new_val != value:
                    rule[key] = new_val
                    stats["year_replaced"] += 1

        new_data.append(rule)

    final_structure = new_data if isinstance(data_source, list) else {"items": new_data}
    save_json_file(final_structure, output_path)
    return stats


# --- 6. MAIN & INTERFACE ---

def main():
    st.title("🛡️ Automatisation & Maintenance CIS")

    mode = st.sidebar.radio(
        "Navigation",
        ("📄 Analyse PDF (Extraction/Comparaison)", "🔄 Générateur de Benchmark (Mise à jour)")
    )

    st.sidebar.divider()

    # ---------------------------------------------------------
    # MODE 1 : ANALYSE PDF
    # ---------------------------------------------------------
    if mode == "📄 Analyse PDF (Extraction/Comparaison)":

        if 'comparison_data' not in st.session_state:
            st.session_state.comparison_data = None

        def clear_state():
            st.session_state.comparison_data = None

        uploaded_files = st.file_uploader(
            "Déposez vos fichiers PDF CIS (1 pour extraction, 2 pour comparaison)",
            type="pdf",
            accept_multiple_files=True,
            on_change=clear_state,
            key="pdf_uploader"
        )

        if len(uploaded_files) == 2:
            file1, file2 = uploaded_files
            st.info(f"🚀 Comparaison : **{file1.name}** vs **{file2.name}**")

            if st.button("🚀 LANCER LA COMPARAISON", type="primary"):
                if not COMPARATOR_AVAILABLE:
                    st.error("src/comparator.py introuvable.")
                else:
                    prog_bar = st.progress(0, text="0% - Lancement...")
                    
                    # Analyse Fichier 1 (0% -> 45%)
                    def update_p1(p):
                        # p est entre 0.0 et 1.0
                        current = int(p * 45)
                        prog_bar.progress(current, text=f"{current}% - Analyse {file1.name} ({int(p*100)}%)...")

                    d1 = process_file_wrapper(file1, progress_callback=update_p1)

                    # Analyse Fichier 2 (45% -> 90%)
                    def update_p2(p):
                        current = 45 + int(p * 45)
                        prog_bar.progress(current, text=f"{current}% - Analyse {file2.name} ({int(p*100)}%)...")

                    d2 = process_file_wrapper(file2, progress_callback=update_p2)

                    prog_bar.progress(90, text="90% - Calcul des différences...")

                    if d1 and d2:
                        st.session_state.comparison_data = compare_data_adapter(d1, d2)
                        prog_bar.progress(100, text="100% - Terminé !")
                        prog_bar.empty()
                        st.success("Comparaison terminée !")
                    else:
                        st.error("Erreur extraction PDF.")

        elif len(uploaded_files) == 1:
            file1 = uploaded_files[0]
            st.info(f"📄 Extraction : **{file1.name}**")
            if st.button("🚀 LANCER L'EXTRACTION", type="primary"):
                prog_bar = st.progress(0, text="0% - Lancement...")
                
                def update_p(p):
                    prog_bar.progress(int(p * 100), text=f"{int(p*100)}% - Analyse {file1.name}...")

                data = process_file_wrapper(file1, progress_callback=update_p)
                
                if data:
                    st.session_state.comparison_data = {"single_mode": True, "data": data}
                    prog_bar.progress(100, text="100% - Terminé !")
                    prog_bar.empty()
                    st.success("Réussi !")

        if st.session_state.comparison_data:
            res = st.session_state.comparison_data

            if res.get("single_mode"):
                data = res["data"]
                # TRI : On s'assure que l'ordre est correct (par ID)
                try:
                    data.sort(key=lambda x: [int(p) if p.isdigit() else p for p in x.get('control_id', '').split('.')])
                except:
                    data.sort(key=lambda x: x.get('control_id', ''))

                st.divider()
                c1, c2 = st.columns([1, 3])
                c1.metric("Règles", len(data))
                c2.download_button("📥 Télécharger JSON", json.dumps(data, indent=4, ensure_ascii=False),
                                   "cis_export.json", "application/json")
                
                st.divider()
                for i, r in enumerate(data):
                    icon = "✅" if r.get('severity') != "Unknown" else "⚠️"
                    with st.expander(f"{icon} [{r.get('control_id')}] {clean_text(r.get('title'))}"):
                        c_id, c_sev = st.columns([1, 4])
                        c_id.text_input("ID", r.get('control_id'), key=f"id_{i}", disabled=True)
                        c_sev.text_input("Sévérité", r.get('severity'), key=f"sev_{i}", disabled=True)
                        st.text_area("Description", clean_text(r.get('description', '')), height=100, key=f"desc_{i}")
                        t1, t2, t3 = st.tabs(["Justification", "Impact", "Remédiation"])
                        t1.info(clean_text(r.get('rationale', 'N/A')))
                        t2.warning(clean_text(r.get('impact', 'N/A')))
                        t3.code(r.get('remediation', '')) # On garde le code brut pour la lisibilité
                        st.caption(f"Page : {r.get('page')}")
            else:
                stats = res.get('stats', {})
                
                # FONCTION DE TRI INTERNE
                def natural_sort_key(item):
                    try:
                        # Tente de trier comme des versions (1.2.3)
                        return [int(p) if p.isdigit() else p for p in item.get('control_id', '').split('.')]
                    except:
                        return item.get('control_id', '')

                # Application du tri aux listes
                res['added'].sort(key=natural_sort_key)
                res['removed'].sort(key=natural_sort_key)
                res['modified'].sort(key=natural_sort_key)

                st.divider()
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Ancien", stats.get('count1', 0))
                m2.metric("Nouveau", stats.get('count2', 0), delta=stats.get('count2', 0) - stats.get('count1', 0))
                m3.metric("Ajouts", stats.get('added_count', 0))
                m4.metric("Suppressions", stats.get('removed_count', 0), delta_color="inverse")

                st.download_button(
                    "📥 Télécharger le fichier Résumé (pour Mise à jour)",
                    json.dumps(res.get('modified'), indent=4, ensure_ascii=False),
                    "resume_modifications.json",
                    "application/json"
                )

                tab_add, tab_rem, tab_mod = st.tabs([
                    f"✅ Ajouts ({stats.get('added_count', 0)})", 
                    f"❌ Suppressions ({stats.get('removed_count', 0)})", 
                    f"⚠️ Modifications ({stats.get('modified_count', 0)})"
                ])

                with tab_add:
                    for r in res.get('added', []):
                        with st.expander(f"➕ [{r.get('control_id')}] {clean_text(r.get('title'))}"):
                            st.success("✅ Règle Ajoutée")
                            st.json(r)

                with tab_rem:
                    for r in res.get('removed', []):
                        with st.expander(f"➖ [{r.get('control_id')}] {clean_text(r.get('title'))}"):
                            st.error("❌ Règle Supprimée")
                            st.json(r)

                with tab_mod:
                    for item in res.get('modified', []):
                        changes = item.get('changes', {})
                        title_clean = clean_text(item.get('new', {}).get('title'))
                        title_str = f"📝 [{item.get('control_id')}] {title_clean} ({len(changes)} chgts)"
                        
                        with st.expander(title_str):
                            if not changes:
                                st.info("Changement détecté mais non listé (ex: espace vide).")
                            
                            for field, vals in changes.items():
                                st.markdown(f"**Champ modifié : `{field}`**")
                                col_a, col_b = st.columns(2)
                                with col_a:
                                    st.caption("🔴 Avant")
                                    st.text(clean_text(vals.get('old', 'N/A')))
                                with col_b:
                                    st.caption("🟢 Après")
                                    st.text(clean_text(vals.get('new', 'N/A')))
                                st.divider()

    # ---------------------------------------------------------
    # MODE 2 : GÉNÉRATEUR BENCHMARK (JSON + EXCEL)
    # ---------------------------------------------------------
    elif mode == "🔄 Générateur de Benchmark (Mise à jour)":
        st.header("Générateur de Benchmark Mis à Jour")
        st.markdown("Générez une nouvelle version (ex: 2026) à partir d'un ancien fichier et d'un résumé.")

        c1, c2 = st.columns(2)
        old_year = c1.text_input("Année Source", value="2025")
        new_year = c2.text_input("Nouvelle Année", value="2026")

        col_src, col_res = st.columns(2)
        src_file = col_src.file_uploader("Source (Ancien Benchmark - JSON ou PDF)", type=["json", "pdf"])
        res_file = col_res.file_uploader("Résumé (Modifications - JSON)", type=["json"])

        if src_file and res_file:
            if st.button("⚡ GÉNÉRER LA VERSION FINALE", type="primary"):
                if not UPDATER_AVAILABLE:
                    st.error("Module src/updater.py manquant.")
                else:
                    prog_update = st.progress(0, text="Démarrage du processus...")
                    
                    p_src = None; p_res = None; p_out = None; p_excel = None; p_pdf_temp = None

                    try:
                        # ÉTAPE 1 : 25%
                        prog_update.progress(25, text="25% - Analyse du fichier source...")
                        if src_file.type == "application/pdf":
                            pdf_data = get_cached_extraction(src_file.getvalue(), src_file.name)
                            if not pdf_data:
                                st.error("Echec extraction PDF."); st.stop()

                            fd, p_pdf_temp = tempfile.mkstemp(suffix=".json")
                            os.close(fd)
                            with open(p_pdf_temp, "w", encoding="utf-8") as f:
                                json.dump(pdf_data, f, indent=4)
                            p_src = p_pdf_temp
                        else:
                            p_src = save_uploaded_file_temp(src_file)

                        # ÉTAPE 2 : 50%
                        prog_update.progress(50, text="50% - Préparation du fichier résumé...")
                        p_res = save_uploaded_file_temp(res_file)
                        fd, p_out = tempfile.mkstemp(suffix=".json")
                        os.close(fd)
                        fd_xls, p_excel = tempfile.mkstemp(suffix=".xlsx")
                        os.close(fd_xls)

                        # ÉTAPE 3 : 75%
                        if p_src and p_res:
                            def update_p_upd(p):
                                # 75% -> 95%
                                current = 75 + int(p * 20)
                                prog_update.progress(current, text=f"{current}% - Application des mises à jour ({int(p*100)}%)...")

                            stats = run_dynamic_update(p_src, p_res, p_out, old_year, new_year, progress_callback=update_p_upd)
                            
                            # Conversion Excel
                            success_xls, msg_xls = convert_json_to_excel(p_out, p_excel)

                            # ÉTAPE 4 : 100%
                            prog_update.progress(100, text="100% - Génération Excel terminée !")
                            st.balloons()
                            st.success("✅ Processus terminé avec succès !")
                            prog_update.empty()

                            if success_xls:
                                st.info("📊 Conversion Excel effectuée automatiquement.")
                            else:
                                st.warning(f"⚠️ Échec conversion Excel : {msg_xls}")

                            k1, k2, k3 = st.columns(3)
                            k1.metric("Mises à jour", stats['updated'])
                            k2.metric("Remplacements Année", stats['year_replaced'])
                            k3.metric("Inchangées", stats['unchanged'])

                            col_dl1, col_dl2 = st.columns(2)

                            # Bouton JSON
                            with open(p_out, "r", encoding="utf-8") as f:
                                final_json = f.read()
                            col_dl1.download_button(
                                f"📥 Télécharger JSON {new_year}",
                                final_json,
                                f"cis_{new_year}.json",
                                "application/json"
                            )

                            # Bouton Excel
                            if success_xls:
                                with open(p_excel, "rb") as f:
                                    final_xls = f.read()
                                col_dl2.download_button(
                                    f"📥 Télécharger Excel {new_year}",
                                    final_xls,
                                    f"cis_{new_year}.xlsx",
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )

                    except Exception as e:
                        st.error(f"Erreur : {e}")

                    finally:
                        # Nettoyage sécurisé
                        for p in [p_src, p_res, p_out, p_excel]:
                            if p and os.path.exists(p): os.remove(p)
                        if p_pdf_temp and os.path.exists(p_pdf_temp) and p_pdf_temp != p_src:
                            os.remove(p_pdf_temp)


if __name__ == "__main__":
    main()