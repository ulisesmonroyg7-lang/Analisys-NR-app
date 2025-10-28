# --- core/data_processor.py ---

"""
Data Processor for NoRia Breather Selection - VERSIÓN CON VALIDACIÓN DE TEMPERATURAS
- CORREGIDO: Garantiza que siempre haya temperaturas ambientales válidas antes del cálculo térmico
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
        
        # Obtiene el catálogo completo
        self.breather_catalog = excel_handler.get_breather_catalog()
        self.results = {}

        # Lógica de filtrado de marca
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
                # Construir configuración final con defaults garantizados
                final_config = self.global_config.copy()
                
                # VALIDACIÓN CRÍTICA: Asegurar que las temperaturas ambientales NUNCA sean None
                final_config.setdefault('min_amb_temp', 60.0)
                final_config.setdefault('max_amb_temp', 80.0)
                
                # Si por alguna razón son None, forzar defaults
                if final_config['min_amb_temp'] is None:
                    final_config['min_amb_temp'] = 60.0
                    logger.warning(f"Asset {idx}: min_amb_temp was None, set to 60.0°F")
                
                if final_config['max_amb_temp'] is None:
                    final_config['max_amb_temp'] = 80.0
                    logger.warning(f"Asset {idx}: max_amb_temp was None, set to 80.0°F")
                
                # Aplicar overrides si existen
                if idx in self.overrides:
                    for key, value in self.overrides[idx].items():
                        if value is not None:
                            final_config[key] = value
                
                # Procesar el registro
                self.results[idx] = self.process_single_record(row, idx, final_config)
                
            except Exception as e:
                logger.error(f"Critical error processing record index {idx}: {str(e)}")
                self.results[idx] = self._create_error_result(str(e))
        
        return self.results
    
    def process_single_record(self, row: pd.Series, row_index: int, config: Dict) -> Dict:
        result = {
            'success': False,
            'row_index': row_index,
            'rule_trace': [],
            'thermal_analysis': {},
            'selected_breather': [],
            'result_status': 'Failed',
            'installation_notes': '',
            'error_message': '',
            'rejected_candidates': []
        }
        
        if self.breather_catalog is None or self.breather_catalog.empty:
            error_msg = "Breather catalog is not loaded or is empty. Analysis cannot continue."
            logger.error(error_msg)
            return self._update_result_with_error(result, error_msg)
        
        try:
            self.rule_engine.config = config
            self.thermal_calculator.safety_factor = config.get('safety_factor', 1.4)
            
            # Rule 1: Check criticality
            rule1_result = self.rule_engine.apply_rule_1(row, config)
            result['rule_trace'].append(f"Rule 1 ({config.get('criticality', 'N/A')}): {rule1_result['description']}")
            
            if not rule1_result['breather_required']:
                result.update({
                    'result_status': 'No Breather Required',
                    'success': True
                })
                return result
            
            # VALIDACIÓN CRÍTICA: Temperaturas ambientales
            min_amb = config.get('min_amb_temp')
            max_amb = config.get('max_amb_temp')
            
            # Log de debug para diagnóstico
            logger.info(f"Asset {row_index} - Ambient temps: min={min_amb}°F, max={max_amb}°F")
            
            # Si alguna es None, usar defaults y registrar warning
            if min_amb is None or max_amb is None:
                min_amb = 60.0
                max_amb = 80.0
                logger.warning(f"Asset {row_index}: Ambient temps were None, using defaults: {min_amb}-{max_amb}°F")
            
            ambient_temps = (min_amb, max_amb)
            
            # Rule 2: Thermal analysis
            thermal_analysis = self.thermal_calculator.calculate_complete_thermal_analysis(row, ambient_temps)
            result['thermal_analysis'] = thermal_analysis
            
            if not thermal_analysis['success']:
                return self._update_result_with_error(result, f"Thermal calculation failed: {thermal_analysis['error_message']}")
            
            cfm_required = thermal_analysis['cfm_required']
            v_oil = thermal_analysis.get('volumes', {}).get('v_oil', 0)
            
            result['rule_trace'].append(f"Rule 2: CFM required = {cfm_required:.2f}")
            
            # Extract operational factors
            factors = self.rule_engine._extract_operational_factors(row, config)
            desiccant_required = factors['desiccant_required']
            
            # Rule 3: Filter by CFM
            initial_candidates = self.rule_engine.apply_rule_3(self.breather_catalog, cfm_required)
            result['rule_trace'].append(f"Rule 3: {len(initial_candidates)} breathers meet CFM")
            
            if initial_candidates.empty:
                return self._update_result_with_error(result, f"No breathers found with CFM >= {cfm_required:.2f} (even after fallback)")
            
            suboptimal_note = ""
            
            # Rule 4: Operational requirements
            rule4_result = self.rule_engine.apply_rule_4(initial_candidates, row, config)
            candidate_breathers = rule4_result['filtered_breathers']
            
            self._log_rejections(result, initial_candidates, candidate_breathers, "Operational Context (Rule 4)")
            result['rule_trace'].extend(rule4_result['trace'])
            
            # Fallback logic if no optimal solution
            if candidate_breathers.empty:
                result['rule_trace'].append("(!) No optimal solution found. Trying sub-optimal fallbacks.")
                fallback_order = ['vibration', 'oil_mist']
                
                for constraint_to_relax in fallback_order:
                    rule4_fallback_result = self.rule_engine.apply_rule_4(
                        initial_candidates, row, config, 
                        exclude_filters=[constraint_to_relax]
                    )
                    if not rule4_fallback_result['filtered_breathers'].empty:
                        candidate_breathers = rule4_fallback_result['filtered_breathers']
                        suboptimal_note = f"Sub-optimal: Requirement for '{constraint_to_relax}' was ignored."
                        break
            
            if candidate_breathers.empty:
                return self._update_result_with_error(result, "No breathers meet core operational requirements.")
            
            # Rule 5: Sump volume
            rule5_result = self.rule_engine.apply_rule_5(candidate_breathers, thermal_analysis['volumes'], system_type='splash')
            candidates_after_rule5 = rule5_result['filtered_breathers']
            
            self._log_rejections(result, candidate_breathers, candidates_after_rule5, "Sump Volume (Rule 5)")
            result['rule_trace'].append(rule5_result['trace'])
            
            if candidates_after_rule5.empty:
                return self._update_result_with_error(result, "No breathers meet sump volume requirements")
            
            # Rule 6: Available space
            space_str = row.get('(D) Breather/Fill Port Clearance')
            space_data_provided = pd.notna(space_str) and str(space_str).strip() != ''
            available_space = self._parse_available_space(space_str)
            
            rule6_result = self.rule_engine.apply_rule_6(candidates_after_rule5, available_space)
            
            self._log_rejections(result, candidates_after_rule5, rule6_result['fitting_breathers'], "Available Space (Rule 6)")
            
            # Rule 7: Final recommendation
            rule7_result = self.rule_engine.apply_rule_7(
                rule6_result['fitting_breathers'],
                rule6_result['non_fitting_breathers'],
                available_space,
                space_data_provided,
                config,
                suboptimal_note,
                cfm_required=cfm_required,
                desiccant_required=desiccant_required,
                v_oil=v_oil,
                system_type='splash'
            )
            
            result['rule_trace'].extend([rule6_result['trace'], rule7_result['trace']])
            
            result.update({
                'selected_breather': rule7_result['selected_breather'],
                'result_status': rule7_result['status'],
                'installation_notes': rule7_result['installation_notes'],
                'success': True
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing record {row_index}: {str(e)}")
            result['error_message'] = str(e)
        
        return result
    
    def _log_rejections(self, result: Dict, before_df: pd.DataFrame, after_df: pd.DataFrame, reason: str):
        """Log rejected candidates for AI analysis"""
        if len(before_df) > len(after_df):
            rejected_df = before_df.loc[~before_df.index.isin(after_df.index)]
            for _, row in rejected_df.head(2).iterrows():
                result['rejected_candidates'].append({
                    'model': f"{row.get('Brand')} {row.get('Model')}",
                    'reason': reason
                })
    
    def _update_result_with_error(self, result, message):
        """Update result with error information"""
        result['error_message'] = message
        result['result_status'] = 'No Solution Found'
        result['installation_notes'] = 'No suitable breathers found that meet all technical requirements.'
        return result
    
    def get_results_as_dataframe(self, export_config: Dict = None) -> pd.DataFrame:
        """Convert results to DataFrame for export
        
        Args:
            export_config: Configuration dict with export options (verbose_trace, include_calculations)
                          If None, uses self.global_config
        """
        results_list = []
        
        # Usar la config pasada como parámetro, o la global como fallback
        config = export_config if export_config is not None else self.global_config
        
        include_trace = config.get('verbose_trace', False)
        include_calcs = config.get('include_calculations', False)
        
        for idx, result in self.results.items():
            row_data = {'original_index': idx}
            
            if result.get('selected_breather'):
                breather = result.get('selected_breather')[0]
                thermal = result.get('thermal_analysis', {})
                
                row_data.update({
                    'Breather_Brand': breather.get('Brand'),
                    'Breather_Model': breather.get('Model'),
                    'CFM_Required': thermal.get('cfm_required'),
                    'Result_Status': result.get('result_status'),
                    'Installation_Notes': result.get('installation_notes')
                })
                
                # Agregar trazada verbose si está activada
                if include_trace:
                    row_data['Verbose_Trace'] = " -> ".join(result.get('rule_trace', []))
                
                # Agregar cálculos intermedios si está activado
                if include_calcs:
                    volumes = thermal.get('volumes', {})
                    row_data.update({
                        'Calc_V_Sump': volumes.get('v_sump', 0),
                        'Calc_V_Oil': volumes.get('v_oil', 0),
                        'Calc_V_Air': volumes.get('v_air', 0),
                        'Calc_Delta_T': thermal.get('delta_t', 0),
                        'Calc_Delta_V_Oil': thermal.get('delta_v_oil', 0),
                        'Calc_Delta_V_Air': thermal.get('delta_v_air', 0),
                        'Calc_V_Total_Exp': thermal.get('v_total_exp', 0),
                        'Calc_Safety_Factor': thermal.get('safety_factor_used', 1.4)
                    })
            else:
                row_data.update({
                    'Result_Status': result.get('result_status', 'Error'),
                    'Installation_Notes': result.get('error_message', 'Processing failed')
                })
                
                # Incluir trazada incluso en fallos
                if include_trace:
                    row_data['Verbose_Trace'] = " -> ".join(result.get('rule_trace', []))
            
            results_list.append(row_data)
        
        if not results_list:
            return pd.DataFrame()
        
        return pd.DataFrame(results_list)
    
    def _parse_available_space(self, space_str: str) -> Dict[str, Optional[float]]:
        """Parse available space string into limits"""
        if pd.isna(space_str) or not str(space_str).strip():
            return {'height_limit': None, 'diameter_limit': None}
        
        s_lower = str(space_str).lower()
        
        mappings = {
            'less than 2 inches': {'h': 2.0, 'd': 2.0},
            '2 to <4 inches': {'h': 4.0, 'd': 4.0},
            '4 to <6 inches': {'h': 6.0, 'd': 6.0},
            'greater than 6 inches': {'h': None, 'd': None},
            'no port available': {'h': 0.0, 'd': 0.0}
        }
        
        for key, limits in mappings.items():
            if key in s_lower:
                return {'height_limit': limits['h'], 'diameter_limit': limits['d']}
        
        return {'height_limit': None, 'diameter_limit': None}
    
    def _create_error_result(self, error_message: str) -> Dict:
        """Create error result structure"""
        return {
            'success': False,
            'error_message': error_message,
            'result_status': 'Error',
            'rule_trace': [f"Error: {error_message}"],
            'selected_breather': [],
            'installation_notes': 'Processing failed due to a critical error.'
        }