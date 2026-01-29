import streamlit as st
import json
import os
import tempfile
import io
import pandas as pd

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
    from src.updater import load_json_file, save_json_file, update_year_in_text, run_dynamic_update
    
    run_updater = run_dynamic_update
    UPDATER_AVAILABLE = True
except ImportError:
    load_json_file = None
    save_json_file = None
    update_year_in_text = None
    run_dynamic_update = None
    run_updater = None
    UPDATER_AVAILABLE = False

st.set_page_config(page_title="Automatisation CIS", page_icon="🛡️", layout="wide")


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
    """Convertit le fichier JSON final en fichier Excel soigné avec XlsxWriter."""
    try:
        # Lecture du JSON généré
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Normalisation
        items = data if isinstance(data, list) else data.get('items', [])

        if not items:
            return False, "Le JSON est vide."

        # Création DataFrame Pandas
        df = pd.DataFrame(items)

        # Réorganisation des colonnes
        priority_cols = ['control_id', 'title', 'severity', 'description', 'rationale', 'impact', 'remediation']
        cols = [c for c in priority_cols if c in df.columns] + [c for c in df.columns if c not in priority_cols]
        df = df[cols]

        # Export Excel avec XlsxWriter pour le formatage
        with pd.ExcelWriter(excel_path, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Benchmark')
            
            workbook = writer.book
            worksheet = writer.sheets['Benchmark']
            
            # Définition des formats
            header_fmt = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#4F81BD',
                'font_color': 'white',
                'border': 1
            })
            
            text_fmt = workbook.add_format({
                'text_wrap': True,
                'valign': 'top',
                'border': 1
            })
            
            # Formatage des colonnes
            for col_num, value in enumerate(df.columns.values):
                # Écriture de l'en-tête stylisé
                worksheet.write(0, col_num, value, header_fmt)
                
                # Définition de la largeur selon la colonne
                if value in ['control_id', 'severity', 'cis_benchmark_version']:
                    width = 15
                elif value == 'title':
                    width = 40
                elif value in ['description', 'rationale', 'impact', 'remediation']:
                    width = 60
                elif value in ['audit', 'check', 'verification']:  # <--- Audit plus large
                    width = 80
                else:
                    width = 25
                
                # Application de la largeur et du format de cellule
                worksheet.set_column(col_num, col_num, width, text_fmt)
            
            # Figer la première ligne (volets)
            worksheet.freeze_panes(1, 0)

        return True, "Succès"
    except Exception as e:
        return False, str(e)


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


def main():
    st.title("🛡️ Automatisation & Maintenance CIS")

    mode = st.sidebar.radio(
        "Navigation",
        ("📄 Analyse PDF (Extraction/Comparaison)", "🔄 Générateur de Benchmark (Mise à jour)")
    )

    st.sidebar.divider()

    #ANALYSE PDF
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
                #On s'assure que l'ordre est correct (par ID)
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
                    "📥 Télécharger le Résumé (pour Mise à jour)",
                    json.dumps(res, indent=4),  # Juste "res", PAS "res['modified']"
                    "resume_complet.json",
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

    # GÉNÉRATEUR BENCHMARK (JSON + EXCEL)
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
                if not UPDATER_AVAILABLE or not run_updater:
                    st.error("Module src/updater.py manquant ou corrompu.")
                else:
                    prog_update = st.progress(0, text="Démarrage du processus...")
                    
                    p_src = None; p_res = None; p_out = None; p_excel = None; p_pdf_temp = None

                    try:
                        #25% -> 50%
                        prog_update.progress(25, text="25% - Analyse du fichier source...")

                        def update_p_src(p):
                            # p est entre 0.0 et 1.0, on le mappe sur l'intervalle 25-50%
                            current = 25 + int(p * 25)
                            prog_update.progress(current, text=f"{current}% - Analyse du fichier source ({int(p*100)}%)...")

                        if src_file.type == "application/pdf":
                            pdf_data = get_cached_extraction(src_file.getvalue(), src_file.name, _progress_callback=update_p_src)
                            if not pdf_data:
                                st.error("Echec extraction PDF."); st.stop()

                            fd, p_pdf_temp = tempfile.mkstemp(suffix=".json")
                            os.close(fd)
                            with open(p_pdf_temp, "w", encoding="utf-8") as f:
                                json.dump(pdf_data, f, indent=4)
                            p_src = p_pdf_temp
                        else:
                            p_src = save_uploaded_file_temp(src_file)

                        #50%
                        prog_update.progress(50, text="50% - Préparation du fichier résumé...")
                        p_res = save_uploaded_file_temp(res_file)
                        fd, p_out = tempfile.mkstemp(suffix=".json")
                        os.close(fd)
                        fd_xls, p_excel = tempfile.mkstemp(suffix=".xlsx")
                        os.close(fd_xls)

                        # 75%
                        if p_src and p_res:
                            def update_p_upd(p):
                                # 75% -> 95%
                                current = 50 + int(p * 45) # Progression de 50 à 95%
                                prog_update.progress(current, text=f"{current}% - Application des mises à jour ({int(p*100)}%)...")

                            stats = run_updater(
                                source_path=p_src, 
                                summary_path=p_res, 
                                output_json=p_out, 
                                old_year=old_year, 
                                new_year=new_year, 
                                progress_callback=update_p_upd
                            )
                            
                            # Conversion Excel
                            prog_update.progress(95, text="95% - Conversion Excel...")
                            success_xls, msg_xls = convert_json_to_excel(p_out, p_excel)

                            # 100%
                            prog_update.progress(100, text="100% - Terminé !")
                            st.balloons()
                            st.success("✅ Processus terminé avec succès !")
                            prog_update.empty()

                            if success_xls:
                                st.info("📊 Conversion Excel effectuée automatiquement.")
                            else:
                                st.warning(f"⚠️ Échec conversion Excel : {msg_xls}")
                            
                            st.subheader("Statistiques de la mise à jour")
                            k1, k2, k3, k4 = st.columns(4)
                            k1.metric("✅ Ajoutées", stats.get('added', 0))
                            k2.metric("❌ Supprimées", stats.get('deleted', 0))
                            k3.metric("✏️ Mises à jour", stats.get('updated', 0))
                            k4.metric("📅 Rempl. Année", stats.get('year_replaced', 0))


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