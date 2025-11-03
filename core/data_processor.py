# core/data_processor.py (Versión con Sintaxis Simplificada)

import pandas as pd
from typing import Dict, List, Optional, Any

from .calculations import ThermalCalculator
from .rule_engine import RuleEngine
import logging
logger = logging.getLogger(__name__)

class DataProcessor:
    """Main data processor implementing the complete breather selection workflow"""
    
    # --- CONSTRUCTOR MODIFICADO (SIN TYPE HINTS PARA MÁXIMA COMPATIBILIDAD) ---
    def __init__(self, excel_handler, data_to_process, global_config, overrides):
        self.excel_handler = excel_handler
        self.data_to_process = data_to_process
        self.global_config = global_config
        self.overrides = overrides
        self.thermal_calculator = ThermalCalculator()
        self.rule_engine = RuleEngine(global_config)
        
        self.breather_catalog = excel_handler.get_breather_catalog()
        self.results = {}

        brand_to_filter = global_config.get('brand_filter')
        if brand_to_filter and brand_to_filter != "All Brands":
            if self.breather_catalog is not None and not self.breather_catalog.empty:
                logger.info(f"Applying brand filter: Only using '{brand_to_filter}' products.")
                self.breather_catalog = self.breather_catalog[self.breather_catalog['Brand'] == brand_to_filter].copy()
                if self.breather_catalog.empty:
                    logger.warning(f"No breathers found for the selected brand '{brand_to_filter}'. Analysis might fail.")
            
    def process_all_records(self) -> Dict[int, Dict]:
        for idx, row in self.data_to_process.iterrows():
            try:
                final_config = self.global_config.copy()
                final_config.setdefault('min_amb_temp', 60.0)
                final_config.setdefault('max_amb_temp', 80.0)
                if final_config['min_amb_temp'] is None: final_config['min_amb_temp'] = 60.0
                if final_config['max_amb_temp'] is None: final_config['max_amb_temp'] = 80.0
                
                if idx in self.overrides:
                    for key, value in self.overrides[idx].items():
                        if value is not None:
                            final_config[key] = value
                
                self.results[idx] = self.process_single_record(row, idx, final_config)
                
            except Exception as e:
                logger.error(f"Critical error processing record index {idx}: {str(e)}", exc_info=True)
                self.results[idx] = self._create_error_result(str(e))
        
        return self.results
    
    def process_single_record(self, row: pd.Series, row_index: int, config: Dict) -> Dict:
        result = {'success': False, 'row_index': row_index, 'rule_trace': [], 'thermal_analysis': {}, 'selected_breather': [], 'result_status': 'Failed', 'installation_notes': '', 'error_message': '', 'rejected_candidates': []}
        if self.breather_catalog is None or self.breather_catalog.empty:
            return self._update_result_with_error(result, "Breather catalog is not loaded or is empty.")
        try:
            self.rule_engine.config = config
            self.thermal_calculator.safety_factor = config.get('safety_factor', 1.4)
            rule1_result = self.rule_engine.apply_rule_1(row, config)
            result['rule_trace'].append(rule1_result['description'])
            if not rule1_result['breather_required']:
                return {**result, 'result_status': 'No Breather Required', 'success': True}
            min_amb, max_amb = config.get('min_amb_temp', 60.0), config.get('max_amb_temp', 80.0)
            ambient_temps = (min_amb, max_amb)
            thermal_analysis = self.thermal_calculator.calculate_complete_thermal_analysis(row, ambient_temps)
            result['thermal_analysis'] = thermal_analysis
            if not thermal_analysis['success']:
                return self._update_result_with_error(result, f"Thermal calculation failed: {thermal_analysis['error_message']}")
            cfm_required = thermal_analysis['cfm_required']
            candidates, trace3 = self.rule_engine.apply_rule_3_cfm(self.breather_catalog, cfm_required)
            result['rule_trace'].append(trace3)
            if candidates.empty: return self._update_result_with_error(result, f"No breathers found with CFM >= {cfm_required:.2f}")
            rule4_result = self.rule_engine.apply_operational_filters(candidates, row, config)
            candidates = rule4_result[0]; result['rule_trace'].extend(rule4_result[1])
            if candidates.empty: return self._update_result_with_error(result, "No breathers meet core operational requirements.")
            candidates, trace5 = self.rule_engine.apply_rule_5_sump(candidates, thermal_analysis['volumes'], 'splash')
            result['rule_trace'].append(f"{trace5} ({len(candidates)} of {len(rule4_result[0])} candidates remain).")
            if candidates.empty: return self._update_result_with_error(result, "No breathers meet sump volume requirements")
            space_str = row.get('(D) Breather/Fill Port Clearance')
            space_data_provided = pd.notna(space_str) and str(space_str).strip() != ''
            available_space = self._parse_available_space(space_str)
            rule6_result = self.rule_engine.apply_rule_6(candidates, available_space)
            rule7_result = self.rule_engine.apply_rule_7(rule6_result['fitting_breathers'], rule6_result['non_fitting_breathers'], available_space, space_data_provided, config, "", cfm_required=cfm_required, desiccant_required=True, v_oil=thermal_analysis.get('volumes', {}).get('v_oil', 0), system_type='splash')
            result['rule_trace'].extend([rule6_result['trace'], rule7_result['trace']])
            result.update({'selected_breather': rule7_result['selected_breather'], 'result_status': rule7_result['status'], 'installation_notes': rule7_result['installation_notes'], 'success': True if rule7_result.get('selected_breather') else False})
            return result
        except Exception as e:
            logger.error(f"Error processing record {row_index}: {str(e)}", exc_info=True)
            result['error_message'] = str(e)
        return result

    def _update_result_with_error(self, result, message):
        result['error_message'] = message; result['result_status'] = 'No Solution Found'
        return result
    
    def get_results_as_dataframe(self, export_config: Dict = None) -> pd.DataFrame:
        results_list = []
        config = export_config if export_config is not None else self.global_config
        include_trace = config.get('verbose_trace', False); include_calcs = config.get('include_calculations', False)
        for idx, result in self.results.items():
            row_data = {'original_index': idx}
            if result.get('selected_breather'):
                breather = result.get('selected_breather')[0]; thermal = result.get('thermal_analysis', {})
                row_data.update({'Breather_Brand': breather.get('Brand'), 'Breather_Model': breather.get('Model'), 'CFM_Required': thermal.get('cfm_required'), 'Result_Status': result.get('result_status'), 'Installation_Notes': result.get('installation_notes')})
                if include_trace: row_data['Verbose_Trace'] = "\n".join(result.get('rule_trace', []))
                if include_calcs:
                    volumes = thermal.get('volumes', {})
                    row_data.update({'Calc_V_Sump': volumes.get('v_sump', 0), 'Calc_V_Oil': volumes.get('v_oil', 0), 'Calc_V_Air': volumes.get('v_air', 0), 'Calc_Delta_T': thermal.get('delta_t', 0), 'Calc_Delta_V_Oil': thermal.get('delta_v_oil', 0), 'Calc_Delta_V_Air': thermal.get('delta_v_air', 0), 'Calc_V_Total_Exp': thermal.get('v_total_exp', 0), 'Calc_Safety_Factor': thermal.get('safety_factor_used', 1.4)})
            else:
                row_data.update({'Result_Status': result.get('result_status', 'Error'), 'Installation_Notes': result.get('error_message', 'Processing failed')})
                if include_trace: row_data['Verbose_Trace'] = "\n".join(result.get('rule_trace', []))
            results_list.append(row_data)
        if not results_list: return pd.DataFrame()
        return pd.DataFrame(results_list)
    
    def _parse_available_space(self, space_str: str) -> Dict[str, Optional[float]]:
        if pd.isna(space_str) or not str(space_str).strip(): return {'height_limit': None, 'diameter_limit': None}
        s_lower = str(space_str).lower()
        mappings = {'less than 2 inches': {'h': 2.0, 'd': 2.0}, '2 to <4 inches': {'h': 4.0, 'd': 4.0}, '4 to <6 inches': {'h': 6.0, 'd': 6.0}, 'greater than 6 inches': {'h': None, 'd': None}, 'no port available': {'h': 0.0, 'd': 0.0}}
        for key, limits in mappings.items():
            if key in s_lower: return {'height_limit': limits['h'], 'diameter_limit': limits['d']}
        return {'height_limit': None, 'diameter_limit': None}
    
    def _create_error_result(self, error_message: str) -> Dict:
        return {'success': False, 'error_message': error_message, 'result_status': 'Error', 'rule_trace': [f"Error: {error_message}"], 'selected_breather': [], 'installation_notes': 'Processing failed due to a critical error.'}