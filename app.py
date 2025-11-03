# app.py (Versión Final con Sintaxis Simplificada)
import streamlit as st
import pandas as pd
from pathlib import Path
import io
import logging

# --- Configuración del Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Importaciones de tu Lógica de Backend ---
from utils.excel_handler import ExcelHandler
from core.data_processor import DataProcessor as SplashDataProcessor
from core.rule_engine import RuleEngine
from core.grease_calculator import GreaseCalculator
from utils.gemini_client import GeminiChat, create_dossier_prompt_for_success, create_failure_analysis_prompt, create_summary_prompt_for_batch

# --- Configuración de la Página de Streamlit ---
st.set_page_config(
    page_title="NoRia Analysis Tool",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🔧"
)

# --- CLASE DE PROCESADOR DE CIRCULACIÓN INTEGRADA ---
class CirculatingSystemsDataProcessor:
    LPM_TO_GPM_FACTOR = 0.264172

    # --- CONSTRUCTOR MODIFICADO (SIN TYPE HINTS) ---
    def __init__(self, excel_handler, data_to_process, global_config, overrides):
        self.excel_handler = excel_handler
        self.data_to_process = data_to_process
        self.global_config = global_config
        self.overrides = overrides
        self.rule_engine = RuleEngine(global_config)
        self.results = {}
        self.full_dataset = None
        self.breather_catalog = self.excel_handler.get_breather_catalog()
        brand_to_filter = global_config.get('brand_filter')
        if brand_to_filter and brand_to_filter != "All Brands" and self.breather_catalog is not None and not self.breather_catalog.empty:
            self.breather_catalog = self.breather_catalog[self.breather_catalog['Brand'] == brand_to_filter].copy()

    def _convert_to_gpm(self, flow_value: float, flow_unit: str) -> float:
        if pd.isna(flow_value) or flow_value <= 0: return 0.0
        return flow_value * self.LPM_TO_GPM_FACTOR if 'lpm' in str(flow_unit).lower().strip() else flow_value

    def _find_pump_siblings(self, target_machine: str, current_index: int) -> list:
        if self.full_dataset is None or self.full_dataset.empty: return []
        siblings = []
        for idx, row in self.full_dataset.iterrows():
            if idx == current_index or str(row.get('Machine', '')).strip() != str(target_machine).strip(): continue
            maint_point = str(row.get('MaintPointTemplate', '')).lower()
            if 'pump' in maint_point or 'sealed pump' in maint_point:
                flow_rate = row.get('(D) Flow Rate')
                if pd.notna(flow_rate) and flow_rate > 0:
                    siblings.append({'flow_rate': float(flow_rate), 'flow_unit': row.get('(DU) Flow Rate', 'gpm')})
        return siblings

    def analyze_flow_data_availability(self, data: pd.DataFrame) -> dict:
        analysis = {'total_records': len(data), 'with_cross_reference': 0, 'with_estimation': 0}
        for idx, row in data.iterrows():
            siblings = self._find_pump_siblings(str(row.get('Machine', '')).strip(), idx)
            if siblings: analysis['with_cross_reference'] += 1
            else: analysis['with_estimation'] += 1
        return analysis

    def calculate_gpm_with_cross_reference(self, row: pd.Series, row_index: int, final_config: dict) -> dict:
        total_flow_gpm = 0.0; method = ""
        manual_gpm = final_config.get('manual_gpm_override')
        if manual_gpm is not None and manual_gpm > 0:
            total_flow_gpm, method = manual_gpm, f"Manual Override ({manual_gpm} GPM)"
        else:
            siblings = self._find_pump_siblings(str(row.get('Machine', '')).strip(), row_index)
            if siblings:
                total_flow_gpm = sum(self._convert_to_gpm(s['flow_rate'], s['flow_unit']) for s in siblings)
                method = f"Cross-Reference ({len(siblings)} pumps, Total: {total_flow_gpm:.1f} GPM)"
            else:
                oil_cap = row.get('(D) Oil Capacity')
                if pd.notna(oil_cap) and oil_cap > 0:
                    total_flow_gpm = (oil_cap / 3.0) * self.LPM_TO_GPM_FACTOR
                    method = f"Estimate (Capacity/3: {oil_cap:.1f}L / 3 = {total_flow_gpm:.1f} GPM)"
        if total_flow_gpm <= 0:
            total_flow_gpm, method = 15.0, "Safety Minimum (15 GPM)"
        cfm_required = (total_flow_gpm / 7.48) * 1.4
        return {'success': True, 'cfm_required': cfm_required, 'total_flow': total_flow_gpm, 'calculation_method': method}

    def _parse_available_space(self, space_str: str) -> dict:
        if pd.isna(space_str) or not str(space_str).strip(): return {'height_limit': None, 'diameter_limit': None}
        s = str(space_str).lower()
        mappings = {'less than 2 inches': {'h': 2.0, 'd': 2.0}, '2 to <4 inches': {'h': 4.0, 'd': 4.0}, '4 to <6 inches': {'h': 6.0, 'd': 6.0}, 'greater than 6 inches': {'h': None, 'd': None}, 'no port available': {'h': 0.0, 'd': 0.0}}
        for key, limits in mappings.items():
            if key in s: return {'height_limit': limits['h'], 'diameter_limit': limits['d']}
        return {'height_limit': None, 'diameter_limit': None}

    def process_all_records(self):
        for idx, row in self.data_to_process.iterrows():
            try:
                final_config = self.global_config.copy()
                if idx in self.overrides: final_config.update(self.overrides[idx])
                self.results[idx] = self.process_single_record(row, idx, self.breather_catalog, final_config)
            except Exception as e:
                logger.error(f"Error processing record {idx}: {str(e)}"); self.results[idx] = self._create_error_result(str(e))
        return self.results

    def process_single_record(self, row, row_index, breather_catalog, final_config):
        result = {'success': False, 'rule_trace': [], 'flow_analysis': {}, 'selected_breather': [], 'result_status': 'Failed', 'error_message': ''}
        try:
            self.rule_engine.config = final_config
            rule1_result = self.rule_engine.apply_rule_1(row, final_config)
            result['rule_trace'].append(rule1_result['description'])
            if not rule1_result['breather_required']:
                return {**result, 'result_status': 'No Breather Required', 'success': True}
            flow_analysis = self.calculate_gpm_with_cross_reference(row, row_index, final_config)
            cfm_required, asset_gpm = flow_analysis['cfm_required'], flow_analysis['total_flow']
            result.update({'flow_analysis': flow_analysis})
            candidates, trace3 = self.rule_engine.apply_rule_3_cfm(breather_catalog, cfm_required)
            result['rule_trace'].append(trace3)
            if candidates.empty: return {**result, 'error_message': "No breathers found matching CFM."}
            initial_count_gpm = len(candidates)
            candidates, trace_gpm = self.rule_engine.apply_rule_gpm_margin(candidates, asset_gpm)
            result['rule_trace'].append(f"{trace_gpm} ({len(candidates)} of {initial_count_gpm} candidates remain).")
            if candidates.empty: return {**result, 'error_message': "No breathers found matching GPM Margin."}
            oil_cap_liters = pd.to_numeric(row.get('(D) Oil Capacity'), errors='coerce')
            v_oil_gallons = (oil_cap_liters * self.LPM_TO_GPM_FACTOR) if pd.notna(oil_cap_liters) else 0
            volumes = {'v_oil': v_oil_gallons}
            initial_count_sump = len(candidates)
            candidates, trace5 = self.rule_engine.apply_rule_5_sump(candidates, volumes, 'circulating')
            result['rule_trace'].append(f"{trace5} ({len(candidates)} of {initial_count_sump} candidates remain).")
            if candidates.empty: return {**result, 'error_message': "No breathers meet Sump Volume requirements."}
            candidates, op_trace = self.rule_engine.apply_operational_filters(candidates, row, final_config)
            result['rule_trace'].extend(op_trace)
            if candidates.empty: return {**result, 'error_message': "No breathers found matching all operational requirements."}
            space_str = row.get('(D) Breather/Fill Port Clearance'); space_data_provided = pd.notna(space_str) and str(space_str).strip() != ''
            available_space = self._parse_available_space(space_str)
            rule6_result = self.rule_engine.apply_rule_6(candidates, available_space)
            result['rule_trace'].append(f"{rule6_result['trace']} ({len(rule6_result['fitting_breathers'])} fitting, {len(rule6_result['non_fitting_breathers'])} non-fitting).")
            rule7_result = self.rule_engine.apply_rule_7(rule6_result['fitting_breathers'], rule6_result['non_fitting_breathers'], available_space, space_data_provided, final_config, "", cfm_required, True, volumes['v_oil'], 'circulating')
            result['rule_trace'].append(rule7_result['trace'])
            result.update({'selected_breather': rule7_result['selected_breather'], 'result_status': rule7_result['status'], 'installation_notes': rule7_result['installation_notes'], 'success': True if rule7_result.get('selected_breather') else False})
        except Exception as e:
            result['error_message'] = str(e); logger.error(f"Critical error on asset {row_index}: {e}", exc_info=True)
        return result

    def _create_error_result(self, error_message: str) -> dict:
        return {'success': False, 'error_message': error_message, 'result_status': 'Error'}

    def get_results_as_dataframe(self, export_config: dict = None) -> pd.DataFrame:
        if not self.results: return pd.DataFrame()
        config = export_config if export_config is not None else self.global_config
        include_trace = config.get('verbose_trace', False); include_calcs = config.get('include_calculations', False)
        results_list = []
        for idx, result in self.results.items():
            row_data = {'original_index': idx}; flow = result.get('flow_analysis', {}); gpm_analysis = result.get('gpm_analysis', {})
            if result.get('success') and result.get('selected_breather'):
                breather = result['selected_breather'][0]
                row_data.update({'Breather_Brand': breather.get('Brand'), 'Breather_Model': breather.get('Model'), 'CFM_Required': flow.get('cfm_required'), 'CFM_Capacity': breather.get('Max Air Flow (cfm)'), 'Flow_Rate_GPM': flow.get('total_flow'), 'GPM_Source': flow.get('calculation_method'), 'Breather_Max_GPM': gpm_analysis.get('breather_max_gpm'), 'GPM_Margin': gpm_analysis.get('gpm_margin'), 'GPM_Margin_Warning': gpm_analysis.get('gpm_margin_warning', ''), 'Result_Status': result.get('result_status'), 'Installation_Notes': result.get('installation_notes')})
            else:
                row_data.update({'Result_Status': result.get('result_status', 'Error'), 'Installation_Notes': result.get('error_message') or 'Processing failed'})
            if include_trace: row_data['Verbose_Trace'] = "\n".join(result.get('rule_trace', []))
            if include_calcs: row_data['Calc_GPM_to_CFM'] = f"({flow.get('total_flow', 0):.2f} GPM / 7.48) * 1.4 = {flow.get('cfm_required', 0):.2f} CFM"
            results_list.append(row_data)
        return pd.DataFrame(results_list)

# --- INICIALIZACIÓN Y FUNCIONES GLOBALES ---

def initialize_state():
    # (Sin cambios)
    if 'excel_handler' not in st.session_state:
        st.session_state.excel_handler = ExcelHandler()
        default_catalog = "data/breathers_catalog.xlsx"
        st.session_state.catalog_loaded = Path(default_catalog).exists() and st.session_state.excel_handler.load_breather_catalog(default_catalog)
    if 'data_loaded' not in st.session_state: st.session_state.data_loaded = False
    if 'loaded_file_name' not in st.session_state: st.session_state.loaded_file_name = ""
    for tab in ['splash', 'circulating', 'grease']:
        if f'{tab}_results' not in st.session_state: st.session_state[f'{tab}_results'] = {}
        if f'{tab}_overrides' not in st.session_state: st.session_state[f'{tab}_overrides'] = {}
        if f'{tab}_analytical_df' not in st.session_state: st.session_state[f'{tab}_analytical_df'] = pd.DataFrame()
        if f'{tab}_config' not in st.session_state:
            st.session_state[f'{tab}_config'] = {'criticality': 'A', 'brand_filter': 'All Brands', 'safety_factor': 1.4, 'min_amb_temp': 60.0, 'max_amb_temp': 80.0, 'mobile_application': False, 'verbose_trace': False, 'include_calculations': False, 'manual_gpm_override': 0.0}
    if 'global_gemini_api_key' not in st.session_state: st.session_state.global_gemini_api_key = ""

# --- PESTAÑAS DE LA INTERFAZ ---

def render_splash_tab():
    st.header("Breather Analysis for Splash / Oil Bath Systems")
    splash_data = st.session_state.excel_handler.get_gearbox_data()
    if splash_data.empty: st.warning("No applicable records for 'Splash/Oil Bath' were found in the file."); return
    config = st.session_state.splash_config
    if st.button("🚀 Process Analysis (Splash)", type="primary"):
        with st.spinner("Running analysis..."):
            processor = SplashDataProcessor(st.session_state.excel_handler, splash_data, config, st.session_state.splash_overrides)
            st.session_state.splash_results = processor.process_all_records()
            st.session_state.splash_analytical_df = get_analytical_dataframe(splash_data, st.session_state.splash_results, config, st.session_state.splash_overrides)
        st.success(f"Analysis completed for {len(st.session_state.splash_results)} records.")
    if not st.session_state.splash_analytical_df.empty:
        df_display = st.session_state.splash_analytical_df
        st.subheader("Analysis Results")
        search_query = st.text_input("Search in results...", key='splash_search')
        if search_query: df_display = df_display[df_display.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)]
        st.dataframe(df_display, use_container_width=True)
        render_asset_editor('splash', df_display)
        st.subheader("Export")
        if st.session_state.splash_results:
            st.info("The export will merge the analysis results with your original data report.")
            processor_for_export = SplashDataProcessor(st.session_state.excel_handler, splash_data, config, st.session_state.splash_overrides)
            processor_for_export.process_all_records() 
            results_df_for_export = processor_for_export.get_results_as_dataframe(export_config=config)
            output_buffer = io.BytesIO()
            success, msg = st.session_state.excel_handler.save_results_with_merge(results_df_for_export, output_buffer)
            if success: st.download_button("📥 Download Full Report (.xlsx)", output_buffer.getvalue(), "splash_results_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key='splash_export_btn')
            else: st.error(f"Error preparing the export file: {msg}")
        render_ai_analysis_section('splash', df_display)

def render_circulating_tab():
    st.header("Breather Analysis for Circulating Systems")
    circulating_data = filter_data_for_circulating_analysis(st.session_state.excel_handler.get_all_data())
    if circulating_data.empty: st.warning("No applicable 'Gearbox (Circulating)' or 'Hydraulic System Reservoir' records were found."); return
    config = st.session_state.circulating_config
    if st.button("🚀 Process Analysis (Circulation)", type="primary"):
        with st.spinner("Running circulation analysis..."):
            full_dataset = st.session_state.excel_handler.get_all_data()
            processor = CirculatingSystemsDataProcessor(st.session_state.excel_handler, circulating_data, config, st.session_state.circulating_overrides)
            processor.full_dataset = full_dataset
            flow_summary = processor.analyze_flow_data_availability(circulating_data)
            st.info(f"""**Flow Rate Data Summary:**\n- **{flow_summary['with_cross_reference']}** records with potential cross-reference from pump siblings.\n- **{flow_summary['with_estimation']}** records requiring flow rate estimation.""")
            st.session_state.circulating_results = processor.process_all_records()
            results_list = [{'original_index': idx, 'Status': res.get('result_status'), 'Recommended_Model': res.get('selected_breather', [{}])[0].get('Model') if res.get('selected_breather') else '-', 'CFM_Required': res.get('flow_analysis', {}).get('cfm_required'), 'Flow_Rate_GPM': res.get('flow_analysis', {}).get('total_flow'), 'GPM_Source': res.get('flow_analysis', {}).get('calculation_method'), 'GPM_Margin': res.get('gpm_analysis', {}).get('gpm_margin'), 'GPM_Warning': '⚠️' if res.get('gpm_analysis', {}).get('gpm_margin_warning') else ''} for idx, res in st.session_state.circulating_results.items()]
            analytical_df = pd.DataFrame(results_list).set_index('original_index')
            st.session_state.circulating_analytical_df = circulating_data[['Machine', 'Component']].join(analytical_df)
        st.success(f"Circulation analysis completed for {len(st.session_state.circulating_results)} records.")
    if not st.session_state.circulating_analytical_df.empty:
        df_display = st.session_state.circulating_analytical_df
        st.subheader("Analysis Results (Circulation)")
        st.dataframe(df_display, use_container_width=True)
        st.subheader("🔍 Analysis Trace Inspector")
        selected_asset_id_trace = st.selectbox("Select an asset to view its detailed selection logic:", options=df_display.index.tolist(), key='circ_trace_selector', index=None, placeholder="Choose an Asset ID...")
        if selected_asset_id_trace:
            asset_result = st.session_state.circulating_results.get(selected_asset_id_trace)
            if asset_result:
                with st.expander(f"Trace for Asset ID {selected_asset_id_trace}", expanded=True):
                    for step in asset_result.get('rule_trace', []): st.text(step)
            else: st.warning("Could not retrieve trace for the selected asset.")
        render_asset_editor('circulating', df_display)
        st.subheader("Export")
        if st.session_state.circulating_results:
            st.info("The export will merge the analysis results with your original data report.")
            processor_for_export = CirculatingSystemsDataProcessor(st.session_state.excel_handler, circulating_data, config, st.session_state.circulating_overrides)
            processor_for_export.full_dataset = st.session_state.excel_handler.get_all_data()
            processor_for_export.process_all_records()
            results_df_for_export = processor_for_export.get_results_as_dataframe(export_config=config)
            output_buffer = io.BytesIO()
            success, msg = st.session_state.excel_handler.save_results_with_merge(results_df_for_export, output_buffer)
            if success: st.download_button("📥 Download Full Report (.xlsx)", output_buffer.getvalue(), "circulating_results_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key='circ_export_btn')
            else: st.error(f"Error preparing the export file: {msg}")
        render_ai_analysis_section('circulating', df_display)

def render_grease_tab():
    st.header("Bearing Grease Analysis")
    grease_data = st.session_state.excel_handler.get_bearing_grease_data()
    if grease_data.empty: st.warning("No applicable records for 'Grease Analysis' were found in the file."); return
    if st.button("🚀 Calculate Grease Quantity & Frequency", type="primary"):
        with st.spinner("Calculating..."):
            calculator = GreaseCalculator(); results = {index: calculator.calculate_complete_analysis(row) for index, row in grease_data.iterrows()}
            st.session_state.grease_results = results
            results_df = pd.DataFrame.from_dict(results, orient='index')
            st.session_state.grease_analytical_df = grease_data[['Machine', 'Component']].join(results_df)
        st.success(f"Calculation completed for {len(results)} bearings.")
    if not st.session_state.grease_analytical_df.empty:
        df_display = st.session_state.grease_analytical_df.copy()
        st.subheader("Grease Calculation Results")
        cols_order = ['Machine', 'Component', 'gq_grams', 'quantity_method', 'frequency_hours', 'frequency_unit', 'K_factor', 'error']
        existing_cols = [col for col in cols_order if col in df_display.columns]
        df_display_formatted = df_display.copy()
        for col in ['gq_grams', 'K_factor']: df_display_formatted[col] = df_display_formatted[col].map('{:,.2f}'.format)
        df_display_formatted['frequency_hours'] = df_display_formatted['frequency_hours'].map('{:,.1f}'.format)
        st.dataframe(df_display_formatted[existing_cols], use_container_width=True)
        st.subheader("Manual Editing")
        st.info("Manual asset editing is not available for Grease Analysis. Calculations are based on physical properties from the data report. To change a result, please modify the source data and re-upload the report.")
        st.subheader("Export")
        if st.session_state.grease_results:
            st.info("The export will merge the calculation results with your original data report.")
            grease_export_df = pd.DataFrame.from_dict(st.session_state.grease_results, orient='index').reset_index().rename(columns={'index': 'original_index'})
            output_buffer = io.BytesIO()
            success, msg = st.session_state.excel_handler.save_results_with_merge(grease_export_df, output_buffer)
            if success: st.download_button("📥 Download Full Report (.xlsx)", output_buffer.getvalue(), "grease_results_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key='grease_export_btn')
            else: st.error(f"Error preparing the export file: {msg}")

def filter_data_for_circulating_analysis(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty: return pd.DataFrame()
    circ_templates = ['Gearbox (Circulating)', 'Hydraulic System Reservoir (Oil)']
    return data[data.iloc[:, 8].astype(str).str.strip().isin(circ_templates)].copy()

def render_asset_editor(tab_key: str, analytical_df: pd.DataFrame):
    st.subheader("📝 Manual Asset Editing")
    options = {f"{idx} - {row.get('Machine', '')} | {row.get('Component', '')}": idx for idx, row in analytical_df.iterrows()}
    selected_labels = st.multiselect(f"1. Select assets to edit for {tab_key.title()} analysis:", options=options.keys(), key=f'{tab_key}_editor_multiselect')
    selected_ids = [options[label] for label in selected_labels]
    if selected_ids:
        with st.expander("2. Define new parameters for the selected assets", expanded=True):
            edit_cols = st.columns(2)
            new_criticality = edit_cols[0].selectbox("New Criticality", ["(No Change)", "A", "B1", "B2", "C"], key=f'{tab_key}_edit_crit')
            new_mobile = edit_cols[1].selectbox("Is Mobile Application", ["(No Change)", "Yes", "No"], key=f'{tab_key}_edit_mobile')
            if tab_key == 'circulating':
                new_gpm = st.number_input("Manual GPM Override (Set to 0 for auto, -1 for no change)", min_value=-1.0, value=-1.0, key=f'{tab_key}_edit_gpm')
            if st.button("💾 Apply Changes to Selection", key=f'{tab_key}_apply_overrides'):
                for asset_id in selected_ids:
                    if asset_id not in st.session_state[f'{tab_key}_overrides']: st.session_state[f'{tab_key}_overrides'][asset_id] = {}
                    if new_criticality != "(No Change)": st.session_state[f'{tab_key}_overrides'][asset_id]['criticality'] = new_criticality
                    if new_mobile != "(No Change)": st.session_state[f'{tab_key}_overrides'][asset_id]['mobile_application'] = (new_mobile == "Yes")
                    if tab_key == 'circulating' and new_gpm >= 0:
                        st.session_state[f'{tab_key}_overrides'][asset_id]['manual_gpm_override'] = new_gpm
                st.success(f"Changes applied to {len(selected_ids)} assets. Re-process to see updated results.")
                st.rerun()

def render_ai_analysis_section(tab_key: str, analytical_df: pd.DataFrame):
    st.subheader("🔬 Artificial Intelligence Analysis")
    if not st.session_state.global_gemini_api_key: st.warning("Enter your Gemini API Key in the sidebar's AI Configuration to enable this feature."); return
    col1, col2 = st.columns(2)
    with col1:
        selected_asset_id = st.selectbox("Select an asset for detailed analysis", analytical_df.index.tolist(), key=f'{tab_key}_asset_select', index=None, placeholder="Choose an ID")
    with col2:
        if st.button("📄 Generate Executive Summary for Batch", key=f'{tab_key}_summary_btn'):
            with st.spinner("AI is generating the summary..."):
                try:
                    chat = GeminiChat(st.session_state.global_gemini_api_key)
                    if chat.model:
                        summary_data = {'total': len(analytical_df), 'status_counts': analytical_df['Status'].value_counts().to_dict(), 'top_models': analytical_df.get('Recommended_Model', pd.Series()).value_counts().to_dict()}
                        prompt = create_summary_prompt_for_batch(summary_data)
                        st.session_state[f'{tab_key}_summary_text'] = chat.send_message(prompt)
                    else: st.error("Could not configure the AI model. Check your API Key.")
                except Exception as e: st.error(f"An error occurred while generating the summary: {e}")
    if f'{tab_key}_summary_text' in st.session_state:
        with st.expander("Executive Summary", expanded=True): st.markdown(st.session_state[f'{tab_key}_summary_text'])
    if selected_asset_id:
        with st.expander(f"Chat with AI about Asset ID: {selected_asset_id}", expanded=True):
            asset_result = st.session_state[f'{tab_key}_results'].get(selected_asset_id)
            if not asset_result: st.error("Could not retrieve analysis results for the selected asset."); return
            chat_session_key = f'{tab_key}_chat_history_{selected_asset_id}'; chat_instance_key = f'{tab_key}_chat_instance'
            if st.session_state.get('current_chat_asset_id') != selected_asset_id:
                st.session_state[chat_session_key] = []; st.session_state['current_chat_asset_id'] = selected_asset_id
                if chat_instance_key in st.session_state: del st.session_state[chat_instance_key]
            if st.button("Start/Reset Conversation", key=f'{tab_key}_start_chat_{selected_asset_id}'):
                with st.spinner("Contacting AI..."):
                    chat = GeminiChat(st.session_state.global_gemini_api_key)
                    if chat.model:
                        prompt = create_dossier_prompt_for_success(asset_result) if asset_result.get('success') else create_failure_analysis_prompt(asset_result)
                        success, initial_message = chat.start_chat_and_get_greeting(prompt)
                        if success: st.session_state[chat_session_key] = [{"role": "assistant", "content": initial_message}]; st.session_state[chat_instance_key] = chat
                        else: st.session_state[chat_session_key] = [{"role": "assistant", "content": f"Error: {initial_message}"}]
                    else: st.session_state[chat_session_key] = [{"role": "assistant", "content": "Error: Could not configure AI model."}]
                st.rerun()
            for message in st.session_state.get(chat_session_key, []):
                with st.chat_message(message["role"]): st.markdown(message["content"])
            if prompt := st.chat_input("Ask a question about this selection..."):
                st.session_state[chat_session_key].append({"role": "user", "content": prompt})
                chat_instance = st.session_state.get(chat_instance_key)
                if chat_instance:
                    with st.spinner("Thinking..."):
                        response = chat_instance.send_message(prompt); st.session_state[chat_session_key].append({"role": "assistant", "content": response}); st.rerun()
                else: st.warning("Please start the conversation first."); st.rerun()

def get_analytical_dataframe(original_data, results, config, overrides) -> pd.DataFrame:
    if original_data.empty: return pd.DataFrame()
    df = original_data.copy()
    rule_engine = RuleEngine({})
    factors_data, overrides_applied = [], []
    for index, row in df.iterrows():
        final_config = config.copy(); override_log = []
        if index in overrides:
            final_config.update(overrides[index])
            for key, val in overrides[index].items(): override_log.append(f"{key.replace('_', ' ').title()}: {val}")
        overrides_applied.append("; ".join(override_log))
        factors = rule_engine._extract_operational_factors(row, final_config); factors['Criticality'] = final_config.get('criticality')
        factors_data.append(factors)
    factors_df = pd.DataFrame(factors_data, index=df.index).rename(columns={'ci': 'CI', 'wcci': 'WCCI', 'esi': 'ESI', 'mobile_application': 'Mobile'})
    df = df.join(factors_df[['Criticality', 'Mobile', 'CI', 'WCCI', 'ESI']]); df['Overrides'] = overrides_applied
    if results:
        df['CFM_Required'] = df.index.map(lambda idx: results.get(idx, {}).get('thermal_analysis', {}).get('cfm_required'))
        df['Status'] = df.index.map(lambda idx: results.get(idx, {}).get('result_status', 'Failed'))
        df['Recommended_Model'] = df.index.map(lambda idx: results.get(idx, {}).get('selected_breather', [{}])[0].get('Model', '-') if results.get(idx, {}).get('selected_breather') else '-')
    else: df['CFM_Required'], df['Status'], df['Recommended_Model'] = ['-'] * 3
    cols_order = ['Overrides', 'Status', 'Recommended_Model', 'CFM_Required', 'Criticality', 'Mobile', 'CI', 'WCCI', 'ESI', 'Machine', 'Component']
    return df[[col for col in cols_order if col in df.columns]]

def main():
    initialize_state()
    st.title("🔧 NoRia Analysis Tool - Multi-Analysis Platform")
    st.markdown("Comprehensive lubrication analysis platform - Adapted for Streamlit")
    with st.sidebar:
        st.header("Data Source")
        if st.session_state.get('catalog_loaded', False): st.success("✓ Breather catalog loaded.")
        else: st.warning("✗ Breather catalog not found.")
        uploaded_file = st.file_uploader("Upload Data Report", type=['xlsx', 'xls', 'csv'])
        if uploaded_file and uploaded_file.name != st.session_state.loaded_file_name:
            with st.spinner('Processing file...'):
                success, error_msg = st.session_state.excel_handler.load_data_report(uploaded_file)
                if success:
                    st.session_state.data_loaded, st.session_state.loaded_file_name = True, uploaded_file.name
                    for tab in ['splash', 'circulating', 'grease']: st.session_state[f'{tab}_results'], st.session_state[f'{tab}_analytical_df'] = {}, pd.DataFrame()
                    st.success(f"'{uploaded_file.name}' loaded."); st.rerun()
                else:
                    st.session_state.data_loaded = False; st.error(f"Error: {error_msg}")
        st.divider()
        st.header("Analysis Parameters")
        with st.expander("⚙️ Configuration (Splash/Oil Bath)", expanded=False):
            config_s = st.session_state.splash_config
            config_s['criticality'] = st.selectbox("Criticality", ["A", "B1", "B2", "C"], key='splash_crit_side')
            config_s['brand_filter'] = st.selectbox("Brand", ["All Brands", "Des-Case", "Air Sentry"], key='splash_brand_side')
            config_s['mobile_application'] = st.checkbox("Mobile Application (Global)", key='splash_mobile_side')
            with st.popover("Advanced (Splash)"):
                config_s['safety_factor'] = st.slider("Safety Factor", 1.0, 2.0, 1.4, 0.1, key='splash_sf_side')
                config_s['verbose_trace'] = st.checkbox("Include verbose trace", key='splash_verbose_side')
                config_s['include_calculations'] = st.checkbox("Include intermediate calculations", key='splash_calcs_side')
        with st.expander("⚙️ Configuration (Circulation)", expanded=False):
            config_c = st.session_state.circulating_config
            config_c['criticality'] = st.selectbox("Criticality", ["A", "B1", "B2", "C"], key='circ_crit_side')
            config_c['brand_filter'] = st.selectbox("Brand", ["All Brands", "Des-Case", "Air Sentry"], key='circ_brand_side')
            config_c['verbose_trace'] = st.checkbox("Include verbose trace", key='circ_verbose_side')
            with st.popover("Advanced (Circulation)"):
                 config_c['manual_gpm_override'] = st.number_input("Manual GPM Override (0 to disable)", value=0.0, key='circ_gpm_side')
        with st.expander("⚙️ Configuration (Grease Analysis)", expanded=False):
            st.info("Grease analysis is fully driven by the data report and does not require additional global settings.")
        st.divider()
        with st.expander("🤖 Gemini AI Configuration", expanded=True):
            st.session_state.global_gemini_api_key = st.text_input("Enter your Gemini API Key", type="password", key='global_api_key_input')
        st.divider()
        if st.button("Clear & Reset All"):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()
    if st.session_state.data_loaded:
        tab1, tab2, tab3 = st.tabs([" Splash/Oil Bath Breathers ", " Circulating System Breathers ", " Bearing Grease Analysis "])
        with tab1: render_splash_tab()
        with tab2: render_circulating_tab()
        with tab3: render_grease_tab()
    else:
        st.info("Please upload a data report from the sidebar to begin.")

if __name__ == "__main__":
    main()