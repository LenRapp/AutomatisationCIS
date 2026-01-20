import streamlit as st
from src.extraction import analyser_pdf_cis

# --- ADAPTATEUR BACKEND (PONT ENTRE UI ET LOGIC) ---
try:
    from src.comparator import compare_rules
    
    def compare_data_adapter(data1, data2):
        """
        Adapte la sortie de compare_rules (format collègue)
        au format attendu par l'interface actuelle.
        """
        # 1. Appel de la fonction du collègue
        raw = compare_rules(data1, data2)
        
        # 2. Transformation pour l'UI
        # L'UI attend : {'added': [...], 'removed': [...], 'modified': [{'old':..., 'new':...}]}
        # Le collègue renvoie : {'added': [...], 'deleted': [...], 'modified': [{'changes':...}]}
        
        adapted_modified = []
        for mod in raw.get('modified', []):
            # On essaie de reconstruire un objet old/new simpliste pour l'affichage
            changes = mod.get('changes', {})
            
            # Extraction intelligente des valeurs (si pas de changement, on met "Inchangé")
            old_sev = changes.get('severity', {}).get('old', 'Inchangé')
            new_sev = changes.get('severity', {}).get('new', 'Inchangé')
            
            old_title = changes.get('title', {}).get('old', 'Inchangé')
            new_title = changes.get('title', {}).get('new', mod.get('control_id')) # Fallback sur l'ID si titre inchangé

            # On crée des objets fictifs pour l'affichage
            old_fake = {'severity': old_sev, 'title': old_title}
            new_fake = {'severity': new_sev, 'title': new_title}
            
            adapted_modified.append({
                "control_id": mod.get('control_id'),
                "old": old_fake,
                "new": new_fake,
                "changes": changes # On passe les vrais changements à l'UI
            })
            
        return {
            "added": raw.get('added', []),
            "removed": raw.get('deleted', []), # Mapping deleted -> removed
            "modified": adapted_modified,
            "stats": {
                "count1": len(data1),
                "count2": len(data2),
                "added_count": len(raw.get('added', [])),
                "removed_count": len(raw.get('deleted', [])),
                "modified_count": len(raw.get('modified', []))
            }
        }
        
    # On utilise l'adaptateur comme fonction principale
    compare_data = compare_data_adapter

except ImportError:
    compare_data = None


import json
import concurrent.futures

st.set_page_config(page_title="Comparateur CIS", page_icon="⚡", layout="wide")

if 'comparison_data' not in st.session_state:
    st.session_state.comparison_data = None

# OPTIMISATION : Mise en cache de l'extraction
# Streamlit ne relancera pas la fonction si le contenu du fichier (les octets) n'a pas changé.
@st.cache_data(show_spinner=False)
def get_cached_extraction(file_content, file_name):
    """
    Fonction wrapper pour mettre en cache le résultat de l'extraction.
    On passe le contenu en bytes car l'objet file_uploader n'est pas stable pour le cache.
    """
    import io
    # On recrée un fichier virtuel en mémoire pour pdfplumber
    virtual_file = io.BytesIO(file_content)
    virtual_file.name = file_name
    return analyser_pdf_cis(virtual_file)

def process_file_wrapper(uploaded_file):
    """Prépare les données pour la fonction mise en cache."""
    # On lit les bytes une fois pour toutes
    bytes_data = uploaded_file.getvalue()
    return get_cached_extraction(bytes_data, uploaded_file.name)

def main():
    st.title("⚡ Comparateur CIS - Interface UI")
    
    def clean_text(text):
        """Nettoie le texte pour l'affichage (supprime les sauts de ligne et espaces superflus)."""
        if not isinstance(text, str):
            return str(text)
        # Remplace les retours à la ligne par des espaces et réduit les espaces multiples
        cleaned = " ".join(text.split())
        return cleaned

    def clear_state():
        st.session_state.comparison_data = None

    # 1. ZONE UPLOAD (Unique et Multi-fichiers)
    uploaded_files = st.file_uploader(
        "Déposez vos fichiers PDF CIS (1 pour extraction, 2 pour comparaison)", 
        type="pdf", 
        accept_multiple_files=True, 
        on_change=clear_state
    )

    # LOGIQUE DE DECISION DES MODES
    if len(uploaded_files) == 2:
        file1, file2 = uploaded_files
        st.info(f"🚀 Mode Comparaison prêt : **{file1.name}** vs **{file2.name}**")
        
        if st.button("🚀 LANCER LA COMPARAISON", type="primary"):
            if compare_data is None:
                st.error("Module de comparaison introuvable dans src/comparator.py (vérifiez le nom de la fonction)")
                return

            with st.spinner("Analyse différentielle en cours..."):
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    f1 = executor.submit(process_file_wrapper, file1)
                    f2 = executor.submit(process_file_wrapper, file2)
                    data1 = f1.result()
                    data2 = f2.result()
                
                if data1 and data2:
                    st.session_state.comparison_data = compare_data(data1, data2)
                    st.success("Comparaison terminée !")
                else:
                    st.error("Erreur lors de l'extraction des PDF.")

    elif len(uploaded_files) == 1:
        file1 = uploaded_files[0]
        st.info(f"📄 Mode Extraction Simple : **{file1.name}**")
        
        if st.button("🚀 LANCER L'EXTRACTION", type="primary"):
            with st.spinner("Extraction des règles..."):
                data = process_file_wrapper(file1)
                if data:
                    st.session_state.comparison_data = {"single_mode": True, "data": data}
                    st.success("Extraction réussie !")
                else:
                    st.error("Aucune donnée extraite.")

    elif len(uploaded_files) > 2:
        st.warning("⚠️ Pour faire la comparaison, il faut exactement deux fichiers (veuillez en retirer).")

    # 2. RENDU VISUEL (VOTRE INTERFACE)
    if st.session_state.comparison_data:
        res = st.session_state.comparison_data
        
        # --- RENDU EXTRACTION SIMPLE (Original) ---
        if res.get("single_mode"):
            data = res["data"]
            st.divider()
            c1, c2 = st.columns([1, 3])
            c1.metric("Règles", len(data))
            json_str = json.dumps(data, indent=4, ensure_ascii=False)
            c2.download_button("📥 Télécharger JSON", json_str, "cis_export.json", "application/json")
            
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

        # --- RENDU COMPARAISON (Différentiel) ---
        else:
            stats = res.get('stats', {})
            st.divider()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Ancien", stats.get('count1', 0))
            m2.metric("Nouveau", stats.get('count2', 0), delta=stats.get('count2', 0)-stats.get('count1', 0))
            m3.metric("Ajouts", stats.get('added_count', 0))
            m4.metric("Suppressions", stats.get('removed_count', 0), delta_color="inverse")
            
            st.divider()
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
                    # Récupération des changements détaillés
                    changes = item.get('changes', {})
                    # Titre dynamique (indique le nombre de champs touchés)
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

if __name__ == "__main__":
    main()
