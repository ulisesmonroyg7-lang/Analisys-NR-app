# --- analysis/circulating_systems_tab.py ---
# VERSIÓN CON LÓGICA DE ESTIMACIÓN AJUSTADA A (CAPACIDAD / 7)

import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
import logging

from .base_analysis_tab import BaseAnalysisTab
from core import RuleEngine
from ui.config_dialog import ConfigurationDialog
from ui.batch_config_dialog import BatchConfigurationDialog

logger = logging.getLogger(__name__)


class FlowRateAnalysisDialog:
    """Dialog to show flow rate data analysis summary"""
    
    def __init__(self, parent, analysis_summary):
        self.parent = parent
        self.analysis_summary = analysis_summary
        self.result = None
        
        self.dialog = ttk.Toplevel(parent)
        self.dialog.title("Flow Rate Data Analysis")
        self.dialog.geometry("750x700")
        self.dialog.resizable(True, True)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.center_dialog()
        self.setup_ui()
        self.dialog.wait_window()
    
    def center_dialog(self):
        self.dialog.update_idletasks()
        parent_x, parent_y = self.parent.winfo_rootx(), self.parent.winfo_rooty()
        parent_w, parent_h = self.parent.winfo_width(), self.parent.winfo_height()
        dialog_w, dialog_h = self.dialog.winfo_width(), self.dialog.winfo_height()
        x = parent_x + (parent_w - dialog_w) // 2
        y = parent_y + (parent_h - dialog_h) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def setup_ui(self):
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=BOTH, expand=True)
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=X, pady=(0, 20), anchor=W)
        ttk.Label(header_frame, text="🔧 Flow Rate Data Analysis", font=("Arial", 16, "bold")).pack(anchor=W)
        ttk.Label(header_frame, text="Analysis of available flow rate data for your circulating systems:", font=("Arial", 10), bootstyle="secondary").pack(anchor=W, pady=(5, 0))
        summary_frame = ttk.LabelFrame(main_frame, text="Data Summary", padding="15")
        summary_frame.pack(fill=X, pady=(0, 15))
        total = self.analysis_summary['total_records']; with_real_flow = self.analysis_summary['with_real_flow']
        with_cross_ref = self.analysis_summary.get('with_cross_reference', 0); with_estimation = self.analysis_summary['with_estimation']
        summary_text = (f"📊 Total Circulating System Records: {total}\n\n"
                        f"✅ Records with Real Flow Rate Data: {with_real_flow}\n"
                        f"🔗 Records with Cross-Reference Flow Data: {with_cross_ref}\n"
                        f"⚡ Records requiring Flow Rate Estimation: {with_estimation}")
        ttk.Label(summary_frame, text=summary_text, font=("Consolas", 11), justify=LEFT).pack(anchor=W)
        if self.analysis_summary['estimation_breakdown']:
            details_frame = ttk.LabelFrame(main_frame, text="Flow Rate Sources", padding="15"); details_frame.pack(fill=X, pady=(0, 15))
            tree_container = ttk.Frame(details_frame); tree_container.pack(fill=X, expand=True)
            tree = ttk.Treeview(tree_container, columns=("Count", "Method"), show="headings", height=6)
            tree.heading("Count", text="Count", anchor=tk.CENTER); tree.heading("Method", text="Flow Rate Source Method", anchor=W)
            tree.column("Count", width=80, anchor=tk.CENTER, stretch=False); tree.column("Method", width=500, anchor=W)
            sorted_breakdown = sorted(self.analysis_summary['estimation_breakdown'].items(), key=lambda item: item[1], reverse=True)
            for method, count in sorted_breakdown: tree.insert("", "end", values=(count, method))
            tree.pack(fill=X, expand=True)
        method_frame = ttk.LabelFrame(main_frame, text="Enhanced Circulating Systems Methodology", padding="15"); method_frame.pack(fill=X, pady=(0, 20))
        method_text = ("Flow-Based CFM Calculation: CFM = (Flow Rate (GPM) / 7.48) × 1.4\n"
                      "• NEW: Cross-reference pump siblings for total system flow\n"
                      "• 7.48 = Gallons to cubic feet conversion factor\n"
                      "• 1.4 = Safety factor for startup/shutdown conditions")
        ttk.Label(method_frame, text=method_text, font=("Arial", 9), justify=LEFT).pack(anchor=W)
        button_frame = ttk.Frame(main_frame); button_frame.pack(fill=X, side=BOTTOM, pady=(10, 0))
        ttk.Label(button_frame, text="💡 Cross-reference logic identifies pump siblings for accurate system flow calculation.", font=("Arial", 9), bootstyle="secondary").pack(side=LEFT, anchor=W)
        continue_btn = ttk.Button(button_frame, text="✅ Continue with Analysis", command=self.accept, bootstyle="success"); continue_btn.pack(side=RIGHT, padx=(10, 0))
        cancel_btn = ttk.Button(button_frame, text="❌ Cancel Analysis", command=self.cancel, bootstyle="outline-danger"); cancel_btn.pack(side=RIGHT)
        continue_btn.focus_set(); self.dialog.bind("<Return>", lambda e: self.accept()); self.dialog.bind("<Escape>", lambda e: self.cancel())
    def accept(self): self.result = True; self.dialog.destroy()
    def cancel(self): self.result = False; self.dialog.destroy()


class CirculatingSystemsDataProcessor:
    LPM_TO_GPM_FACTOR = 0.264172
    def __init__(self, excel_handler, global_config, overrides):
        self.excel_handler = excel_handler; self.global_config = global_config; self.overrides = overrides
        self.rule_engine = RuleEngine(global_config); self.results = {}; self.full_dataset = None
        self.breather_catalog = excel_handler.get_breather_catalog()
        brand_to_filter = global_config.get('brand_filter')
        if brand_to_filter and brand_to_filter != "All Brands" and self.breather_catalog is not None and not self.breather_catalog.empty:
            self.breather_catalog = self.breather_catalog[self.breather_catalog['Brand'] == brand_to_filter].copy()
            if self.breather_catalog.empty: logger.warning(f"[Circulating] No breathers found for brand '{brand_to_filter}'.")

    def _convert_to_gpm(self, flow_value: float, flow_unit: str) -> float:
        if pd.isna(flow_value) or flow_value <= 0: return 0.0
        return flow_value * self.LPM_TO_GPM_FACTOR if 'lpm' in str(flow_unit).lower().strip() else flow_value

    def analyze_flow_data_availability(self, data: pd.DataFrame) -> Dict:
        analysis = {'total_records': len(data), 'with_real_flow': 0, 'with_cross_reference': 0, 'with_estimation': 0, 'estimation_breakdown': {}}
        self.full_dataset = self.excel_handler.get_all_data()
        for idx, row in data.iterrows():
            has_real_flow = pd.notna(row.get('(D) Flow rate')) and row.get('(D) Flow rate') > 0
            siblings = self._find_pump_siblings(row.get('Machine', ''), idx) if pd.notna(row.get('Machine', '')) else []
            if has_real_flow:
                analysis['with_real_flow'] += 1; method = "Dato Real (Excel)"
            elif siblings:
                analysis['with_cross_reference'] += 1; method = f"Referencia Cruzada ({len(siblings)} bombas)"
            else:
                analysis['with_estimation'] += 1
                method = f"Estimado por Capacidad ({row.get('(D) Oil Capacity')}L)" if pd.notna(row.get('(D) Oil Capacity')) and row.get('(D) Oil Capacity') > 0 else f"Estimado Fijo ({str(row.get('MaintPointTemplate', 'N/A')).strip()})"
            analysis['estimation_breakdown'][method] = analysis['estimation_breakdown'].get(method, 0) + 1
        return analysis

    def _find_pump_siblings(self, target_machine: str, current_index: int) -> List[Dict]:
        if self.full_dataset is None or self.full_dataset.empty: return []
        siblings = []
        for idx, row in self.full_dataset.iterrows():
            if idx != current_index and str(row.get('Machine', '')).strip() == str(target_machine).strip() and any(k in str(row.get('MaintPointTemplate', '')).lower() for k in ['pump', 'bomba']):
                flow_rate = row.get('(D) Flow rate'); flow_unit = row.get('(DU) Flow Rate', 'gpm')
                if pd.notna(flow_rate) and flow_rate > 0: siblings.append({'flow_rate': float(flow_rate), 'flow_unit': flow_unit})
        return siblings

    def calculate_gpm_with_cross_reference(self, row: pd.Series, row_index: int, final_config: dict) -> Dict:
        total_flow_gpm = 0.0; method = "Error"
        manual_gpm = final_config.get('manual_gpm_override')
        if manual_gpm is not None and manual_gpm > 0:
            total_flow_gpm = manual_gpm; method = f"Anulación Manual ({manual_gpm} GPM)"
        if total_flow_gpm == 0:
            siblings = self._find_pump_siblings(row.get('Machine', ''), row_index)
            if siblings:
                total_flow_gpm = sum([self._convert_to_gpm(s['flow_rate'], s['flow_unit']) for s in siblings])
                method = f"Referencia Cruzada ({len(siblings)} bombas, Total: {total_flow_gpm:.1f} GPM)"
            else:
                individual_flow = row.get('(D) Flow rate')
                if pd.notna(individual_flow) and individual_flow > 0:
                    total_flow_gpm = self._convert_to_gpm(individual_flow, row.get('(DU) Flow Rate', 'gpm'))
                    method = f"Dato Real Individual ({total_flow_gpm:.1f} GPM)"
        if total_flow_gpm == 0:
            oil_cap = row.get('(D) Oil Capacity')
            # --- MODIFICACIÓN: Lógica de Estimación por Capacidad / 3 ---
            if pd.notna(oil_cap) and oil_cap > 0:
                estimated_lpm = oil_cap / 3
                total_flow_gpm = estimated_lpm * self.LPM_TO_GPM_FACTOR
                method = "Estimado (Capacidad / 3)"
            # --- FIN DE LA MODIFICACIÓN ---
            else:
                maint_point = str(row.get('MaintPointTemplate', 'N/A')).lower()
                if 'turbine' in maint_point: total_flow_gpm = 60.0
                elif 'hydraulic' in maint_point: total_flow_gpm = 40.0
                elif 'reservoir' in maint_point: total_flow_gpm = 35.0
                else: total_flow_gpm = 15.0
                method = f"Estimado Fijo ({maint_point.split(' ')[0]})"
        if total_flow_gpm <= 0: total_flow_gpm = 15.0; method = "Mínimo de Seguridad"
        cfm_required = (total_flow_gpm / 7.48) * 1.4
        return {'success': True, 'cfm_required': cfm_required, 'total_flow': total_flow_gpm, 'calculation_method': method}

    def process_all_records(self):
        self.full_dataset = self.excel_handler.get_all_data()
        for idx, row in self.excel_handler.data_report_df.iterrows():
            try:
                final_config = self.global_config.copy()
                if idx in self.overrides: final_config.update(self.overrides[idx])
                self.results[idx] = self.process_single_record(row, idx, self.breather_catalog, final_config)
            except Exception as e: self.results[idx] = self._create_error_result(str(e))
        return self.results

    def process_single_record(self, row: pd.Series, row_index: int, breather_catalog: pd.DataFrame, final_config: Dict) -> Dict:
        result = {'success': False, 'row_index': row_index, 'rule_trace': [], 'flow_analysis': {}, 'selected_breather': [], 'result_status': 'Failed', 'installation_notes': '', 'error_message': '', 'gpm_analysis': {}}
        try:
            self.rule_engine.config = final_config
            rule1 = self.rule_engine.apply_rule_1(row, final_config)
            result['rule_trace'].append(f"Rule 1 ({final_config.get('criticality', 'N/A')}): {rule1['description']}")
            if not rule1['breather_required']:
                return {**result, 'result_status': 'No Breather Required', 'success': True}
            flow_analysis = self.calculate_gpm_with_cross_reference(row, row_index, final_config)
            result['flow_analysis'] = flow_analysis
            cfm_required, asset_gpm = flow_analysis['cfm_required'], flow_analysis['total_flow']
            result['rule_trace'].append(f"Rule 2: CFM = {cfm_required:.2f} (Source: {flow_analysis['calculation_method']})")
            
            avg_humidity = pd.to_numeric(row.get('(D) Average Relative Humidity'), errors='coerce')
            if (pd.notna(avg_humidity) and avg_humidity >= 75.0) or asset_gpm >= 25.0:
                final_config['esi_manual'] = 'Extended service'
                result['rule_trace'].append("(!) Adaptive Logic: High RH or GPM detected, forcing E.S.")
            
            candidates = breather_catalog.copy()
            gpm_col = 'Max Fluid Flow (gpm)'
            if gpm_col in candidates.columns:
                candidates[gpm_col] = pd.to_numeric(candidates[gpm_col], errors='coerce')
                candidates = candidates[(candidates[gpm_col] >= asset_gpm) | (candidates[gpm_col].isna())]
                result['rule_trace'].append(f"Rule 2.5: {len(candidates)} breathers meet GPM >= {asset_gpm:.2f}")
                if candidates.empty: return {**result, 'error_message': f"No breathers found supporting {asset_gpm:.2f} GPM"}

            candidates = self.rule_engine.apply_rule_3(candidates, cfm_required)
            result['rule_trace'].append(f"Rule 3: {len(candidates)} breathers meet CFM >= {cfm_required:.2f}")
            if candidates.empty: return {**result, 'error_message': f"No breathers found with CFM >= {cfm_required:.2f}"}

            rule4 = self.rule_engine.apply_rule_4(candidates, row, final_config)
            candidates = rule4['filtered_breathers']; result['rule_trace'].extend(rule4['trace'])
            if candidates.empty: return {**result, 'error_message': "No breathers meet operational requirements"}

            volumes = {'v_oil': pd.to_numeric(row.get('(D) Oil Capacity'), errors='coerce') * 0.264172 if pd.notna(row.get('(D) Oil Capacity')) else 0}
            rule5 = self.rule_engine.apply_rule_5(candidates, volumes, 'circulating')
            candidates = rule5['filtered_breathers']; result['rule_trace'].append(rule5['trace'])
            if candidates.empty: return {**result, 'error_message': "No breathers meet sump volume requirements"}

            space_str = row.get('(D) Breather/Fill Port Clearance'); space_provided = pd.notna(space_str) and str(space_str).strip()
            space = self._parse_available_space(space_str); rule6 = self.rule_engine.apply_rule_6(candidates, space)
            
            rule7 = self.rule_engine.apply_rule_7(rule6['fitting_breathers'], rule6['non_fitting_breathers'], space, space_provided, final_config, "", cfm_required, True, volumes.get('v_oil', 0), 'circulating')
            result['rule_trace'].extend([rule6['trace'], rule7['trace']])
            
            if rule7['selected_breather']:
                breather = rule7['selected_breather'][0]; max_gpm = pd.to_numeric(breather.get('Max Fluid Flow (gpm)'), errors='coerce')
                margin = max_gpm / asset_gpm if pd.notna(max_gpm) and max_gpm > 0 and asset_gpm > 0 else 0
                result['gpm_analysis'] = {'asset_gpm': asset_gpm, 'breather_max_gpm': max_gpm, 'gpm_margin': margin, 'gpm_margin_warning': "Warning: GPM margin < 20%" if margin < 1.2 and margin > 0 else ""}
            
            final_notes = rule7['installation_notes']
            if result['gpm_analysis'].get('gpm_margin_warning'): final_notes += f"\n{result['gpm_analysis']['gpm_margin_warning']}"
            if 'Remote' in rule7['status']: final_notes += "\n\nRemote install notes: Use bypass/check valve..."
            
            result.update({'selected_breather': rule7['selected_breather'], 'result_status': rule7['status'], 'installation_notes': final_notes, 'success': True})
        except Exception as e: result['error_message'] = str(e)
        return result

    def _parse_available_space(self, space_str: str) -> Dict[str, Optional[float]]:
        if pd.isna(space_str) or not str(space_str).strip(): return {'height_limit': None, 'diameter_limit': None}
        s = str(space_str).lower()
        mappings = {'less than 2 inches': {'h': 2.0, 'd': 2.0}, '2 to <4 inches': {'h': 4.0, 'd': 4.0}, '4 to <6 inches': {'h': 6.0, 'd': 6.0}, 'greater than 6 inches': {'h': None, 'd': None}, 'no port available': {'h': 0.0, 'd': 0.0}}
        for key, limits in mappings.items():
            if key in s: return {'height_limit': limits['h'], 'diameter_limit': limits['d']}
        return {'height_limit': None, 'diameter_limit': None}

    def _create_error_result(self, error_message: str) -> Dict:
        return {'success': False, 'error_message': error_message, 'result_status': 'Error'}

    def get_results_as_dataframe(self) -> pd.DataFrame:
        if not self.results: return pd.DataFrame()
        results_list = []; include_trace = self.global_config.get('verbose_trace', False); include_calcs = self.global_config.get('include_calculations', False)
        for idx, result in self.results.items():
            row_data = {'original_index': idx}; flow = result.get('flow_analysis', {}); gpm_analysis = result.get('gpm_analysis', {})
            if result.get('selected_breather'):
                breather = result['selected_breather'][0]
                row_data.update({'Breather_Brand': breather.get('Brand'), 'Breather_Model': breather.get('Model'), 'CFM_Required': flow.get('cfm_required'), 'CFM_Capacity': breather.get('Max Air Flow (cfm)'), 'Flow_Rate_GPM': flow.get('total_flow'), 'GPM_Source': flow.get('calculation_method'), 'Breather_Max_GPM': gpm_analysis.get('breather_max_gpm'), 'GPM_Margin': gpm_analysis.get('gpm_margin'), 'GPM_Margin_Warning': gpm_analysis.get('gpm_margin_warning', ''), 'Result_Status': result.get('result_status'), 'Installation_Notes': result.get('installation_notes')})
            else:
                row_data.update({'Result_Status': result.get('result_status', 'Error'), 'Installation_Notes': result.get('error_message') or 'Processing failed'})
            if include_trace: row_data['Verbose_Trace'] = " -> ".join(result.get('rule_trace', []))
            if include_calcs: row_data['Calc_GPM_to_CFM'] = f"({flow.get('total_flow', 0):.2f} GPM / 7.48) * 1.4 = {flow.get('cfm_required', 0):.2f} CFM"
            results_list.append(row_data)
        return pd.DataFrame(results_list)

class CirculatingSystemsTab(BaseAnalysisTab):
    def __init__(self, parent, excel_handler, status_callback):
        super().__init__(parent, excel_handler, status_callback); self.data_processor = None; self.rule_engine_for_factors = RuleEngine({})
    def get_tab_name(self) -> str: return "Circulating System Breathers"
    def filter_data_for_analysis(self, data: pd.DataFrame) -> pd.DataFrame:
        if data.empty: return pd.DataFrame()
        circ_templates = ['Piping (Circulating)', 'Circulating System Reservoir (Oil)', 'Pump (Oil)', 'Gearbox (Circulating)', 'Pump Bearings (Circulating)', 'Bearing (Circulating)', 'Hydraulic System Reservoir (Oil)', 'Piping (Hydraulic)', 'Turbine Bearing (Circulating)', 'Sealed Pump']
        col_i = data.iloc[:, 8].astype(str); mask_exact = col_i.str.strip().isin(circ_templates)
        circ_keywords = ['circulating', 'pump', 'bomba', 'hydraulic', 'reservoir']
        mask_kw = pd.Series([False] * len(data), index=data.index)
        for kw in circ_keywords: mask_kw |= col_i.str.contains(kw, case=False, na=False, regex=True)
        filtered = data[mask_exact | mask_kw].copy()
        self.update_status(f"Found {len(filtered)} circulating system records")
        return filtered
    def setup_analysis_section(self):
        analysis_frame = ttk.LabelFrame(self.frame, text="Circulating Systems Analysis", padding="15"); analysis_frame.pack(fill=BOTH, expand=True, pady=(0, 15))
        self.setup_methodology_info(analysis_frame); self.setup_search_section(analysis_frame); self.setup_data_display(analysis_frame)
    def setup_methodology_info(self, parent):
        info_frame = ttk.Frame(parent, bootstyle="info"); info_frame.pack(fill=X, pady=(0, 10))
        info_text = "Enhanced Circulating Systems Methodology: Cross-reference pump siblings + GPM margin analysis + adaptive Extended Service logic."
        ttk.Label(info_frame, text=info_text, wraplength=800, font=("Arial", 9), bootstyle="info").pack(padx=10, pady=5)
    def setup_search_section(self, parent):
        search_frame = ttk.Frame(parent); search_frame.pack(fill=X, pady=(0, 10))
        ttk.Label(search_frame, text="Search:").pack(side=LEFT, padx=(0, 5)); self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var); search_entry.pack(side=LEFT, fill=X, expand=True); search_entry.bind("<KeyRelease>", self.filter_data_live)
        ttk.Label(search_frame, text=" (e.g., 'pump', 'source:cross', 'margin:<1.2')").pack(side=LEFT, padx=(5, 10))
        ttk.Button(search_frame, text="Clear", command=self.clear_filter, bootstyle="outline-secondary").pack(side=LEFT)
    def setup_data_display(self, parent):
        tree_frame = ttk.Frame(parent); tree_frame.pack(fill=BOTH, expand=True)
        self.tree = ttk.Treeview(tree_frame, show='headings', bootstyle="primary", selectmode='extended')
        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview); h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set); v_scrollbar.pack(side='right', fill='y'); h_scrollbar.pack(side='bottom', fill='x'); self.tree.pack(fill=BOTH, expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.on_selection_change)
    def get_analysis_columns(self) -> List[str]: return ['Status', 'Recommended_Model', 'CFM_Required', 'Flow_Rate_GPM', 'GPM_Source', 'GPM_Margin', 'GPM_Warning', 'Criticality', 'Mobile', 'CI', 'WCCI', 'ESI', 'Machine', 'Component']
    def setup_tree_columns(self):
        cols = self.get_analysis_columns(); config = {'Status': {'w': 60, 'a': 'center'}, 'Recommended_Model': {'w': 120, 'a': 'w'}, 'CFM_Required': {'w': 80, 'a': 'center'}, 'Flow_Rate_GPM': {'w': 80, 'a': 'center'}, 'GPM_Source': {'w': 200, 'a': 'w'}, 'GPM_Margin': {'w': 80, 'a': 'center'}, 'GPM_Warning': {'w': 60, 'a': 'center'}, 'Criticality': {'w': 70, 'a': 'center'}, 'Mobile': {'w': 50, 'a': 'center'}, 'CI': {'w': 50, 'a': 'center'}, 'WCCI': {'w': 60, 'a': 'center'}, 'ESI': {'w': 80, 'a': 'center'}, 'Machine': {'w': 120, 'a': 'w'}, 'Component': {'w': 120, 'a': 'w'}}
        self.tree["columns"] = cols; self.tree["displaycolumns"] = cols
        for col in cols: self.tree.heading(col, text=col.replace('_', ' '), anchor='w'); self.tree.column(col, width=config.get(col, {'w': 100})['w'], anchor=config.get(col, {'a': 'w'})['a'])
    def get_analytical_dataframe(self) -> pd.DataFrame:
        if self.original_data.empty: return pd.DataFrame()
        df = self.original_data.copy(); g_config = self.get_current_config(); factors_data = []
        for idx, row in df.iterrows():
            f_config = g_config.copy();
            if idx in self.overrides: f_config.update(self.overrides[idx])
            factors = self.rule_engine_for_factors._extract_operational_factors(row, f_config); factors['Criticality'] = f_config.get('criticality', g_config['criticality']); factors_data.append(factors)
        factors_df = pd.DataFrame(factors_data, index=df.index).rename(columns={'ci': 'CI', 'wcci': 'WCCI', 'esi': 'ESI', 'mobile_application': 'Mobile'})
        if 'Criticality' in df.columns: df = df.drop(columns=['Criticality'])
        df = df.join(factors_df[['Criticality', 'Mobile', 'CI', 'WCCI', 'ESI']])
        if self.data_processor and self.data_processor.results:
            res = self.data_processor.results
            df['CFM_Required'] = df.index.map(lambda i: res.get(i, {}).get('flow_analysis', {}).get('cfm_required'))
            df['Flow_Rate_GPM'] = df.index.map(lambda i: res.get(i, {}).get('flow_analysis', {}).get('total_flow'))
            df['GPM_Source'] = df.index.map(lambda i: res.get(i, {}).get('flow_analysis', {}).get('calculation_method'))
            df['Status'] = df.index.map(lambda i: res.get(i, {}).get('result_status', 'Failed'))
            df['GPM_Margin'] = df.index.map(lambda i: res.get(i, {}).get('gpm_analysis', {}).get('gpm_margin'))
            df['GPM_Warning'] = df.index.map(lambda i: '⚠️' if res.get(i, {}).get('gpm_analysis', {}).get('gpm_margin_warning') else '')
            df['Recommended_Model'] = df.index.map(lambda i: res.get(i, {}).get('selected_breather', [{}])[0].get('Model', 'N/A') if res.get(i, {}).get('selected_breather') else '-')
        else:
            for col in ['CFM_Required', 'Flow_Rate_GPM', 'GPM_Source', 'Recommended_Model', 'GPM_Margin']: df[col] = '-';
            df['Status'] = 'Pending'; df['GPM_Warning'] = ''
        return df
    def filter_data_live(self, event=None): self.filter_data()
    def filter_data(self):
        df = self.get_analytical_dataframe(); query = self.search_var.get().lower().strip()
        if not query: self.update_data_display(df); return
        for term in query.split():
            if ":" in term:
                key, val = term.split(":", 1)
                col_map = {'crit': 'Criticality', 'mobile': 'Mobile', 'ci': 'CI', 'wcci': 'WCCI', 'esi': 'ESI', 'model': 'Recommended_Model', 'flow': 'Flow_Rate_GPM', 'source': 'GPM_Source', 'margin': 'GPM_Margin'}
                if key in col_map:
                    if key == 'margin' and val.startswith('<'):
                        try: df = df[pd.to_numeric(df[col_map[key]], errors='coerce') < float(val[1:])]
                        except ValueError: pass
                    elif key == 'source' and 'cross' in val: df = df[df[col_map[key]].str.contains('Referencia Cruzada', na=False)]
                    else: df = df[df[col_map[key]].astype(str).str.lower().str.contains(val, na=False)]
            else: df = df[df['Machine'].str.lower().str.contains(term, na=False) | df['Component'].str.lower().str.contains(term, na=False)]
        self.update_data_display(df)
    def update_data_display(self, df_to_show: pd.DataFrame):
        for item in self.tree.get_children(): self.tree.delete(item)
        if df_to_show.empty: return
        if not self.tree["columns"]: self.setup_tree_columns()
        for index, row in df_to_show.iterrows():
            values = []
            for col in self.get_analysis_columns():
                val = row.get(col, '')
                if col == 'GPM_Margin' and isinstance(val, (int, float)) and not pd.isna(val): values.append(f"{val:.2f}")
                elif isinstance(val, (int, float)) and not pd.isna(val): values.append(f"{val:.1f}")
                else: values.append(str(val))
            self.tree.insert("", "end", iid=index, values=values)
    def clear_filter(self): self.search_var.set(""); self.filter_data()
    def refresh_display(self): self.filter_data()
    def on_selection_change(self, event):
        self.edit_selected_btn.config(state="normal" if self.tree.selection() else "disabled"); self.ai_btn.config(state="disabled")
    def process_analysis(self):
        if self.original_data.empty: return messagebox.showwarning("No Data", "No data available")
        temp_proc = CirculatingSystemsDataProcessor(self.excel_handler, {}, {}); summary = temp_proc.analyze_flow_data_availability(self.original_data)
        if summary['with_estimation'] > 0 or summary['with_cross_reference'] > 0:
            dialog = FlowRateAnalysisDialog(self.frame, summary)
            if not dialog.result: self.update_status("Analysis cancelled"); return
        self.processing = True; self.results = {}; self.process_btn.config(state="disabled"); self.update_status("Processing enhanced circulating systems analysis..."); self.frame.update()
        try:
            self.excel_handler.data_report_df = self.original_data.copy()
            self.data_processor = CirculatingSystemsDataProcessor(self.excel_handler, self.get_current_config(), self.overrides)
            self.results = self.data_processor.process_all_records()
            self.update_status("Enhanced analysis complete"); self.export_btn.config(state="normal"); self.refresh_display()
            total = len(self.results); successful = sum(1 for r in self.results.values() if r.get('success'))
            with_cross_ref = sum(1 for r in self.results.values() if 'Referencia Cruzada' in r.get('flow_analysis', {}).get('calculation_method', ''))
            with_gpm_warnings = sum(1 for r in self.results.values() if r.get('gpm_analysis', {}).get('gpm_margin_warning'))
            msg = (f"Enhanced Analysis Complete!\n\nProcessed: {total} records\nSuccessful: {successful} analyses\n"
                   f"Cross-Referenced: {with_cross_ref} pump siblings found\nGPM Margin Warnings: {with_gpm_warnings}")
            messagebox.showinfo("Analysis Complete", msg)
        except Exception as e: messagebox.showerror("Error", f"Analysis failed: {str(e)}"); self.update_status(f"Analysis failed: {str(e)}"); logger.error(f"Analysis error: {str(e)}", exc_info=True)
        finally: self.processing = False; self.process_btn.config(state="normal"); self.on_selection_change(None)
    def open_edit_dialog(self):
        selected = self.tree.selection()
        if not selected: return
        if len(selected) == 1:
            idx = int(selected[0]); config = self.get_current_config().copy()
            if idx in self.overrides: config.update(self.overrides[idx])
            dialog = ConfigurationDialog(self.frame, config)
        else: dialog = BatchConfigurationDialog(self.frame, len(selected))
        if dialog.result:
            for item_id in selected:
                idx = int(item_id)
                if idx not in self.overrides: self.overrides[idx] = {}
                self.overrides[idx].update(dialog.result)
            self.update_status(f"Configuration updated for {len(selected)} asset(s)"); self.refresh_display()
    def start_ai_analysis(self): messagebox.showinfo("Feature Not Available", "AI analysis is not yet available for this module.")
    def perform_export(self, file_path: str):
        if not self.results: raise Exception("No results to export")
        results_df = self.data_processor.get_results_as_dataframe()
        success, msg = self.excel_handler.save_results_with_merge(results_df, file_path)
        if not success: raise Exception(msg)
    def clear_all(self):
        if messagebox.askyesno("Confirmar", "¿Limpiar todos los datos y reiniciar este análisis?"):
            super().clear_all(); self.search_var.set("")
            for item in self.tree.get_children(): self.tree.delete(item)
            self.update_status("Análisis limpiado. Carga un reporte de datos para continuar.")