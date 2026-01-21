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


@st.cache_data(show_spinner=False)
def get_cached_extraction(file_content, file_name):
    virtual_file = io.BytesIO(file_content)
    virtual_file.name = file_name
    return analyser_pdf_cis(virtual_file)


def process_file_wrapper(uploaded_file):
    return get_cached_extraction(uploaded_file.getvalue(), uploaded_file.name)


# --- 5. LOGIQUE UPDATER (Backend) ---

def run_dynamic_update(source_path, summary_path, output_path, old_year, new_year):
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

    for rule in source_items:
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
                    with st.spinner("Analyse..."):
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            f1 = executor.submit(process_file_wrapper, file1)
                            f2 = executor.submit(process_file_wrapper, file2)
                            d1 = f1.result()
                            d2 = f2.result()

                        if d1 and d2:
                            st.session_state.comparison_data = compare_data_adapter(d1, d2)
                            st.success("Terminé !")
                        else:
                            st.error("Erreur extraction PDF.")

        elif len(uploaded_files) == 1:
            file1 = uploaded_files[0]
            st.info(f"📄 Extraction : **{file1.name}**")
            if st.button("🚀 LANCER L'EXTRACTION", type="primary"):
                with st.spinner("Extraction..."):
                    data = process_file_wrapper(file1)
                    if data:
                        st.session_state.comparison_data = {"single_mode": True, "data": data}
                        st.success("Réussi !")

        if st.session_state.comparison_data:
            res = st.session_state.comparison_data

            if res.get("single_mode"):
                data = res["data"]
                st.divider()
                c1, c2 = st.columns([1, 3])
                c1.metric("Règles", len(data))
                c2.download_button("📥 Télécharger JSON", json.dumps(data, indent=4, ensure_ascii=False),
                                   "cis_export.json", "application/json")
                with st.expander("Voir les règles extraites"):
                    st.json(data[:5])
            else:
                stats = res.get('stats', {})
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

                tab_add, tab_rem, tab_mod = st.tabs(["Ajouts", "Suppressions", "Modifications"])
                with tab_add:
                    for r in res.get('added', []):
                        with st.expander(f"➕ [{r.get('control_id')}]"): st.json(r)
                with tab_rem:
                    for r in res.get('removed', []):
                        with st.expander(f"➖ [{r.get('control_id')}]"): st.json(r)
                with tab_mod:
                    for item in res.get('modified', []):
                        title = clean_text(item.get('new', {}).get('title'))
                        with st.expander(f"📝 [{item.get('control_id')}] {title}"):
                            for field, vals in item.get('changes', {}).items():
                                st.markdown(f"**{field}**")
                                ca, cb = st.columns(2)
                                ca.caption("Avant");
                                ca.text(clean_text(vals.get('old')))
                                cb.caption("Après");
                                cb.text(clean_text(vals.get('new')))

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
                    with st.spinner(f"Traitement {old_year} ➔ {new_year}..."):
                        p_src = None;
                        p_res = None;
                        p_out = None;
                        p_excel = None;
                        p_pdf_temp = None

                        try:
                            # 1. Gestion Source (Conversion PDF si besoin)
                            if src_file.type == "application/pdf":
                                with st.status("Conversion du PDF en cours..."):
                                    pdf_data = get_cached_extraction(src_file.getvalue(), src_file.name)
                                    if not pdf_data:
                                        st.error("Echec extraction PDF.");
                                        st.stop()

                                    fd, p_pdf_temp = tempfile.mkstemp(suffix=".json")
                                    os.close(fd)
                                    with open(p_pdf_temp, "w", encoding="utf-8") as f:
                                        json.dump(pdf_data, f, indent=4)
                                    p_src = p_pdf_temp
                            else:
                                p_src = save_uploaded_file_temp(src_file)

                            # 2. Gestion Résumé et Output
                            p_res = save_uploaded_file_temp(res_file)
                            fd, p_out = tempfile.mkstemp(suffix=".json")
                            os.close(fd)

                            # Fichier Excel temporaire
                            fd_xls, p_excel = tempfile.mkstemp(suffix=".xlsx")
                            os.close(fd_xls)

                            # 3. Exécution UPDATE (JSON -> JSON)
                            if p_src and p_res:
                                stats = run_dynamic_update(p_src, p_res, p_out, old_year, new_year)

                                st.balloons()
                                st.success("✅ Mise à jour JSON terminée !")

                                # 4. Exécution CONVERSION EXCEL (JSON Final -> Excel)
                                # On utilise uniquement le JSON de sortie (p_out)
                                success_xls, msg_xls = convert_json_to_excel(p_out, p_excel)

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