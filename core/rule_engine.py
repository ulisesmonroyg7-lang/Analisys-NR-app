# core/rule_engine.py (Versión con Jerarquía Corregida y Ranking por Sílica)

import pandas as pd
import numpy as np
import re
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)

class RuleEngine:
    CI_MATRIX = {'Low': 'Low', 'Medium': 'Medium', 'Severe': 'High', 'Extreme': 'High'}
    WCCI_MATRIX = {
        'No Water Contact, Very Dry Conditions': {'factor': 'Very Low', 'desiccant': False},
        'No Water Contact, Typical Humidity': {'factor': 'Low', 'desiccant': True},
        'Typical Humidity, but Occasional Rain': {'factor': 'Medium', 'desiccant': True},
        'Nearby Steam/Spray': {'factor': 'Medium', 'desiccant': True},
        'Other Mild Water Contact': {'factor': 'Medium', 'desiccant': True},
        'Other Moderate Water Contact': {'factor': 'Medium', 'desiccant': True},
        'Occasional Washdowns': {'factor': 'High', 'desiccant': True},
        'Severe Water Contact': {'factor': 'High', 'desiccant': True},
        'Submerged in Water': {'factor': 'High', 'desiccant': True}
    }
    ESI_MATRIX = {
        ('Low', 'Very Low'): 'basic', ('Low', 'Low'): 'basic', ('Low', 'Medium'): 'basic', ('Low', 'High'): 'Extended service',
        ('Medium', 'Low'): 'basic', ('Medium', 'Medium'): 'Extended service', ('Medium', 'High'): 'Extended service',
        ('High', 'Very Low'): 'Extended service', ('High', 'Low'): 'Extended service', ('High', 'Medium'): 'Extended service', ('High', 'High'): 'Extended service'
    }

    def __init__(self, config: Dict):
        self.config = config
        self.catalog_columns = {}

    def _find_column(self, df_columns, keyword):
        direct_mappings = {
            'integrated oil mist control': 'Integrated oil mist control', 'high vibration': 'High vibration',
            'extended service': 'Extended Service', 'mobile applications': 'Mobile applications',
            'sump volume max gal': 'Gearbox, pump, storage Sump Volume MAX gal',
            'circulating/hyd sump volume max gal.': 'Circulating/Hyd sump volume max gal.'
        }
        if not keyword: return None
        keyword_clean = keyword.lower().strip()
        if keyword_clean in direct_mappings:
            col_name = direct_mappings[keyword_clean]
            if col_name in df_columns: return col_name
        for col in df_columns:
            if keyword_clean in col.lower().replace('\n', ' ').replace('\r', ' ').strip():
                return col
        return None

    def apply_rule_1(self, row: pd.Series, config: Dict) -> Dict:
        criticality = config.get('criticality', 'A')
        if criticality in ['A', 'B1', 'B2']:
            return {'breather_required': True, 'description': f"Rule 1: Criticality '{criticality}' requires a breather."}
        else:
            return {'breather_required': False, 'description': f"Rule 1: Criticality '{criticality}' does not require a breather."}

    def apply_rule_3_cfm(self, breather_catalog: pd.DataFrame, cfm_required: float) -> Tuple[pd.DataFrame, str]:
        cfm_column = 'Max Air Flow (cfm)'
        if cfm_column not in breather_catalog.columns: return pd.DataFrame(), f"Rule 3: FAILED - Column '{cfm_column}' not found in catalog."
        catalog_copy = breather_catalog.copy()
        catalog_copy[cfm_column] = pd.to_numeric(catalog_copy[cfm_column], errors='coerce')
        filtered = catalog_copy[catalog_copy[cfm_column] >= cfm_required].copy()
        trace = f"Rule 3 (CFM): Required >= {cfm_required:.2f}. Found {len(filtered)} of {len(breather_catalog)} models."
        return filtered, trace

    def apply_rule_gpm_margin(self, breathers: pd.DataFrame, asset_gpm: float) -> Tuple[pd.DataFrame, str]:
        gpm_col = 'Max Fluid Flow (gpm)'; required_gpm = asset_gpm * 1.2
        trace = f"Rule 2.5 (GPM Margin): Asset GPM={asset_gpm:.2f}, Required GPM (x1.2) >= {required_gpm:.2f}."
        if gpm_col not in breathers.columns: return breathers, f"{trace} Skipped (column not found)."
        candidates = breathers.copy(); candidates[gpm_col] = pd.to_numeric(candidates[gpm_col], errors='coerce')
        filtered = candidates[(candidates[gpm_col] >= required_gpm) | (candidates[gpm_col].isna())]
        return filtered, trace

    def apply_rule_5_sump(self, candidate_breathers: pd.DataFrame, volumes: Dict, system_type: str = 'splash') -> Tuple[pd.DataFrame, str]:
        volume_key = 'v_oil'; sump_col_name = "circulating/hyd sump volume max gal." if system_type == 'circulating' else "sump volume max gal"
        asset_volume = volumes.get(volume_key, 0)
        trace = f"Rule 5 (Sump): Required Capacity >= {asset_volume:.1f} gal."
        if asset_volume <= 0: return candidate_breathers, f"{trace} Skipped (Asset volume is 0)."
        sump_col = self._find_column(candidate_breathers.columns, sump_col_name)
        if not sump_col: return candidate_breathers, f"{trace} Skipped (Column '{sump_col_name}' not found)."
        breathers_copy = candidate_breathers.copy()
        breathers_copy[sump_col] = pd.to_numeric(breathers_copy[sump_col].astype(str).str.replace(',', ''), errors='coerce')
        suitable = breathers_copy[(breathers_copy[sump_col] >= asset_volume) | (breathers_copy[sump_col].isna())]
        return suitable, trace

    def apply_operational_filters(self, candidate_breathers: pd.DataFrame, row: pd.Series, config: Dict) -> Tuple[pd.DataFrame, List[str]]:
        filtered = candidate_breathers.copy()
        trace = []
        factors = self._extract_operational_factors(row, config)
        filter_map = {
            'wcci': (self._apply_wcci_filter, (factors['wcci'],)),
            'humidity': (self._apply_humidity_filter, (factors['humidity_level'], factors['avg_humidity'])),
            'contamination': (self._apply_contamination_filter, (factors['ci'], factors['particle_filter_required'])),
            'esi': (self._apply_extended_service_filter, (factors['esi'],)),
            'oil_mist': (self._apply_oil_mist_filter, (factors['oil_mist_evidence'],)),
            'vibration': (self._apply_vibration_filter, (factors['vibration'],)),
            'mobile': (self._apply_mobile_filter, (factors['mobile_application'],))
        }
        for filter_name, (func, args) in filter_map.items():
            initial_count = len(filtered)
            result = func(filtered, *args)
            filtered = result['breathers']
            trace.append(f"{result['trace']} ({len(filtered)} of {initial_count} candidates remain).")
            if filtered.empty: break
        return filtered, trace

    def _extract_operational_factors(self, row: pd.Series, config: Dict) -> Dict:
        ci = self.CI_MATRIX.get(str(row.get('(D) Contaminant Likelihood', '')).strip(), 'Medium')
        wcci_info = self.WCCI_MATRIX.get(str(row.get('(D) Water Contact Conditions', '')).strip(), {'factor': 'Low', 'desiccant': True})
        esi = config.get('esi_manual') or self.ESI_MATRIX.get((ci, wcci_info['factor']), 'basic')
        humidity_str = str(row.get('(D) Average Relative Humidity', '')).strip().replace('%', '')
        avg_humidity = pd.to_numeric(humidity_str, errors='coerce')
        humidity_level = 'High' if pd.notna(avg_humidity) and avg_humidity >= 75.0 else 'Normal'
        oil_mist = str(row.get('(D) Oil Mist Evidence on Headspace', '')).lower() in ['true', 'yes', 'y', 'x', '1', '1.0', 'si', 'sí']
        return {'ci': ci, 'wcci': wcci_info['factor'], 'esi': esi, 'desiccant_required': wcci_info['desiccant'], 'humidity_level': humidity_level, 'avg_humidity': avg_humidity if pd.notna(avg_humidity) else 50.0, 'oil_mist_evidence': oil_mist, 'vibration': str(row.get('(D) Vibration', '')), 'mobile_application': config.get('mobile_application', False), 'particle_filter_required': config.get('high_particle_removal', False) or (ci == 'High')}

    def _parse_vibration_level(self, vibration_str: str) -> Dict[str, Any]:
        if pd.isna(vibration_str): return {'heavy_duty_required': False, 'description': 'No data'}
        clean_str = vibration_str.strip();
        if clean_str == '>0.4 ips': return {'heavy_duty_required': True, 'description': 'High (>0.4 ips)'}
        return {'heavy_duty_required': False, 'description': 'Low/Medium'}

    def _apply_vibration_filter(self, breathers: pd.DataFrame, vibration_str: str) -> Dict:
        vib_info = self._parse_vibration_level(vibration_str); vibration_col = self._find_column(breathers.columns, "high vibration")
        trace = f"Rule 4.8: Vibration requirement = {vib_info['description']}."
        if not vibration_col: return {'breathers': breathers, 'trace': f"{trace} Skipped (column not found)."}
        if vib_info['heavy_duty_required']:
            vibration_resistant = breathers[breathers[vibration_col] == True]
            if not vibration_resistant.empty: return {'breathers': vibration_resistant, 'trace': f"{trace} Filtering for High Vibration models."}
            else: return {'breathers': breathers, 'trace': f"{trace} NO High Vibration models found (fallback)."}
        else:
            standard_vibration = breathers[breathers[vibration_col] != True]
            if not standard_vibration.empty: return {'breathers': standard_vibration, 'trace': f"{trace} Preferring Standard models."}
            else: logger.warning("No standard vibration breathers found. Falling back to heavy-duty models."); return {'breathers': breathers, 'trace': f"{trace} No standard models found (fallback)."}

    def _apply_wcci_filter(self, breathers: pd.DataFrame, wcci: str) -> Dict:
        trace = f"Rule 4.1: Water Contact (WCCI) = {wcci}."
        if wcci in ['Very Low', 'Low']: return {'breathers': breathers, 'trace': f"{trace} No specific filter needed."}
        target_col_key = 'water contact conditions medium' if wcci == 'Medium' else 'water contact conditions high'
        target_col = self._find_column(breathers.columns, target_col_key)
        if not target_col: return {'breathers': breathers, 'trace': f"{trace} Skipped (column not found)."}
        suitable = breathers[breathers[target_col] == True]
        return {'breathers': suitable if not suitable.empty else breathers, 'trace': f"{trace} Filtering for models rated for '{wcci}'."}

    def _apply_humidity_filter(self, breathers: pd.DataFrame, humidity_level: str, avg_humidity: float) -> Dict:
        trace_base = f"Rule 4.3: Humidity RH={avg_humidity:.1f}% ({humidity_level})."
        if humidity_level == 'Normal':
            return {'breathers': breathers, 'trace': f"{trace_base} No specific filter needed for normal humidity."}
        if humidity_level == 'High':
            target_col_name = 'Rh >75%'
            if target_col_name not in breathers.columns:
                logger.warning(f"La columna '{target_col_name}' no se encontró. No se aplicó filtro."); return {'breathers': breathers, 'trace': f"{trace_base} Skipped (column '{target_col_name}' not found)."}
            suitable_breathers = breathers[breathers[target_col_name] == True]
            if suitable_breathers.empty:
                logger.warning(f"No se encontraron respiradores para '{target_col_name}'. Usando fallback."); return {'breathers': breathers, 'trace': f"{trace_base} No models found for high humidity range (fallback)."}
            return {'breathers': suitable_breathers, 'trace': f"{trace_base} Filtering for models rated for high humidity."}
        return {'breathers': breathers, 'trace': f"{trace_base} Condition not applicable."}

    def _apply_contamination_filter(self, breathers: pd.DataFrame, ci: str, particle_req: bool) -> Dict:
        trace = f"Rule 4.4/4.5: Contamination Index (CI)='{ci}', Forced High Particle='{particle_req}'."
        if ci == 'Low' and not particle_req: return {'breathers': breathers, 'trace': f"{trace} No high particle filter needed."}
        ext_service_col = self._find_column(breathers.columns, "extended service")
        if not ext_service_col: return {'breathers': breathers, 'trace': f"{trace} Skipped (column not found)."}
        high_filtration = breathers[breathers[ext_service_col] == True]
        return {'breathers': high_filtration if not high_filtration.empty else breathers, 'trace': f"{trace} High particle filtration required."}

    def _apply_extended_service_filter(self, breathers: pd.DataFrame, esi: str) -> Dict:
        trace = f"Rule 4.6: ESI requirement = '{esi}'."
        ext_service_col = self._find_column(breathers.columns, "extended service")
        if not ext_service_col: return {'breathers': breathers, 'trace': f"{trace} Skipped (column not found)."}
        if esi != 'Extended service':
            basic_breathers = breathers[breathers[ext_service_col] != True]
            return {'breathers': basic_breathers if not basic_breathers.empty else breathers, 'trace': f"{trace} Preferring Basic models."}
        else:
            extended = breathers[breathers[ext_service_col] == True]
            return {'breathers': extended if not extended.empty else breathers, 'trace': f"{trace} Filtering for Extended Service models."}

    def _apply_oil_mist_filter(self, breathers: pd.DataFrame, oil_mist: bool) -> Dict:
        trace = f"Rule 4.7: Oil Mist Evidence = {oil_mist}."
        oil_mist_col = self._find_column(breathers.columns, "integrated oil mist control")
        if not oil_mist_col: return {'breathers': breathers, 'trace': f"{trace} Skipped (column not found)."}
        if not oil_mist:
            no_oil_mist = breathers[breathers[oil_mist_col] != True]
            return {'breathers': no_oil_mist if not no_oil_mist.empty else breathers, 'trace': f"{trace} Preferring models without oil mist control."}
        else:
            oil_mist_capable = breathers[breathers[oil_mist_col] == True]
            return {'breathers': oil_mist_capable if not oil_mist_capable.empty else breathers, 'trace': f"{trace} Filtering for models with oil mist control."}

    def _apply_mobile_filter(self, breathers: pd.DataFrame, mobile: bool) -> Dict:
        trace = f"Rule 4.9: Mobile Application = {mobile}."
        mobile_col = self._find_column(breathers.columns, "mobile applications")
        if not mobile_col: return {'breathers': breathers, 'trace': f"{trace} Skipped (column not found)."}
        if not mobile:
            non_mobile = breathers[breathers[mobile_col] != True]
            return {'breathers': non_mobile if not non_mobile.empty else breathers, 'trace': f"{trace} Preferring non-mobile models."}
        else:
            mobile_suitable = breathers[breathers[mobile_col] == True]
            return {'breathers': mobile_suitable, 'trace': f"{trace} Filtering for mobile models (strict)."}

    def apply_rule_6(self, candidate_breathers: pd.DataFrame, available_space: Dict) -> Dict:
        h_limit, d_limit = available_space.get('height_limit'), available_space.get('diameter_limit')
        if h_limit is None and d_limit is None:
            return {'fitting_breathers': candidate_breathers, 'non_fitting_breathers': pd.DataFrame(), 'trace': "Rule 6: No space constraints provided"}
        mask = pd.Series(True, index=candidate_breathers.index)
        if h_limit is not None: mask &= (pd.to_numeric(candidate_breathers['Height (in)'], errors='coerce') <= h_limit)
        if d_limit is not None: mask &= (pd.to_numeric(candidate_breathers['Diameter (in)'], errors='coerce') <= d_limit)
        constraints = [f"H≤{h_limit}\"" for h in [h_limit] if h is not None] + [f"D≤{d_limit}\"" for d in [d_limit] if d is not None]
        fitting, non_fitting = candidate_breathers[mask], candidate_breathers[~mask]
        return {'fitting_breathers': fitting, 'non_fitting_breathers': non_fitting, 'trace': f"Rule 6: Space constraints ({', '.join(constraints)})."}

    def apply_rule_7(self, fitting_breathers: pd.DataFrame, non_fitting_breathers: pd.DataFrame, available_space: Dict, space_data_provided: bool, config: Dict, suboptimal_note: str, cfm_required: float, desiccant_required: bool, v_oil: float, system_type: str) -> Dict:
        primary_status = "Sub-optimal" if suboptimal_note else "Optimal" if not fitting_breathers.empty else "Optimal - Remote Installation" if not non_fitting_breathers.empty and available_space.get('height_limit') == 0 else "Sub-optimal"
        context = {'cfm_required': cfm_required, 'desiccant_required': desiccant_required, 'v_oil': v_oil, 'system_type': system_type}
        result = self._get_critical_a_recommendation(fitting_breathers, non_fitting_breathers, config, context) if config.get('criticality') == 'A' else self._get_standard_recommendation(fitting_breathers, non_fitting_breathers, space_data_provided, config, context)
        final_status = primary_status or result.get('status', 'No Solution Found')
        final_notes = f"{suboptimal_note}\n{result.get('installation_notes', 'No suitable breathers found')}" if suboptimal_note else result.get('installation_notes', 'No suitable breathers found')
        return {'selected_breather': result.get('selected_breather', []), 'status': final_status, 'installation_notes': final_notes, 'trace': result.get('trace', "Rule 7: Final recommendation")}

    def _rank_and_select_best_breather(self, candidates: pd.DataFrame, context: Dict) -> Optional[Dict]:
        if candidates.empty: return None
        df = candidates.copy()
        df['CFM_Margin'] = pd.to_numeric(df['Max Air Flow (cfm)'], errors='coerce').fillna(999) - context['cfm_required']
        df['Adsorption Capacity (mL)'] = pd.to_numeric(df['Adsorption Capacity (mL)'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        sump_col_name = "circulating/hyd sump volume max gal." if context['system_type'] == 'circulating' else "sump volume max gal"
        sump_col = self._find_column(df.columns, sump_col_name)
        if sump_col and context['v_oil'] > 0:
            df[sump_col] = pd.to_numeric(df[sump_col], errors='coerce').fillna(99999)
            df['Sump_Margin'] = df[sump_col] - context['v_oil']
            df = df.sort_values(by=['Adsorption Capacity (mL)', 'Sump_Margin', 'CFM_Margin'], ascending=[True, True, True])
        else:
            df = df.sort_values(by=['Adsorption Capacity (mL)', 'CFM_Margin'], ascending=[True, True])
        best_choice = df.iloc[0].to_dict()
        logger.info(f"Rule 8 (Ranking): Selected '{best_choice.get('Model')}' from {len(df)} final candidates.")
        return best_choice

    def _get_critical_a_recommendation(self, fitting_breathers, non_fitting_breathers, config, context):
        all_candidates = pd.concat([fitting_breathers, non_fitting_breathers]) if not fitting_breathers.empty or not non_fitting_breathers.empty else pd.DataFrame()
        if all_candidates.empty: return self._no_solution_result()
        rebuildables = all_candidates[all_candidates['Type'].str.contains('Rebuildable', na=False, case=False)]
        disposables = all_candidates[all_candidates['Type'].str.contains('Disposable', na=False, case=False)]
        optimal_choice = self._rank_and_select_best_breather(rebuildables, context)
        cost_effective_choice = self._rank_and_select_best_breather(disposables, context)
        recommendations, notes = [], []
        if optimal_choice:
            recommendations.append(optimal_choice)
            fit_status = "Fits directly." if not fitting_breathers.empty and optimal_choice['Model'] in fitting_breathers['Model'].values else "Requires remote installation or space check."
            notes.append(f"Optimal (Rebuildable): {optimal_choice.get('Brand')} {optimal_choice.get('Model')}. {fit_status}")
        if cost_effective_choice and not any(rec['Model'] == cost_effective_choice['Model'] for rec in recommendations):
            recommendations.append(cost_effective_choice)
            fit_status = "Fits directly." if not fitting_breathers.empty and cost_effective_choice['Model'] in fitting_breathers['Model'].values else "Requires remote installation or space check."
            notes.append(f"Cost-Effective (Disposable): {cost_effective_choice.get('Brand')} {cost_effective_choice.get('Model')}. {fit_status}")
        return self._no_solution_result() if not recommendations else {'selected_breather': recommendations, 'installation_notes': '\n'.join(notes), 'trace': "Rule 7.A: Criticality A logic applied"}

    def _get_standard_recommendation(self, fitting_breathers, non_fitting_breathers, space_data_provided, config, context):
        if space_data_provided:
            if not fitting_breathers.empty:
                selected = self._rank_and_select_best_breather(fitting_breathers, context)
                return {'selected_breather': [selected], 'status': 'Optimal', 'installation_notes': 'Direct installation.', 'trace': "Rule 7.1: Optimal solution (fits space)"}
            elif not non_fitting_breathers.empty:
                selected = self._rank_and_select_best_breather(non_fitting_breathers, context)
                return {'selected_breather': [selected], 'status': 'Sub-optimal', 'installation_notes': 'Exceeds available space. Remote installation may be required.', 'trace': "Rule 7.3: Sub-optimal solution (space constraints)"}
        else:
            all_candidates = pd.concat([fitting_breathers, non_fitting_breathers]) if not fitting_breathers.empty or not non_fitting_breathers.empty else pd.DataFrame()
            if not all_candidates.empty:
                selected = self._rank_and_select_best_breather(all_candidates, context)
                note = f"Manual space verification required for the optimal choice: {selected.get('Brand')} {selected.get('Model')} ({selected.get('Height (in)', 0):.1f}\"H x {selected.get('Diameter (in)', 0):.1f}\"D)"
                return {'selected_breather': [selected], 'status': 'Optimal', 'installation_notes': note, 'trace': "Rule 7: No space data - manual verification needed"}
        return self._no_solution_result()

    def _no_solution_result(self) -> Dict:
        return {'selected_breather': [], 'status': 'No Solution Found', 'installation_notes': 'No suitable breathers found after all filters.', 'trace': "Rule 7: No viable solution available"}