# core/data_processor.py (FINAL and COMPLETE version - Handles row-specific ambient temperatures)

import pandas as pd
from typing import Dict, List, Optional

from .calculations import ThermalCalculator
from .rule_engine import RuleEngine
from utils.excel_handler import ExcelHandler
import logging

logger = logging.getLogger(__name__)

class DataProcessor:
    """Main data processor implementing the complete breather selection workflow for Splash/Oil Bath."""
    
    def __init__(self, excel_handler: ExcelHandler, data_to_process: pd.DataFrame, global_config: Dict, overrides: Dict):
        self.excel_handler = excel_handler
        self.data_to_process = data_to_process
        self.global_config = global_config
        self.overrides = overrides
        self.thermal_calculator = ThermalCalculator()
        self.rule_engine = RuleEngine({})
        
        self.breather_catalog = excel_handler.get_breather_catalog()
        self.results = {}

        brand_to_filter = global_config.get('brand_filter')
        if brand_to_filter and brand_to_filter != "All Brands" and not self.breather_catalog.empty:
            logger.info(f"Applying brand filter: Only using '{brand_to_filter}' products.")
            self.breather_catalog = self.breather_catalog[self.breather_catalog['Brand'] == brand_to_filter].copy()
            if self.breather_catalog.empty:
                logger.warning(f"No breathers found for the selected brand '{brand_to_filter}'. Analysis might fail.")

    def process_all_records(self) -> Dict:
        """Processes all records in the provided DataFrame."""
        for idx, row in self.data_to_process.iterrows():
            try:
                # Start with a copy of global config
                final_config = self.global_config.copy()
                
                # Apply any row-specific overrides from the UI
                if idx in self.overrides:
                    for key, value in self.overrides[idx].items():
                        if value is not None:
                            final_config[key] = value
                
                self.results[idx] = self.process_single_record(row, idx, final_config)
                
            except Exception as e:
                logger.error(f"Critical error processing record index {idx}: {str(e)}")
                self.results[idx] = self._create_error_result(f"Critical error: {str(e)}")
        
        return self.results
    
    def process_single_record(self, row: pd.Series, row_index: int, config: Dict) -> Dict:
        """Processes a single asset row through the entire analysis workflow."""
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
            
            # Rule 1: Breather Requirement Check (now uses data from the DataFrame)
            criticity_from_data = row.get('Criticality', 'A') # Fallback to 'A' if column somehow missing
            
            # To use the rule engine consistently, we temporarily put the data-driven criticality into the config for the rule.
            temp_config_for_rule1 = config.copy()
            temp_config_for_rule1['criticality'] = criticity_from_data
            
            rule1_result = self.rule_engine.apply_rule_1(row, temp_config_for_rule1)
            result['rule_trace'].append(f"Rule 1 ({criticity_from_data}): {rule1_result['description']}")
            if not rule1_result['breather_required']:
                return {**result, 'result_status': 'No Breather Required', 'success': True}

            # Ambient Temperature Logic: Use row-specific data if enabled, otherwise use global config.
            min_amb, max_amb = config.get('min_amb_temp'), config.get('max_amb_temp')
            if config.get('use_ambient_temp_column'):
                amb_temp_str = row.get('(D) Ambient Temperature')
                if pd.notna(amb_temp_str) and amb_temp_str:
                    min_row_amb, max_row_amb = self.thermal_calculator.extract_temperatures(str(amb_temp_str))
                    if min_row_amb is not None and max_row_amb is not None:
                        min_amb, max_amb = min_row_amb, max_row_amb
                        result['rule_trace'].append(f"Info: Using ambient temperature from data row: '{amb_temp_str}'")
            
            ambient_temps = (min_amb, max_amb)
            
            # Rule 2: Thermal Calculation
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
            
            # Rule 3: Initial CFM Filtering
            initial_candidates = self.rule_engine.apply_rule_3(self.breather_catalog, cfm_required)
            result['rule_trace'].append(f"Rule 3: {len(initial_candidates)} breathers meet CFM")
            if initial_candidates.empty:
                return self._update_result_with_error(result, f"No breathers found with CFM >= {cfm_required:.2f}")
            
            # Rule 4: Operational Context Filtering
            rule4_result = self.rule_engine.apply_rule_4(initial_candidates, row, config, volumes)
            candidate_breathers = rule4_result['filtered_breathers']
            result['rule_trace'].extend(rule4_result['trace'])
            if candidate_breathers.empty:
                return self._update_result_with_error(result, "No breathers meet core operational requirements.")
            
            # Rule 5: Sump Volume Filtering
            rule5_result = self.rule_engine.apply_rule_5(candidate_breathers, volumes, system_type='splash')
            candidate_breathers = rule5_result['filtered_breathers']
            result['rule_trace'].append(rule5_result['trace'])
            if candidate_breathers.empty:
                return self._update_result_with_error(result, "No breathers meet sump volume requirements.")

            # Final Selection Logic
            context = {'cfm_required': cfm_required, 'v_oil': v_oil, 'system_type': 'splash'}
            selected = self.rule_engine._rank_and_select_best_breather(candidate_breathers, context)
            
            if selected:
                result['selected_breather'] = [selected]
                result['lcc_breather'] = self.rule_engine.select_lcc_breather(candidate_breathers, context)
                result['cost_benefit_breather'] = self.rule_engine.select_cost_benefit_breather(candidate_breathers, context)
                result['success'] = True
                result['result_status'] = 'Optimal'
                result['installation_notes'] = 'Direct installation. Verify space constraints.'
            else:
                result['error_message'] = 'No suitable breather found after all rules were applied.'

            return result
            
        except Exception as e:
            logger.error(f"Error processing record {row_index}: {str(e)}")
            return self._update_result_with_error(result, f"Unexpected error: {str(e)}")
    
    def _update_result_with_error(self, result, message):
        result['error_message'] = message
        result['result_status'] = 'No Solution Found'
        result['installation_notes'] = 'No suitable breathers found that meet all technical requirements.'
        return result
    
    def _create_error_result(self, error_message: str) -> Dict:
        return {
            'success': False, 'error_message': error_message, 'result_status': 'Error',
            'rule_trace': [f"Error: {error_message}"], 'selected_breather': [],
            'installation_notes': 'Processing failed due to a critical error.', 'operational_factors': {},
            'lcc_breather': None, 'cost_benefit_breather': None
        }
    
    def _build_breather_description(self, breather_dict: Optional[Dict]) -> str:
        if not breather_dict or not isinstance(breather_dict, dict): return "N/A"
        try:
            cfm = f"{float(breather_dict.get('Max Air Flow (cfm)', 0)):.2f}"
            adsorption_ml_str = str(breather_dict.get('Adsorption Capacity (mL)', '0')).replace(',', '')
            adsorption_oz = float(adsorption_ml_str) / 29.5735
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
    
    def get_results_as_dataframe(self) -> pd.DataFrame:
        results_list = []
        include_trace = self.global_config.get('verbose_trace', False)
        include_calcs = self.global_config.get('include_calculations', False)
        
        for idx, result in self.results.items():
            row_data = {'original_index': idx}
            
            if result.get('success') and result.get('selected_breather'):
                breather = result['selected_breather'][0]
                thermal = result.get('thermal_analysis', {})
                lcc_breather = result.get('lcc_breather')
                cost_benefit_breather = result.get('cost_benefit_breather')
                
                row_data.update({
                    'Breather_Brand': breather.get('Brand'), 'Breather_Model': breather.get('Model'),
                    'Default_Breather_Desc': self._build_breather_description(breather),
                    'LCC_Model': (lcc_breather or {}).get('Model', 'N/A'),
                    'LCC_Breather_Desc': self._build_breather_description(lcc_breather),
                    'Cost_Benefit_Model': (cost_benefit_breather or {}).get('Model', 'N/A'),
                    'Cost_Benefit_Breather_Desc': self._build_breather_description(cost_benefit_breather),
                    'CFM_Required': thermal.get('cfm_required'),
                    'Installation_Notes': result.get('installation_notes')
                })
                
                if include_trace:
                    row_data['Verbose_Trace'] = " -> ".join(result.get('rule_trace', []))
                
                if include_calcs:
                    volumes = thermal.get('volumes', {})
                    row_data.update({
                        'Calc_V_Sump': volumes.get('v_sump'), 'Calc_V_Oil': volumes.get('v_oil'),
                        'Calc_V_Air': volumes.get('v_air'), 'Calc_Delta_T': thermal.get('delta_t'),
                        'Calc_Delta_V_Oil': thermal.get('delta_v_oil'), 'Calc_Delta_V_Air': thermal.get('delta_v_air'),
                        'Calc_V_Total_Exp': thermal.get('v_total_exp'), 'Calc_Safety_Factor': thermal.get('safety_factor_used')
                    })
            else:
                row_data['Installation_Notes'] = result.get('error_message', 'Processing failed')
            
            results_list.append(row_data)
        
        if not results_list: return pd.DataFrame()
        return pd.DataFrame(results_list)