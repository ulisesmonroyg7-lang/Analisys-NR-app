# core/circulating_processor.py (FINAL and COMPLETE version with LCC/Cost-Benefit logic)

import pandas as pd
from typing import Dict, List, Optional

from .rule_engine import RuleEngine
from .calculations import ThermalCalculator
from utils.excel_handler import ExcelHandler
import logging

logger = logging.getLogger(__name__)

class CirculatingSystemsDataProcessor:
    LPM_TO_GPM_FACTOR = 0.264172
    
    def __init__(self, excel_handler: ExcelHandler, global_config: Dict, overrides: Dict):
        self.excel_handler = excel_handler
        self.global_config = global_config
        self.overrides = overrides
        self.rule_engine = RuleEngine(global_config)
        self.thermal_calculator = ThermalCalculator()
        self.results = {}
        self.full_dataset = self.excel_handler.get_all_data()
        
        if not self.full_dataset.empty:
            self.machine_col = self.full_dataset.columns[1]
            self.maint_point_col = self.full_dataset.columns[8]
        
        self.breather_catalog = self.excel_handler.get_breather_catalog()
        brand_to_filter = global_config.get('brand_filter')
        if brand_to_filter and brand_to_filter != "All Brands" and not self.breather_catalog.empty:
            self.breather_catalog = self.breather_catalog[self.breather_catalog['Brand'] == brand_to_filter].copy()

    def _convert_to_gpm(self, flow_value: float, flow_unit: str) -> float:
        if pd.isna(flow_value) or flow_value <= 0: return 0.0
        return flow_value * self.LPM_TO_GPM_FACTOR if 'lpm' in str(flow_unit).lower().strip() else flow_value

    def _find_pump_siblings(self, target_machine: str, current_index: int) -> List[Dict]:
        if self.full_dataset.empty: return []
        siblings = []
        machine_siblings = self.full_dataset[self.full_dataset[self.machine_col].astype(str).str.strip() == str(target_machine).strip()]
        for idx, row in machine_siblings.iterrows():
            if idx == current_index: continue
            maint_point = str(row[self.maint_point_col]).lower()
            if 'pump' in maint_point:
                flow_rate = row.get('(D) Flow Rate')
                flow_unit = row.get('(DU) Flow Rate', 'gpm')
                if pd.notna(flow_rate) and float(flow_rate) > 0:
                    siblings.append({'flow_rate': float(flow_rate), 'flow_unit': flow_unit})
        return siblings

    def analyze_flow_data_availability(self, data_to_process: pd.DataFrame) -> Dict:
        analysis = {'total_records': len(data_to_process), 'with_cross_reference': 0, 'with_estimation': 0}
        for idx, row in data_to_process.iterrows():
            machine_name = str(row.get(self.machine_col, '')).strip()
            siblings = self._find_pump_siblings(machine_name, idx) if machine_name else []
            analysis['with_cross_reference' if siblings else 'with_estimation'] += 1
        return analysis

    def calculate_gpm_and_cfm(self, row: pd.Series, row_index: int, final_config: dict) -> Dict:
        if final_config.get('enable_manual_gpm') and final_config.get('manual_gpm_override', 0) > 0:
            manual_gpm = final_config['manual_gpm_override']
            cfm_required = (manual_gpm / 7.48) * 1.4
            return {'cfm_required': cfm_required, 'total_flow': manual_gpm, 'calculation_method': f"Manual Override ({manual_gpm} GPM)"}
        total_flow_gpm, method = 0.0, "Error"
        machine_name = str(row.get(self.machine_col, '')).strip()
        if machine_name:
            siblings = self._find_pump_siblings(machine_name, row_index)
            if siblings:
                total_flow_gpm = sum(self._convert_to_gpm(s['flow_rate'], s['flow_unit']) for s in siblings)
                method = f"Cross-Reference ({len(siblings)} pumps)"
        if total_flow_gpm == 0:
            oil_cap_liters = row.get('(D) Oil Capacity')
            if pd.notna(oil_cap_liters) and oil_cap_liters > 0:
                total_flow_gpm = (oil_cap_liters / 3.0) * self.LPM_TO_GPM_FACTOR
                method = f"Estimated from Oil Capacity ({oil_cap_liters:.1f} L)"
        if total_flow_gpm <= 0:
            total_flow_gpm = 15.0
            method = "Safety Minimum (15 GPM)"
        cfm_required = (total_flow_gpm / 7.48) * 1.4
        return {'cfm_required': cfm_required, 'total_flow': total_flow_gpm, 'calculation_method': method}

    def process_all_records(self, data_to_process: pd.DataFrame) -> Dict:
        for idx, row in data_to_process.iterrows():
            final_config = self.global_config.copy()
            if idx in self.overrides:
                final_config.update(self.overrides[idx])
            self.results[idx] = self._process_single_record(row, idx, final_config)
        return self.results

    def _process_single_record(self, row: pd.Series, row_index: int, final_config: Dict) -> Dict:
        result = {'success': False, 'row_index': row_index, 'rule_trace': [], 'flow_analysis': {}, 'selected_breather': [], 'result_status': 'Failed', 'installation_notes': '', 'error_message': '', 'gpm_analysis': {}, 'lcc_breather': None, 'cost_benefit_breather': None}
        try:
            self.rule_engine.config = final_config
            rule1 = self.rule_engine.apply_rule_1(row, final_config)
            result['rule_trace'].append(f"Rule 1 ({final_config.get('criticality', 'A')}): {rule1['description']}")
            if not rule1['breather_required']:
                return {**result, 'result_status': 'No Breather Required', 'success': True}

            flow_analysis = self.calculate_gpm_and_cfm(row, row_index, final_config)
            result['flow_analysis'] = flow_analysis
            cfm_required, asset_gpm = flow_analysis['cfm_required'], flow_analysis['total_flow']
            result['rule_trace'].append(f"Rule 2 (GPM-based): CFM required = {cfm_required:.2f} from {asset_gpm:.1f} GPM ({flow_analysis['calculation_method']})")

            volumes = self.thermal_calculator.calculate_volumes(row, system_type='circulating')
            v_oil = volumes.get('v_oil', 0)
            
            candidates = self.breather_catalog.copy()
            if candidates.empty: return {**result, 'error_message': 'Breather catalog is empty or filtered out.'}
            
            gpm_col = 'Max Fluid Flow (gpm)'
            if gpm_col in candidates.columns:
                candidates[gpm_col] = pd.to_numeric(candidates[gpm_col], errors='coerce')
                candidates = candidates[candidates[gpm_col] >= asset_gpm].copy()
                result['rule_trace'].append(f"Rule 2.5: Filter by Breather GPM >= {asset_gpm:.1f}. {len(candidates)} candidates remain.")
                if candidates.empty: return {**result, 'error_message': 'No breathers support required GPM.'}
            
            candidates = self.rule_engine.apply_rule_3(candidates, cfm_required)
            result['rule_trace'].append(f"Rule 3: Filter by CFM >= {cfm_required:.2f}. {len(candidates)} remain.")
            if candidates.empty: return {**result, 'error_message': 'No breathers meet minimum CFM.'}
            
            rule4_result = self.rule_engine.apply_rule_4(candidates, row, final_config, volumes)
            candidates = rule4_result['filtered_breathers']
            result['rule_trace'].extend(rule4_result['trace'])
            if candidates.empty: return {**result, 'error_message': 'No breathers meet operational requirements.'}

            rule5_result = self.rule_engine.apply_rule_5(candidates, volumes, system_type='circulating')
            candidates = rule5_result['filtered_breathers']
            result['rule_trace'].append(rule5_result['trace'])
            if candidates.empty: return {**result, 'error_message': 'No breathers meet sump volume requirements.'}

            context = {'cfm_required': cfm_required, 'v_oil': v_oil, 'system_type': 'circulating'}
            selected = self.rule_engine._rank_and_select_best_breather(candidates, context)
            
            if selected:
                result['selected_breather'] = [selected]
                # --- CORRECCIÓN: Añadir las llamadas a LCC y Cost-Benefit ---
                result['lcc_breather'] = self.rule_engine.select_lcc_breather(candidates, context)
                result['cost_benefit_breather'] = self.rule_engine.select_cost_benefit_breather(candidates, context)

                breather_gpm = selected.get(gpm_col)
                if pd.notna(breather_gpm) and asset_gpm > 0:
                    result['gpm_analysis'] = {'gpm_margin': breather_gpm / asset_gpm, 'breather_max_gpm': breather_gpm}
                result['success'] = True
                result['result_status'] = 'Optimal'
                result['installation_notes'] = 'Direct installation recommended. Verify space constraints.'
            else:
                result['error_message'] = 'No suitable breather found after all rules.'

            return result
        except Exception as e:
            result['error_message'] = str(e)
            return result

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
            flow = result.get('flow_analysis', {})
            gpm_analysis = result.get('gpm_analysis', {})
            
            if result.get('success') and result.get('selected_breather'):
                breather = result['selected_breather'][0]
                lcc_breather = result.get('lcc_breather')
                cost_benefit_breather = result.get('cost_benefit_breather')
                
                row_data.update({
                    'Breather_Brand': breather.get('Brand'), 'Breather_Model': breather.get('Model'),
                    'Default_Breather_Desc': self._build_breather_description(breather),
                    'LCC_Model': lcc_breather.get('Model') if lcc_breather else 'N/A',
                    'LCC_Breather_Desc': self._build_breather_description(lcc_breather),
                    'Cost_Benefit_Model': cost_benefit_breather.get('Model') if cost_benefit_breather else 'N/A',
                    'Cost_Benefit_Breather_Desc': self._build_breather_description(cost_benefit_breather),
                    'CFM_Required': flow.get('cfm_required'),
                    'Flow_Rate_GPM': flow.get('total_flow'),
                    'GPM_Source': flow.get('calculation_method'),
                    'Breather_Max_GPM': gpm_analysis.get('breather_max_gpm'),
                    'GPM_Margin': gpm_analysis.get('gpm_margin'),
                    'Installation_Notes': result.get('installation_notes')
                })
            else:
                row_data['Installation_Notes'] = result.get('error_message', 'Processing failed')
            
            if include_trace:
                row_data['Verbose_Trace'] = " -> ".join(result.get('rule_trace', []))
            if include_calcs:
                row_data['Calc_GPM_to_CFM'] = f"({flow.get('total_flow', 0):.2f} GPM / 7.48) * 1.4 = {flow.get('cfm_required', 0):.2f} CFM"
            
            results_list.append(row_data)
        
        return pd.DataFrame(results_list)