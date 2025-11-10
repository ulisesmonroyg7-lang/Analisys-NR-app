# --- core/data_processor.py ---
# VERSIÃ“N FINAL - CON DESCRIPCIONES EN INGLÃ‰S Y ADSORCIÃ“N EN FL. OZ

"""
Data Processor for NoRia Breather Selection - VERSIÃ“N CON VALIDACIÃ“N DE TEMPERATURAS
- MEJORA: Agregadas 3 columnas de descripciÃ³n tÃ©cnica (con AdsorciÃ³n en Fl. oz).
- MEJORA: Pasa el volumen del sumidero al Rule Engine para lÃ³gica condicional.
- CORRECCIÃ“N: Pasa el `system_type` al calculador tÃ©rmico para la lÃ³gica de Splash.
"""
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any

from .calculations import ThermalCalculator
from .rule_engine import RuleEngine
import logging
logger = logging.getLogger(__name__)

class DataProcessor:
    """Main data processor implementing the complete breather selection workflow"""
    
    def __init__(self, excel_handler, data_to_process: pd.DataFrame, global_config: Dict, overrides: Dict):
        self.excel_handler = excel_handler
        self.data_to_process = data_to_process
        self.global_config = global_config
        self.overrides = overrides
        self.thermal_calculator = ThermalCalculator()
        self.rule_engine = RuleEngine({})
        
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
                
                if final_config['min_amb_temp'] is None:
                    final_config['min_amb_temp'] = 60.0
                    logger.warning(f"Asset {idx}: min_amb_temp was None, set to 60.0Â°F")
                
                if final_config['max_amb_temp'] is None:
                    final_config['max_amb_temp'] = 80.0
                    logger.warning(f"Asset {idx}: max_amb_temp was None, set to 80.0Â°F")
                
                if idx in self.overrides:
                    for key, value in self.overrides[idx].items():
                        if value is not None:
                            final_config[key] = value
                
                self.results[idx] = self.process_single_record(row, idx, final_config)
                
            except Exception as e:
                logger.error(f"Critical error processing record index {idx}: {str(e)}")
                self.results[idx] = self._create_error_result(str(e))
        
        return self.results
    
    def process_single_record(self, row: pd.Series, row_index: int, config: Dict) -> Dict:
        result = {
            'success': False, 'row_index': row_index, 'rule_trace': [], 'thermal_analysis': {},
            'selected_breather': [], 'result_status': 'Failed', 'installation_notes': '', 'error_message': '',
            'rejected_candidates': [], 'operational_factors': {}, 'lcc_breather': None, 'cost_benefit_breather': None
        }
        
        if self.breather_catalog is None or self.breather_catalog.empty:
            return self._update_result_with_error(result, "Breather catalog is not loaded or is empty.")
        
        try:
            self.rule_engine.config = config
            self.thermal_calculator.safety_factor = config.get('safety_factor', 1.4)
            
            rule1_result = self.rule_engine.apply_rule_1(row, config)
            result['rule_trace'].append(f"Rule 1 ({config.get('criticality', 'N/A')}): {rule1_result['description']}")
            if not rule1_result['breather_required']:
                return {**result, 'result_status': 'No Breather Required', 'success': True}
            
            min_amb, max_amb = config.get('min_amb_temp'), config.get('max_amb_temp')
            ambient_temps = (min_amb, max_amb)
            
            # --- CORRECCIÃ“N: Especificar que este es un anÃ¡lisis de tipo 'splash' ---
            thermal_analysis = self.thermal_calculator.calculate_complete_thermal_analysis(row, ambient_temps, system_type='splash')
            result['thermal_analysis'] = thermal_analysis
            if not thermal_analysis['success']:
                return self._update_result_with_error(result, f"Thermal calculation failed: {thermal_analysis['error_message']}")
            
            cfm_required = thermal_analysis['cfm_required']
            v_oil = thermal_analysis.get('volumes', {}).get('v_oil', 0)
            volumes = thermal_analysis.get('volumes', {})
            result['rule_trace'].append(f"Rule 2: CFM required = {cfm_required:.2f}")
            
            factors = self.rule_engine._extract_operational_factors(row, config)
            result['operational_factors'] = factors
            desiccant_required = factors['desiccant_required']
            
            initial_candidates = self.rule_engine.apply_rule_3(self.breather_catalog, cfm_required)
            result['rule_trace'].append(f"Rule 3: {len(initial_candidates)} breathers meet CFM")
            if initial_candidates.empty:
                return self._update_result_with_error(result, f"No breathers found with CFM >= {cfm_required:.2f}")
            
            suboptimal_note = ""
            rule4_result = self.rule_engine.apply_rule_4(initial_candidates, row, config, volumes)
            candidate_breathers = rule4_result['filtered_breathers']
            self._log_rejections(result, initial_candidates, candidate_breathers, "Operational Context (Rule 4)")
            result['rule_trace'].extend(rule4_result['trace'])
            
            if candidate_breathers.empty:
                result['rule_trace'].append("(!) No optimal solution found. Trying sub-optimal fallbacks.")
                # NOTA: NUNCA relajar 'mobile' - debe mantenerse estricto
                fallback_attempts = [
                    ['vibration'],
                    ['oil_mist'],
                    ['vibration', 'oil_mist'],
                    ['esi'],
                    ['vibration', 'oil_mist', 'esi']
                ]
                for constraints in fallback_attempts:
                    rule4_fallback_result = self.rule_engine.apply_rule_4(initial_candidates, row, config, volumes, exclude_filters=constraints)
                    if not rule4_fallback_result['filtered_breathers'].empty:
                        candidate_breathers = rule4_fallback_result['filtered_breathers']
                        suboptimal_note = f"Sub-optimal: Requirements for {constraints} were relaxed."
                        result['rule_trace'].append(suboptimal_note)
                        break
            
            if candidate_breathers.empty:
                return self._update_result_with_error(result, "No breathers meet core operational requirements.")
            
            rule5_result = self.rule_engine.apply_rule_5(candidate_breathers, volumes, system_type='splash')
            candidates_after_rule5 = rule5_result['filtered_breathers']
            self._log_rejections(result, candidate_breathers, candidates_after_rule5, "Sump Volume (Rule 5)")
            result['rule_trace'].append(rule5_result['trace'])
            if candidates_after_rule5.empty:
                return self._update_result_with_error(result, "No breathers meet sump volume requirements")
            
            space_str = row.get('(D) Breather/Fill Port Clearance')
            space_data_provided = pd.notna(space_str) and str(space_str).strip() != ''
            available_space = self._parse_available_space(space_str)
            rule6_result = self.rule_engine.apply_rule_6(candidates_after_rule5, available_space)
            self._log_rejections(result, candidates_after_rule5, rule6_result['fitting_breathers'], "Available Space (Rule 6)")
            
            rule7_result = self.rule_engine.apply_rule_7(
                rule6_result['fitting_breathers'], rule6_result['non_fitting_breathers'], available_space,
                space_data_provided, config, suboptimal_note, cfm_required, desiccant_required, v_oil, 'splash'
            )
            result['rule_trace'].extend([rule6_result['trace'], rule7_result['trace']])
            result.update({
                'selected_breather': rule7_result['selected_breather'], 'result_status': rule7_result['status'],
                'installation_notes': rule7_result['installation_notes'], 'success': True
            })
            
            all_candidates = pd.concat([rule6_result['fitting_breathers'], rule6_result['non_fitting_breathers']])
            context = {'cfm_required': cfm_required, 'desiccant_required': desiccant_required, 'v_oil': v_oil, 'system_type': 'splash'}
            result['lcc_breather'] = self.rule_engine.select_lcc_breather(all_candidates, context)
            result['cost_benefit_breather'] = self.rule_engine.select_cost_benefit_breather(all_candidates, context)
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing record {row_index}: {str(e)}")
            return self._update_result_with_error(result, str(e))
    
    def _build_breather_description(self, breather_dict: Optional[Dict]) -> str:
        """Construye una descripciÃ³n tÃ©cnica en inglÃ©s, con formato y usando Fl. oz."""
        if not breather_dict or not isinstance(breather_dict, dict):
            return "N/A"
        
        try:
            cfm = f"{float(breather_dict.get('Max Air Flow (cfm)', 0)):.2f}"
            adsorption_oz_str = str(breather_dict.get('Adsorption Capacity (mL)', '0')).replace(',', '')
            adsorption_ml = float(adsorption_oz_str)
            adsorption_oz = adsorption_ml / 29.5735
            height = f"{float(breather_dict.get('Height (in)', 0)):.2f}"
            diameter = f"{float(breather_dict.get('Diameter (in)', 0)):.2f}"
        except (ValueError, TypeError):
            cfm, adsorption_oz, height, diameter = "N/A", 0.0, "N/A", "N/A"

        media = breather_dict.get('Filter media', 'N/A')
        vibration = "Yes" if breather_dict.get('High vibration', False) else "No"
        mobile = "Yes" if breather_dict.get('Mobile applications', False) else "No"
        valve = "Yes" if str(breather_dict.get('Check Valve', 'No')).strip().lower() == 'yes' else "No"

        return (f"CFM: {cfm} | Adsorption Capacity: {adsorption_oz:.2f} Fl. oz | Dimensions: {height}\"H x {diameter}\"D | "
                f"Filter Media: {media} | High Vibration: {vibration} | Mobile Application: {mobile} | Check Valve: {valve}")

    def _log_rejections(self, result: Dict, before_df: pd.DataFrame, after_df: pd.DataFrame, reason: str):
        if len(before_df) > len(after_df):
            rejected_df = before_df.loc[~before_df.index.isin(after_df.index)]
            for _, row in rejected_df.head(2).iterrows():
                result['rejected_candidates'].append({'model': f"{row.get('Brand')} {row.get('Model')}", 'reason': reason})
    
    def _update_result_with_error(self, result, message):
        result['error_message'] = message
        result['result_status'] = 'No Solution Found'
        result['installation_notes'] = 'No suitable breathers found that meet all technical requirements.'
        return result
    
    def get_results_as_dataframe(self, export_config: Dict = None) -> pd.DataFrame:
        results_list = []
        config = export_config if export_config is not None else self.global_config
        include_trace = config.get('verbose_trace', False)
        include_calcs = config.get('include_calculations', False)
        
        for idx, result in self.results.items():
            row_data = {'original_index': idx}
            
            if result.get('selected_breather'):
                breather = result['selected_breather'][0]
                thermal = result.get('thermal_analysis', {})
                cfm_required = thermal.get('cfm_required', 0)
                lcc_breather = result.get('lcc_breather')
                cost_benefit_breather = result.get('cost_benefit_breather')
                
                row_data.update({
                    'Breather_Brand': breather.get('Brand'),
                    'Breather_Model': breather.get('Model'),
                    'Default_Breather_Desc': self._build_breather_description(breather),
                    'LCC_Brand': lcc_breather.get('Brand') if lcc_breather else 'N/A',
                    'LCC_Model': lcc_breather.get('Model') if lcc_breather else 'N/A',
                    'LCC_Breather_Desc': self._build_breather_description(lcc_breather),
                    'Cost_Benefit_Brand': cost_benefit_breather.get('Brand') if cost_benefit_breather else 'N/A',
                    'Cost_Benefit_Model': cost_benefit_breather.get('Model') if cost_benefit_breather else 'N/A',
                    'Cost_Benefit_Breather_Desc': self._build_breather_description(cost_benefit_breather),
                    'CFM_Required': cfm_required,
                    'Installation_Notes': result.get('installation_notes')
                })
                
                if include_trace:
                    row_data['Verbose_Trace'] = " -> ".join(result.get('rule_trace', []))
                
                if include_calcs:
                    volumes = thermal.get('volumes', {})
                    row_data.update({
                        'Calc_V_Sump': volumes.get('v_sump', 0), 'Calc_V_Oil': volumes.get('v_oil', 0),
                        'Calc_V_Air': volumes.get('v_air', 0), 'Calc_Delta_T': thermal.get('delta_t', 0),
                        'Calc_Delta_V_Oil': thermal.get('delta_v_oil', 0), 'Calc_Delta_V_Air': thermal.get('delta_v_air', 0),
                        'Calc_V_Total_Exp': thermal.get('v_total_exp', 0), 'Calc_Safety_Factor': thermal.get('safety_factor_used', 1.4)
                    })
            else:
                row_data.update({
                    'Installation_Notes': result.get('error_message', 'Processing failed')
                })
                if include_trace:
                    row_data['Verbose_Trace'] = " -> ".join(result.get('rule_trace', []))
            
            results_list.append(row_data)
        
        if not results_list: return pd.DataFrame()
        return pd.DataFrame(results_list)
    
    def _parse_available_space(self, space_str: str) -> Dict[str, Optional[float]]:
        if pd.isna(space_str) or not str(space_str).strip():
            return {'height_limit': None, 'diameter_limit': None}
        
        s_lower = str(space_str).lower()
        mappings = {
            'less than 2 inches': {'h': 2.0, 'd': 2.0}, '2 to <4 inches': {'h': 4.0, 'd': 4.0},
            '4 to <6 inches': {'h': 6.0, 'd': 6.0}, 'greater than 6 inches': {'h': None, 'd': None},
            'no port available': {'h': 0.0, 'd': 0.0}
        }
        for key, limits in mappings.items():
            if key in s_lower: return {'height_limit': limits['h'], 'diameter_limit': limits['d']}
        return {'height_limit': None, 'diameter_limit': None}
    
    def _create_error_result(self, error_message: str) -> Dict:
        return {
            'success': False, 'error_message': error_message, 'result_status': 'Error',
            'rule_trace': [f"Error: {error_message}"], 'selected_breather': [],
            'installation_notes': 'Processing failed due to a critical error.', 'operational_factors': {},
            'lcc_breather': None, 'cost_benefit_breather': None
        }