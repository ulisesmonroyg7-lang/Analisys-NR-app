# app.py (FINAL VERSION - All 3 Tabs, Consolidated Export, All Bugs Fixed, No Omissions)
import streamlit as st
import pandas as pd
from pathlib import Path
import io

# Importar toda la lógica de negocio reutilizada
from utils.excel_handler import ExcelHandler
from utils.gemini_client import GeminiChat, create_dossier_prompt_for_success, create_summary_prompt_for_batch, create_failure_analysis_prompt
from core.data_processor import DataProcessor
from core.circulating_processor import CirculatingSystemsDataProcessor
from core.grease_calculator import GreaseCalculator
from core.rule_engine import RuleEngine

# --- 1. Page Configuration ---
st.set_page_config(page_title="NORIA Analysis Tool", layout="wide", initial_sidebar_state="expanded")

# --- 2. App Title ---
st.title("NORIA Analysis Tool - Multi-Analysis Platform")
st.markdown("A comprehensive lubrication analysis platform for breather selection and grease analysis.")

# --- Helper Functions ---
def to_excel_multifile(sheets_data: dict):
    output = io.BytesIO()
    with st.spinner('Generating Consolidated Excel Report...'):
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            for sheet_name, df in sheets_data.items():
                if not df.empty:
                    df.to_excel(writer, index=False, sheet_name=sheet_name)
    return output.getvalue()

def clear_all_state():
    """Resets the entire application state to its default."""
    preserve_keys = ['excel_handler', 'default_catalog_message']
    for key in list(st.session_state.keys()):
        if key not in preserve_keys:
            del st.session_state[key]
    
    st.session_state.data_loaded = False
    st.session_state.file_name = ""
    st.session_state.data_report_df = pd.DataFrame()
    st.session_state.splash_df = pd.DataFrame()
    st.session_state.splash_results = None
    st.session_state.splash_overrides = {}
    st.session_state.circulating_df = pd.DataFrame()
    st.session_state.circulating_results = None
    st.session_state.circulating_overrides = {}
    st.session_state.grease_df = pd.DataFrame()
    st.session_state.grease_results = None
    st.session_state.show_gpm_summary = False
    st.session_state.gpm_summary_data = {}
    
    st.session_state.global_config = {'max_amb_temp': 80.0, 'min_amb_temp': 60.0, 'mobile_application': False, 'high_particle_removal': False, 'esi_manual': None, 'safety_factor': 1.4, 'verbose_trace': False, 'include_calculations': False, 'gemini_api_key': '', 'enable_manual_gpm': False, 'manual_gpm_override': 0.0}
    try:
        if st.session_state.excel_handler.load_breather_catalog("data/breathers_catalog.xlsx"):
            st.session_state.catalog_loaded = True
    except Exception:
        st.session_state.catalog_loaded = False

# --- 3. Session State Initialization ---
if 'excel_handler' not in st.session_state:
    st.session_state.excel_handler = ExcelHandler()
    try:
        if st.session_state.excel_handler.load_breather_catalog("data/breathers_catalog.xlsx"):
            st.session_state.default_catalog_message = f"✓ Default catalog loaded ({len(st.session_state.excel_handler.get_breather_catalog())} models)"
        else: st.session_state.default_catalog_message = "Default catalog not found."
    except Exception: st.session_state.default_catalog_message = "Error loading default catalog."
    clear_all_state()

# --- 4. Sidebar ---
with st.sidebar:
    st.header("Data Source")
    uploaded_report = st.file_uploader("Upload Data Report...", type=["xlsx", "xls"], key="report_uploader")
    uploaded_catalog = st.file_uploader("Upload Breather Catalog (Optional Override)...", type=["xlsx", "xls"], key="catalog_uploader")
    st.markdown("---")
    if st.button("🗑️ Clear All Data & Reset App", use_container_width=True, type="secondary"):
        clear_all_state()
        st.rerun()
    new_file_uploaded = False
    if uploaded_report is not None and st.session_state.get('file_name', '') != uploaded_report.name:
        try:
            success, error_msg = st.session_state.excel_handler.load_data_report(uploaded_report)
            if success:
                st.session_state.data_report_df = st.session_state.excel_handler.get_all_data()
                st.session_state.data_loaded = True
                st.session_state.file_name = uploaded_report.name
                new_file_uploaded = True
            else:
                st.error(f"Load error: {error_msg}")
        except Exception as e: st.error(f"An unexpected error occurred: {e}")
    if uploaded_catalog is not None:
        try:
            if st.session_state.excel_handler.load_breather_catalog(uploaded_catalog):
                st.session_state.catalog_loaded = True
                st.session_state.default_catalog_message = f"✓ Custom catalog loaded"
        except Exception as e: st.error(f"Error reading custom catalog: {e}")
            
    st.markdown("---")
    if st.session_state.data_loaded: st.success(f"✓ {st.session_state.file_name}\n({len(st.session_state.data_report_df)} records)")
    else: st.info("Waiting for Data Report...")
    if st.session_state.get('catalog_loaded', False): st.success(st.session_state.default_catalog_message)
    else: st.warning(st.session_state.default_catalog_message)
    
    st.markdown("---")
    st.header("Export Results")
    splash_ready = st.session_state.get('splash_results') is not None
    circ_ready = st.session_state.get('circulating_results') is not None
    grease_ready = st.session_state.get('grease_results') is not None
    st.markdown(f"{'✅' if splash_ready else '⚪'} Splash / Oil Bath")
    st.markdown(f"{'✅' if circ_ready else '⚪'} Circulating Systems")
    st.markdown(f"{'✅' if grease_ready else '⚪'} Bearing Grease")
    if splash_ready or circ_ready or grease_ready:
        sheets_to_export = {}
        if splash_ready:
            processor = DataProcessor(st.session_state.excel_handler, st.session_state.splash_df, st.session_state.global_config, st.session_state.splash_overrides)
            processor.results = st.session_state.splash_results
            results_df = processor.get_results_as_dataframe()
            sheets_to_export['Splash_Results'] = st.session_state.excel_handler.merge_results_with_original(results_df)
        if circ_ready:
            circ_processor = CirculatingSystemsDataProcessor(st.session_state.excel_handler, st.session_state.global_config, st.session_state.circulating_overrides)
            circ_processor.results = st.session_state.circulating_results
            circ_results_df = circ_processor.get_results_as_dataframe()
            sheets_to_export['Circulating_Results'] = st.session_state.excel_handler.merge_results_with_original(circ_results_df)
        if grease_ready:
            grease_results_list = []
            for index, res in st.session_state.grease_results.items():
                row_data = {'original_index': index, **res}
                grease_results_list.append(row_data)
            grease_results_df = pd.DataFrame(grease_results_list)
            sheets_to_export['Grease_Results'] = st.session_state.excel_handler.merge_results_with_original(grease_results_df)
        excel_data = to_excel_multifile(sheets_to_export)
        st.download_button(label="💾 Download Full Analysis Report", data=excel_data, file_name=f"Full_Analysis_Report_{st.session_state.file_name}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")
    else:
        st.info("Process at least one analysis to enable export.")

# --- 5. Centralized Data Filtering ---
if st.session_state.data_loaded and (new_file_uploaded or st.session_state.splash_df.empty):
    if new_file_uploaded:
        st.session_state.splash_results = None; st.session_state.splash_overrides = {}
        st.session_state.circulating_results = None; st.session_state.circulating_overrides = {}
        st.session_state.grease_results = None
    
    all_data = st.session_state.data_report_df
    splash_types = ['Gearbox Housing (Oil)', 'Bearing (Oil)', 'Pump (Oil)', 'Electric Motor Bearing (Oil)', 'Blower (Oil)']
    mask_splash = all_data.iloc[:, 8].astype(str).str.strip().isin(splash_types)
    st.session_state.splash_df = all_data[mask_splash].copy()
    circ_types = ['Circulating System Reservoir (Oil)', 'Hydraulic System Reservoir (Oil)']
    mask_circ = all_data.iloc[:, 8].astype(str).str.strip().isin(circ_types)
    st.session_state.circulating_df = all_data[mask_circ].copy()
    grease_types = ['Bearing (Grease)', 'Bushing (Grease)', 'Electric Motor (Grease)']
    mask_grease = all_data.iloc[:, 8].astype(str).str.strip().isin(grease_types)
    st.session_state.grease_df = all_data[mask_grease].copy()

# --- 6. Main Tabs Creation ---
splash_tab, circulating_tab, grease_tab = st.tabs(["Splash/Oil Bath Breathers", "Circulating System Breathers", "Bearing Grease Analysis"])

# --- 7. Dialog Functions ---
@st.dialog("Advanced Configuration")
def advanced_config_dialog():
    st.markdown("Set detailed parameters for the analysis.")
    config = st.session_state.global_config.copy()
    general_tab, temp_tab, env_tab, advanced_tab = st.tabs(["General", "Temperature", "Environment", "Advanced"])
    with general_tab: config['mobile_application'] = st.toggle("This is a Mobile Application", value=config.get('mobile_application', False))
    with temp_tab:
        st.markdown("Set the ambient temperature range for your facility (°F).")
        config['min_amb_temp'] = st.number_input("Minimum Ambient Temperature (°F)", value=float(config.get('min_amb_temp', 60.0)), step=1.0)
        config['max_amb_temp'] = st.number_input("Maximum Ambient Temperature (°F)", value=float(config.get('max_amb_temp', 80.0)), step=1.0)
    with env_tab:
        config['high_particle_removal'] = st.toggle("Force high particle removal", value=config.get('high_particle_removal', False))
        esi_options = ["Auto", "Disposable", "Rebuildable"]; current_esi = config.get('esi_manual') or "Auto"
        config['esi_manual'] = st.radio("Extended Service Override", options=esi_options, index=esi_options.index(current_esi))
    with advanced_tab:
        st.subheader("Manual Overrides (Circulating Systems Only)")
        config['enable_manual_gpm'] = st.toggle("Manually override GPM flow rate", value=config.get('enable_manual_gpm', False))
        config['manual_gpm_override'] = st.number_input("Flow Rate (GPM)", value=float(config.get('manual_gpm_override', 0.0)), min_value=0.0, step=0.5, disabled=not config['enable_manual_gpm'])
        st.markdown("---")
        st.subheader("CFM Calculation")
        config['safety_factor'] = st.slider("Safety Factor", 1.0, 2.0, float(config.get('safety_factor', 1.4)), 0.1)
        st.markdown("---")
        st.subheader("AI & Debugging")
        config['gemini_api_key'] = st.text_input("Gemini API Key", type="password", value=config.get('gemini_api_key', ''))
        config['verbose_trace'] = st.checkbox("Include verbose rule trace in output", value=config.get('verbose_trace', False))
        config['include_calculations'] = st.checkbox("Include intermediate calculations in output", value=config.get('include_calculations', False))
    if st.button("Save Configuration", type="primary"):
        if config['max_amb_temp'] <= config['min_amb_temp']: st.error("Maximum temperature must be greater than minimum.")
        else: st.session_state.global_config = config; st.rerun()

@st.dialog("Batch Edit Configuration")
def batch_config_dialog(selected_indices, override_key, df_key, is_circulating=False):
    st.markdown(f"Apply changes to **{len(selected_indices)} selected assets**.")
    config_changes = {}; df_changes = {}
    with st.container(border=True):
        if st.checkbox("Change Criticality"):
            config_changes['criticality'] = st.selectbox("New Criticality", ["A", "B1", "B2", "C"])
    with st.container(border=True):
        if st.checkbox("Change Mobile Status"):
            config_changes['mobile_application'] = st.toggle("Is Mobile Application", key="batch_mobile")
    with st.container(border=True):
        if st.checkbox("Change Operating Temperature"):
            df_changes['(D) Operating Temperature'] = st.text_input("New Operating Temperature (e.g., '120°F - 140°F')")
    if is_circulating:
        with st.container(border=True):
            if st.checkbox("Set Manual GPM Override"):
                config_changes['enable_manual_gpm'] = True
                config_changes['manual_gpm_override'] = st.number_input("New Flow Rate (GPM)", min_value=0.0, step=0.5, key="batch_gpm_value")
    if st.button("Apply Changes", type="primary"):
        if config_changes:
            for index in selected_indices:
                if index not in st.session_state[override_key]: st.session_state[override_key][index] = {}
                st.session_state[override_key][index].update(config_changes)
        if df_changes:
            for index in selected_indices:
                for col, value in df_changes.items():
                    if value: st.session_state[df_key].loc[index, col] = value
        st.rerun()

@st.dialog("Flow Rate Data Analysis")
def gpm_summary_dialog(summary):
    st.markdown("Analysis of available flow rate data for your circulating systems.")
    st.metric("Total Circulating Records", summary['total_records'])
    st.metric("Records with Cross-Reference Flow", summary.get('with_cross_reference', 0))
    st.metric("Records Requiring GPM Estimation", summary['with_estimation'])
    st.markdown("**Methodology:** CFM is calculated from GPM (`CFM = (GPM / 7.48) * 1.4`).")
    st.info("The system cross-references pump siblings for accurate flow. If none are found, it estimates GPM based on oil capacity.")
    col1, col2 = st.columns(2)
    if col1.button("✅ Continue with Analysis", type="primary"):
        st.session_state.run_circulating_analysis = True; st.session_state.show_gpm_summary = False; st.rerun()
    if col2.button("Cancel"):
        st.session_state.show_gpm_summary = False; st.rerun()

# --- 8. Splash/Oil Bath Tab Content ---
with splash_tab:
    st.header("Splash/Oil Bath Breather Analysis")
    if not st.session_state.data_loaded or not st.session_state.get('catalog_loaded'): st.warning("Please upload files to begin.")
    elif st.session_state.splash_df.empty: st.info("No applicable records found.")
    else:
        st.subheader("Configuration & Actions")
        col1, col2, col3 = st.columns(3);
        with col1: criticality = st.selectbox("Global Criticality", ["A", "B1", "B2", "C"], key="splash_criticality")
        with col2: brand_filter = st.selectbox("Brand Filter", ["All Brands", "Des-Case", "Air Sentry"], key="splash_brand_filter")
        with col3:
            if st.button("Advanced...", key="splash_adv_btn"):
                advanced_config_dialog()
        st.markdown("---")
        if st.button("🚀 Process Analysis", type="primary", key="splash_process_btn"):
            current_config = {**st.session_state.global_config, 'criticality': criticality, 'brand_filter': brand_filter}
            with st.spinner("Processing..."):
                processor = DataProcessor(st.session_state.excel_handler, st.session_state.splash_df, current_config, st.session_state.splash_overrides)
                st.session_state.splash_results = processor.process_all_records()
                st.success("Analysis complete!")
                st.rerun()
        st.subheader("Analysis Table")
        def get_splash_display_df():
            df = st.session_state.splash_df.copy()
            crit_val = st.session_state.get('splash_criticality', 'A')
            df['Config_Criticality'] = df.index.map(lambda i: st.session_state.splash_overrides.get(i, {}).get('criticality', crit_val))
            df['Operating_Temp'] = df['(D) Operating Temperature']
            if st.session_state.get('splash_results'):
                res = st.session_state.splash_results
                df['Result_Model'] = df.index.map(lambda i: res.get(i, {}).get('selected_breather', [{}])[0].get('Model', 'No Solution') if res.get(i, {}).get('selected_breather') else 'No Solution')
                df['Result_CFM_Req'] = df.index.map(lambda i: f"{res.get(i, {}).get('thermal_analysis', {}).get('cfm_required', 0):.2f}")
                df['Result_Notes'] = df.index.map(lambda i: res.get(i, {}).get('installation_notes', ''))
            return df
        splash_display_df = get_splash_display_df()
        m_col = splash_display_df.columns[1] if len(splash_display_df.columns) > 1 else 'Machine'
        c_col = splash_display_df.columns[2] if len(splash_display_df.columns) > 2 else 'Component'
        cols_to_show = [m_col, c_col, 'Config_Criticality', 'Operating_Temp']
        if st.session_state.get('splash_results'): cols_to_show.extend(['Result_Model', 'Result_CFM_Req', 'Result_Notes'])
        st.dataframe(splash_display_df[cols_to_show], use_container_width=True, hide_index=True)
        st.markdown("---")
        st.subheader("Edit Asset Configurations")
        splash_asset_options = [f"{row[m_col]} - {row[c_col]} (ID: {index})" for index, row in splash_display_df.iterrows()]
        splash_selected_assets = st.multiselect("Select assets to edit:", options=splash_asset_options, placeholder="Choose one or more assets", key="splash_multiselect")
        if splash_selected_assets:
            splash_selected_indices = [int(asset.split('(ID: ')[1][:-1]) for asset in splash_selected_assets]
            if st.button(f"Edit {len(splash_selected_indices)} Selected...", type="secondary", key="splash_edit_btn"):
                batch_config_dialog(splash_selected_indices, "splash_overrides", "splash_df")

# --- 9. Circulating Systems Tab Content ---
with circulating_tab:
    st.header("Circulating System Breather Analysis")
    if not st.session_state.data_loaded or not st.session_state.catalog_loaded:
        st.warning("Please upload a Data Report and ensure a Breather Catalog is loaded to begin.")
    elif st.session_state.circulating_df.empty:
        st.info("No applicable records for this analysis were found in the uploaded report.")
    else:
        st.subheader("Configuration & Actions")
        col1, col2, col3 = st.columns(3)
        with col1: criticality_circ = st.selectbox("Global Criticality", ["A", "B1", "B2", "C"], key="circ_criticality")
        with col2: brand_filter_circ = st.selectbox("Brand Filter", ["All Brands", "Des-Case", "Air Sentry"], key="circ_brand_filter")
        with col3:
            if st.button("Advanced...", key="circ_adv_btn"):
                advanced_config_dialog()
        st.markdown("---")
        if st.button("🚀 Process Analysis", type="primary", key="circ_process_btn"):
            with st.spinner("Analyzing flow data..."):
                temp_proc = CirculatingSystemsDataProcessor(st.session_state.excel_handler, {}, {})
                summary = temp_proc.analyze_flow_data_availability(st.session_state.circulating_df)
                st.session_state.gpm_summary_data = summary
                st.session_state.show_gpm_summary = True
                st.rerun()
        if st.session_state.get('show_gpm_summary'):
            gpm_summary_dialog(st.session_state.gpm_summary_data)
        if st.session_state.get('run_circulating_analysis'):
            with st.spinner("Processing..."):
                current_config = {**st.session_state.global_config, 'criticality': criticality_circ, 'brand_filter': brand_filter_circ}
                processor = CirculatingSystemsDataProcessor(st.session_state.excel_handler, current_config, st.session_state.circulating_overrides)
                st.session_state.circulating_results = processor.process_all_records(st.session_state.circulating_df)
                st.success("Analysis complete!")
            st.session_state.run_circulating_analysis = False
            st.rerun()
        st.subheader("Analysis Table")
        def get_circ_display_df():
            df = st.session_state.circulating_df.copy()
            crit_val = st.session_state.get('circ_criticality', 'A')
            df['Config_Criticality'] = df.index.map(lambda i: st.session_state.circulating_overrides.get(i, {}).get('criticality', crit_val))
            df['GPM_Source_Override'] = df.index.map(lambda i: f"Manual: {st.session_state.circulating_overrides.get(i, {}).get('manual_gpm_override')} GPM" if st.session_state.circulating_overrides.get(i, {}).get('enable_manual_gpm') else None)
            df['Operating_Temp'] = df['(D) Operating Temperature']
            if st.session_state.get('circulating_results'):
                res = st.session_state.circulating_results
                df['Result_Model'] = df.index.map(lambda i: res.get(i, {}).get('selected_breather', [{}])[0].get('Model', 'No Solution') if res.get(i, {}).get('selected_breather') else 'No Solution')
                df['LCC_Model'] = df.index.map(lambda i: (res.get(i, {}).get('lcc_breather') or {}).get('Model', '-'))
                df['Cost_Benefit_Model'] = df.index.map(lambda i: (res.get(i, {}).get('cost_benefit_breather') or {}).get('Model', '-'))
                df['Flow_Rate_GPM'] = df.index.map(lambda i: f"{res.get(i, {}).get('flow_analysis', {}).get('total_flow', 0):.1f}")
                df['GPM_Source'] = df.index.map(lambda i: res.get(i, {}).get('flow_analysis', {}).get('calculation_method', 'N/A'))
            return df
        circ_display_df = get_circ_display_df()
        m_col_c = circ_display_df.columns[1] if len(circ_display_df.columns) > 1 else 'Machine'
        c_col_c = circ_display_df.columns[2] if len(circ_display_df.columns) > 2 else 'Component'
        columns_to_show_circ = [m_col_c, c_col_c, 'Config_Criticality', 'Operating_Temp']
        if st.session_state.get('circulating_results'):
            columns_to_show_circ.extend(['Result_Model', 'LCC_Model', 'Cost_Benefit_Model', 'Flow_Rate_GPM', 'GPM_Source'])
        else:
            columns_to_show_circ.append('GPM_Source_Override')
        st.dataframe(circ_display_df[columns_to_show_circ], use_container_width=True, hide_index=True)
        st.markdown("---")
        st.subheader("Edit Asset Configurations")
        circ_asset_options = [f"{row[m_col_c]} - {row[c_col_c]} (ID: {index})" for index, row in circ_display_df.iterrows()]
        circ_selected_assets = st.multiselect("Select assets to edit:", options=circ_asset_options, placeholder="Choose one or more assets", key="circ_multiselect")
        if circ_selected_assets:
            circ_selected_indices = [int(asset.split('(ID: ')[1][:-1]) for asset in circ_selected_assets]
            if st.button(f"Edit {len(circ_selected_indices)} Selected...", type="secondary", key="circ_edit_btn"):
                batch_config_dialog(circ_selected_indices, "circulating_overrides", "circulating_df", is_circulating=True)

# --- 10. Bearing Grease Tab ---
with grease_tab:
    st.header("Bearing Grease Analysis")
    if not st.session_state.data_loaded:
        st.warning("Please upload a Data Report to begin.")
    elif st.session_state.grease_df.empty:
        st.info("No applicable records for Bearing Grease analysis were found in the uploaded report.")
    else:
        st.subheader("Actions")
        if st.button("🚀 Process Grease Analysis", type="primary", key="grease_process_btn", use_container_width=True):
            with st.spinner("Calculating grease quantity and frequency..."):
                calculator = GreaseCalculator()
                results = {}
                for index, row in st.session_state.grease_df.iterrows():
                    results[index] = calculator.calculate_complete_analysis(row)
                st.session_state.grease_results = results
                st.success("Grease analysis complete!")
                st.rerun()
        
        st.subheader("Analysis Table")
        def get_grease_display_df():
            df = st.session_state.grease_df.copy()
            if st.session_state.get('grease_results'):
                res = st.session_state.grease_results
                df['Status'] = df.index.map(lambda i: "Success" if (res.get(i, {}).get('gq_grams', 0) > 0 or res.get(i, {}).get('frequency_hours', 0) > 0) else "Failed")
                df['Grease_g'] = df.index.map(lambda i: f"{res.get(i, {}).get('gq_grams', 0):.2f}")
                df['Qty_Method'] = df.index.map(lambda i: res.get(i, {}).get('quantity_method', 'N/A'))
                df['Frequency_h'] = df.index.map(lambda i: f"{res.get(i, {}).get('frequency_hours', 0):.1f}")
                df['Freq_Unit'] = df.index.map(lambda i: res.get(i, {}).get('frequency_unit', 'N/A'))
                df['K_Factor'] = df.index.map(lambda i: f"{res.get(i, {}).get('K_factor', 0):.2f}")
            else:
                df['Status'] = 'Pending'; df['Grease_g'] = '-'; df['Qty_Method'] = '-'; df['Frequency_h'] = '-'; df['Freq_Unit'] = '-'; df['K_Factor'] = '-'
            
            # Asignación segura de columnas por nombre
            df['RecordID'] = df['RecordID'] if 'RecordID' in df.columns else 'N/A'
            df['Machine'] = df['Machine'] if 'Machine' in df.columns else 'N/A'
            df['Component'] = df['Component'] if 'Component' in df.columns else 'N/A'
            return df

        grease_display_df = get_grease_display_df()
        
        cols_to_show = ['RecordID', 'Machine', 'Component', 'Status', 'Grease_g', 'Qty_Method', 'Frequency_h', 'Freq_Unit', 'K_Factor']
        
        existing_cols_to_show = [col for col in cols_to_show if col in grease_display_df.columns]
        
        st.dataframe(grease_display_df[existing_cols_to_show], use_container_width=True, hide_index=True)