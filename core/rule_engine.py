# --- analysis/rule_engine.py ---
# VERSIÃ“N FINAL CON LÃ“GICA CONDICIONAL DE SELECCIÃ“N

"""
Rule Engine for NoRia Breather Selection - VERSIÃ“N DEFINITIVA
- CORRECCIÃ“N (Default Selection): LÃ³gica condicional (Sump>CFM para Circulating, CFM>Sump para Splash).
- CORRECCIÃ“N (Oil Mist): Ignora el filtro de niebla de aceite si V_Sump < 15 gal.
- CORRECCIÃ“N (WCCI): Actualizada la matriz WCCI segÃºn la nueva especificaciÃ³n.
- CORRECCIÃ“N (LCC): Actualizada la lÃ³gica de selecciÃ³n LCC para priorizar el CFM mÃ¡s cercano.
- CORRECCIÃ“N (Cost Benefit): Actualizada la lÃ³gica para buscar el desechable con mejor ajuste tÃ©cnico.
"""

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
        'Occasional Washdowns': {'factor': 'Medium', 'desiccant': True},
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
            'integrated oil mist control': ['Integrated oil mist control'],
            'high vibration': ['High vibration'],
            'extended service': ['Extended Service'],
            'mobile applications': ['Mobile applications'],
            'rh 25 to 75': ['Rh 25 to 75%'],
            'rh >75%': ['Rh >75%'],
            'water contact conditions high': ['Water contact conditions\r\nHigh', 'Water contact conditions High', 'Water contact conditions\nHigh'],
            'water contact conditions medium': ['Water contact conditions\r\nMedium', 'Water contact conditions Medium', 'Water contact conditions\nMedium'],
            'water contact conditions low': ['Water contact conditions\r\nLow', 'Water contact conditions Low', 'Water contact conditions\nLow'],
            'sump volume max gal': ['Gearbox, pump, storage Sump Volume MAX gal'],
            'circulating/hyd sump volume max gal.': ['Circulating/Hyd sump volume max gal.']
        }
        if not keyword: return None
        if keyword in self.catalog_columns and self.catalog_columns[keyword] in df_columns:
            return self.catalog_columns[keyword]
        keyword_clean = keyword.lower().strip()
        if keyword_clean in direct_mappings:
            for potential_col in direct_mappings[keyword_clean]:
                if potential_col in df_columns:
                    self.catalog_columns[keyword] = potential_col
                    return potential_col
        for col in df_columns:
            col_clean = col.lower().replace('\n', ' ').replace('\r', ' ').strip()
            if keyword_clean in col_clean:
                self.catalog_columns[keyword] = col
                return col
        self.catalog_columns[keyword] = None
        return None

    def apply_rule_1(self, row: pd.Series, config: Dict) -> Dict:
        criticality = config.get('criticality', 'A')
        if criticality in ['A', 'B1', 'B2']:
            return {'breather_required': True, 'description': f"Criticality {criticality} requires breather"}
        else:
            return {'breather_required': False, 'description': f"Criticality {criticality} does not require breather"}

    def apply_rule_3(self, breather_catalog: pd.DataFrame, cfm_required: float) -> pd.DataFrame:
        cfm_column = 'Max Air Flow (cfm)'
        if cfm_column not in breather_catalog.columns: return pd.DataFrame()
        catalog_copy = breather_catalog.copy()
        catalog_copy[cfm_column] = pd.to_numeric(catalog_copy[cfm_column], errors='coerce')
        filtered = catalog_copy[catalog_copy[cfm_column] >= cfm_required].copy()
        return filtered

    def apply_rule_4(self, candidate_breathers: pd.DataFrame, row: pd.Series, config: Dict, volumes: Dict, exclude_filters: List[str] = None) -> Dict:
        if exclude_filters is None: exclude_filters = []
        filtered = candidate_breathers.copy()
        trace = []
        factors = self._extract_operational_factors(row, config)

        # PASO 1: MOBILE FILTER VA PRIMERO (ESTRICTO - sin fallback)
        if factors['mobile_application'] and 'mobile' not in exclude_filters:
            mobile_result = self._apply_mobile_filter(filtered, factors['mobile_application'])
            filtered = mobile_result['breathers']
            trace.append(mobile_result['trace'])
            
            # Si mobile=True pero no hay breathers móviles, filtered quedará vacío
            # El fallback en data_processor manejará relajar otros constraints

        # PASO 2: Aplicar el resto de filtros
        filter_map = {
            'wcci': (self._apply_wcci_filter, (factors['wcci'],)),
            'desiccant': (self._apply_desiccant_filter, (factors['desiccant_required'],)),
            'esi': (self._apply_extended_service_filter, (factors['esi'],)),
            'humidity': (self._apply_humidity_filter, (factors['humidity_level'], factors['avg_humidity'])),
            'contamination': (self._apply_contamination_filter, (factors['ci'], factors['particle_filter_required'])),
            'oil_mist': (self._apply_oil_mist_filter, (factors['oil_mist_evidence'],)),
            'vibration': (self._apply_vibration_filter, (factors['vibration'],))
        }

        v_sump = volumes.get('v_sump', 0)
        if v_sump < 15 and 'oil_mist' in filter_map:
            del filter_map['oil_mist']
            trace.append(f"Rule 4.7 (Oil Mist): Skipped due to Sump Volume < 15 gal ({v_sump:.2f} gal).")

        for filter_name, (func, args) in filter_map.items():
            if filter_name in exclude_filters:
                trace.append(f"Rule 4.x: Skipped '{filter_name}' filter.")
                continue
            result = func(filtered, *args)
            filtered = result['breathers']
            trace.append(result['trace'])
            if filtered.empty: break
        return {'filtered_breathers': filtered, 'trace': trace}

    def apply_rule_5(self, candidate_breathers: pd.DataFrame, volumes: Dict, system_type: str = 'splash') -> Dict:
        volume_key = 'v_oil'
        sump_col_name = "circulating/hyd sump volume max gal." if system_type == 'circulating' else "sump volume max gal"
        asset_volume = volumes.get(volume_key, 0)
        if asset_volume <= 0: return {'filtered_breathers': candidate_breathers, 'trace': "Rule 5: Skipped (Asset volume is 0)"}
        sump_col = self._find_column(candidate_breathers.columns, sump_col_name)
        if not sump_col: return {'filtered_breathers': candidate_breathers, 'trace': f"Rule 5: Skipped (Column not found)"}
        breathers_copy = candidate_breathers.copy()
        breathers_copy[sump_col] = pd.to_numeric(breathers_copy[sump_col].astype(str).str.replace(',', ''), errors='coerce')
        suitable = breathers_copy[breathers_copy[sump_col] >= asset_volume]
        return {'filtered_breathers': suitable if not suitable.empty else candidate_breathers,
                'trace': f"Rule 5: {len(suitable)} breathers meet volume >= {asset_volume:.1f} gal" if not suitable.empty else f"Rule 5: No breathers meet volume >= {asset_volume:.1f} gal (fallback)"}

    def _extract_operational_factors(self, row: pd.Series, config: Dict) -> Dict:
        ci = self.CI_MATRIX.get(str(row.get('(D) Contaminant Likelihood', '')).strip(), 'Medium')
        wcci_info = self.WCCI_MATRIX.get(str(row.get('(D) Water Contact Conditions', '')).strip(), {'factor': 'Low', 'desiccant': True})
        esi = config.get('esi_manual') or self.ESI_MATRIX.get((ci, wcci_info['factor']), 'basic')
        humidity_str = str(row.get('(D) Average Relative Humidity', '')).strip().replace('%', '')
        avg_humidity = pd.to_numeric(humidity_str, errors='coerce')
        humidity_level = 'High' if pd.notna(avg_humidity) and avg_humidity >= 75.0 else 'Normal'
        oil_mist = str(row.get('(D) Oil Mist Evidence on Headspace', '')).lower() in ['true', 'yes', 'y', 'x', '1', '1.0', 'si', 'sÃ­']
        return {'ci': ci, 'wcci': wcci_info['factor'], 'esi': esi, 'desiccant_required': wcci_info['desiccant'], 'humidity_level': humidity_level,
                'avg_humidity': avg_humidity if pd.notna(avg_humidity) else 50.0, 'oil_mist_evidence': oil_mist, 'vibration': str(row.get('(D) Vibration', '')),
                'mobile_application': config.get('mobile_application', False), 'particle_filter_required': config.get('high_particle_removal', False) or (ci == 'High')}

    def _parse_vibration_level(self, vibration_str: str) -> Dict[str, Any]:
        if pd.isna(vibration_str): return {'heavy_duty_required': False, 'description': 'No data'}
        clean_str = vibration_str.strip().lower()
        if clean_str == '>0.4 ips': return {'heavy_duty_required': True, 'description': 'High (>0.4 ips)'}
        return {'heavy_duty_required': False, 'description': 'Low/Medium'}

    def _apply_vibration_filter(self, breathers: pd.DataFrame, vibration_str: str) -> Dict:
        vib_info = self._parse_vibration_level(vibration_str)
        vibration_col = self._find_column(breathers.columns, "high vibration")
        trace_base = f"Rule 4.8: Vibration={vib_info['description']}"
        if not vibration_col: return {'breathers': breathers, 'trace': f"{trace_base}, column not found"}
        if not vib_info['heavy_duty_required']:
            low_vib_breathers = breathers[breathers[vibration_col] != True]
            return {'breathers': low_vib_breathers if not low_vib_breathers.empty else breathers,
                    'trace': f"{trace_base}, {len(low_vib_breathers)} non-HD selected" if not low_vib_breathers.empty else f"{trace_base}, only HD available (fallback)"}
        else:
            high_vib_capable = breathers[breathers[vibration_col] == True]
            return {'breathers': high_vib_capable if not high_vib_capable.empty else breathers,
                    'trace': f"{trace_base}, {len(high_vib_capable)} HD found" if not high_vib_capable.empty else f"{trace_base}, no HD found (fallback)"}

    def _apply_wcci_filter(self, breathers: pd.DataFrame, wcci_factor: str) -> Dict:
        trace = f"Rule 4.1: WCCI={wcci_factor}"
        col_map = {'Very Low': 'water contact conditions low', 'Low': 'water contact conditions low',
                   'Medium': 'water contact conditions medium', 'High': 'water contact conditions high'}
        target_col = self._find_column(breathers.columns, col_map.get(wcci_factor))
        if not target_col: return {'breathers': breathers, 'trace': f"{trace}, column not found"}
        suitable = breathers[breathers[target_col] == True]
        return {'breathers': suitable if not suitable.empty else breathers,
                'trace': f"{trace}, {len(suitable)} resistant found" if not suitable.empty else f"{trace}, none found (fallback)"}

    def _apply_desiccant_filter(self, breathers: pd.DataFrame, desiccant_required: bool) -> Dict:
        return {'breathers': breathers, 'trace': f"Rule 4.2: Desiccant required={desiccant_required}"}

    def _apply_humidity_filter(self, breathers: pd.DataFrame, humidity_level: str, avg_humidity: float) -> Dict:
        trace_base = f"Rule 4.3: Humidity RH={avg_humidity:.1f}% ({humidity_level})"
        target_col_name = 'rh >75%' if humidity_level == 'High' else 'rh 25 to 75%'
        col_to_find = self._find_column(breathers.columns, target_col_name)
        if not col_to_find:
            logger.warning(f"Rule 4.3: Humidity column '{target_col_name}' not found. No filter applied.")
            return {'breathers': breathers, 'trace': f"{trace_base}, column not found"}
        suitable_breathers = breathers[breathers[col_to_find] == True]
        if suitable_breathers.empty:
            logger.warning(f"Rule 4.3: No breathers found for range '{target_col_name}'. Using fallback.")
            return {'breathers': breathers, 'trace': f"{trace_base}, none found for this range (fallback)"}
        return {'breathers': suitable_breathers, 'trace': f"{trace_base}, {len(suitable_breathers)} models selected for '{target_col_name}'"}

    def _apply_contamination_filter(self, breathers: pd.DataFrame, ci: str, particle_req: bool) -> Dict:
        trace = f"Rule 4.4/4.5: CI={ci}, Force_High_Particle={particle_req}"
        if ci == 'Low' and not particle_req: return {'breathers': breathers, 'trace': f"{trace}, no filter"}
        ext_service_col = self._find_column(breathers.columns, "extended service")
        if not ext_service_col: return {'breathers': breathers, 'trace': f"{trace}, column not found"}
        high_filtration = breathers[breathers[ext_service_col] == True]
        return {'breathers': high_filtration if not high_filtration.empty else breathers,
                'trace': f"{trace}, {len(high_filtration)} E.S. found" if not high_filtration.empty else f"{trace}, no E.S. found (fallback)"}

    def _apply_extended_service_filter(self, breathers: pd.DataFrame, esi: str) -> Dict:
        trace = f"Rule 4.6: ESI requirement = {esi}"
        ext_service_col = self._find_column(breathers.columns, "extended service")
        if not ext_service_col: return {'breathers': breathers, 'trace': f"{trace}, column not found"}
        if esi != 'Extended service':
            basic_breathers = breathers[breathers[ext_service_col] != True]
            return {'breathers': basic_breathers if not basic_breathers.empty else breathers,
                    'trace': f"{trace}, {len(basic_breathers)} basic selected" if not basic_breathers.empty else f"{trace}, only E.S. available (fallback)"}
        else:
            extended = breathers[breathers[ext_service_col] == True]
            return {'breathers': extended if not extended.empty else breathers,
                    'trace': f"{trace}, {len(extended)} E.S. found" if not extended.empty else f"{trace}, none available (fallback)"}

    def _apply_oil_mist_filter(self, breathers: pd.DataFrame, oil_mist: bool) -> Dict:
        trace = "Rule 4.7: Oil Mist Control"
        oil_mist_col = self._find_column(breathers.columns, "integrated oil mist control")
        if not oil_mist_col: return {'breathers': breathers, 'trace': f"{trace}, column not found"}
        if not oil_mist:
            no_oil_mist = breathers[breathers[oil_mist_col] != True]
            return {'breathers': no_oil_mist if not no_oil_mist.empty else breathers,
                    'trace': f"{trace} not required, {len(no_oil_mist)} selected" if not no_oil_mist.empty else f"{trace} not required, but only capable models found (fallback)"}
        else:
            oil_mist_capable = breathers[breathers[oil_mist_col] == True]
            return {'breathers': oil_mist_capable if not oil_mist_capable.empty else breathers,
                    'trace': f"{trace} required, {len(oil_mist_capable)} found" if not oil_mist_capable.empty else f"{trace} required, but none found (fallback)"}

    def _apply_mobile_filter(self, breathers: pd.DataFrame, mobile: bool) -> Dict:
        trace = "Rule 4.9: Mobile Application"
        mobile_col = self._find_column(breathers.columns, "mobile applications")
        if not mobile_col: 
            return {'breathers': breathers, 'trace': f"{trace}, column not found"}
        
        if not mobile:
            # Si mobile NO es requerido, excluir breathers móviles (con fallback)
            non_mobile = breathers[breathers[mobile_col] != True]
            return {
                'breathers': non_mobile if not non_mobile.empty else breathers,
                'trace': f"{trace} not required, {len(non_mobile)} selected" if not non_mobile.empty else f"{trace} not required, but only mobile available (fallback)"
            }
        else:
            # Si mobile ES requerido, SOLO breathers móviles (SIN fallback - estricto)
            mobile_suitable = breathers[breathers[mobile_col] == True]
            return {
                'breathers': mobile_suitable,
                'trace': f"{trace} required, {len(mobile_suitable)} mobile breathers found" if not mobile_suitable.empty else f"{trace} required, NO mobile breathers found"
            }

    def apply_rule_6(self, candidate_breathers: pd.DataFrame, available_space: Dict) -> Dict:
        h_limit = available_space.get('height_limit')
        d_limit = available_space.get('diameter_limit')
        if h_limit is None and d_limit is None:
            return {'fitting_breathers': candidate_breathers, 'non_fitting_breathers': pd.DataFrame(), 'trace': "Rule 6: No space constraints provided"}
        mask = pd.Series(True, index=candidate_breathers.index)
        if h_limit is not None: mask &= (pd.to_numeric(candidate_breathers['Height (in)'], errors='coerce') <= h_limit)
        if d_limit is not None: mask &= (pd.to_numeric(candidate_breathers['Diameter (in)'], errors='coerce') <= d_limit)
        constraints = []
        if h_limit is not None: constraints.append(f"H<={h_limit}\"")
        if d_limit is not None: constraints.append(f"D<={d_limit}\"")
        fitting = candidate_breathers[mask]
        non_fitting = candidate_breathers[~mask]
        return {'fitting_breathers': fitting, 'non_fitting_breathers': non_fitting, 'trace': f"Rule 6: Space constraints ({', '.join(constraints)}), {len(fitting)} fit, {len(non_fitting)} don't fit"}

    def apply_rule_7(self, fitting_breathers: pd.DataFrame, non_fitting_breathers: pd.DataFrame, available_space: Dict, space_data_provided: bool, config: Dict,
                     suboptimal_note: str, cfm_required: float, desiccant_required: bool, v_oil: float, system_type: str) -> Dict:
        primary_status = "Sub-optimal" if suboptimal_note else ("Optimal" if not fitting_breathers.empty else ("Optimal - Remote Installation" if available_space.get('height_limit') == 0 else "Sub-optimal")) if not non_fitting_breathers.empty else ""
        context = {'cfm_required': cfm_required, 'desiccant_required': desiccant_required, 'v_oil': v_oil, 'system_type': system_type}
        result = self._get_critical_a_recommendation(fitting_breathers, non_fitting_breathers, config, context) if config.get('criticality') == 'A' else self._get_standard_recommendation(fitting_breathers, non_fitting_breathers, space_data_provided, config, context)
        final_status = primary_status or result.get('status', 'No Solution Found')
        final_notes = f"{suboptimal_note}\n{result.get('installation_notes', 'No suitable breathers found')}" if suboptimal_note else result.get('installation_notes', 'No suitable breathers found')
        return {'selected_breather': result.get('selected_breather', []), 'status': final_status, 'installation_notes': final_notes, 'trace': result.get('trace', "Rule 7: Final recommendation")}

    def _rank_and_select_best_breather(self, candidates: pd.DataFrame, context: Dict) -> Optional[Dict]:
        """
        Ranking y selecciÃ³n del mejor respirador por defecto con LÃ“GICA CONDICIONAL.
        - Para Circulating Systems: Prioriza Sump Margin -> CFM Margin.
        - Para Splash Systems: Prioriza CFM Margin -> Sump Margin.
        """
        if candidates.empty:
            return None

        df = candidates.copy()
        df['CFM_Margin'] = pd.to_numeric(df['Max Air Flow (cfm)'], errors='coerce').fillna(999) - context['cfm_required']
        df['Adsorption Capacity (mL)'] = pd.to_numeric(df['Adsorption Capacity (mL)'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

        sump_col_name = "circulating/hyd sump volume max gal." if context.get('system_type') == 'circulating' else "sump volume max gal"
        sump_col = self._find_column(df.columns, sump_col_name)

        if sump_col and context.get('v_oil', 0) > 0:
            df[sump_col] = pd.to_numeric(df[sump_col], errors='coerce').fillna(99999)
            df['Sump_Margin'] = df[sump_col] - context['v_oil']
            
            if context.get('system_type') == 'circulating':
                logger.info("Applying CIRCULATING system ranking logic (Sump > CFM).")
                df = df.sort_values(
                    by=['Sump_Margin', 'CFM_Margin', 'Adsorption Capacity (mL)'],
                    ascending=[True, True, False]
                )
            else:
                logger.info("Applying SPLASH system ranking logic (CFM > Sump).")
                df = df.sort_values(
                    by=['CFM_Margin', 'Sump_Margin', 'Adsorption Capacity (mL)'],
                    ascending=[True, True, False]
                )
        else:
            logger.info("No sump data, ranking by CFM only.")
            df = df.sort_values(
                by=['CFM_Margin', 'Adsorption Capacity (mL)'],
                ascending=[True, False]
            )

        best_choice = df.iloc[0].to_dict()
        logger.info(f"Default best breather selected for {context.get('system_type', 'system')}: {best_choice.get('Brand')} {best_choice.get('Model')}")
        return best_choice

    def select_lcc_breather(self, all_candidates: pd.DataFrame, context: Dict) -> Optional[Dict]:
        """
        SelecciÃ³n LCC (Life Cycle Cost) - LÃ“GICA CORREGIDA
        Prioridad: Rebuildable con el CFM mÃ¡s cercano al requerido.
        """
        if all_candidates.empty: return None
        df = all_candidates.copy()
        df['CFM_Margin'] = pd.to_numeric(df['Max Air Flow (cfm)'], errors='coerce').fillna(999) - context['cfm_required']
        df['Adsorption Capacity (mL)'] = pd.to_numeric(df['Adsorption Capacity (mL)'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        
        rebuildables = df[df['Type'].str.contains('Rebuildable', na=False, case=False)]
        if not rebuildables.empty:
            rebuildables_sorted = rebuildables.sort_values(by=['CFM_Margin', 'Adsorption Capacity (mL)'], ascending=[True, False])
            lcc_choice = rebuildables_sorted.iloc[0].to_dict()
            logger.info(f"LCC breather selected (Rebuildable - Closest CFM): {lcc_choice.get('Brand')} {lcc_choice.get('Model')}")
            return lcc_choice
        
        disposables = df[df['Type'].str.contains('Disposable', na=False, case=False)]
        if not disposables.empty:
            disposables_sorted = disposables.sort_values(by=['CFM_Margin', 'Adsorption Capacity (mL)'], ascending=[True, False])
            lcc_choice = disposables_sorted.iloc[0].to_dict()
            logger.info(f"LCC breather selected (Disposable fallback - Closest CFM): {lcc_choice.get('Brand')} {lcc_choice.get('Model')}")
            return lcc_choice

        df_sorted = df.sort_values(by=['CFM_Margin', 'Adsorption Capacity (mL)'], ascending=[True, False])
        lcc_choice = df_sorted.iloc[0].to_dict()
        logger.info(f"LCC breather selected (generic fallback - Closest CFM): {lcc_choice.get('Brand')} {lcc_choice.get('Model')}")
        return lcc_choice
    
    def select_cost_benefit_breather(self, all_candidates: pd.DataFrame, context: Dict) -> Optional[Dict]:
        """
        SelecciÃ³n Cost Benefit - LÃ“GICA CORREGIDA
        Busca el respirador DESECHABLE con el mejor ajuste tÃ©cnico.
        """
        if all_candidates.empty: return None
        df = all_candidates.copy()
        
        disposables = df[df['Type'].str.contains('Disposable', na=False, case=False)]
        if disposables.empty:
            logger.warning("No Disposable breathers found for Cost Benefit selection")
            return None

        disposables_df = disposables.copy()
        disposables_df['CFM_Margin'] = pd.to_numeric(disposables_df['Max Air Flow (cfm)'], errors='coerce').fillna(999) - context['cfm_required']
        disposables_df['Adsorption Capacity (mL)'] = pd.to_numeric(disposables_df['Adsorption Capacity (mL)'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        
        sump_col_name = "circulating/hyd sump volume max gal." if context['system_type'] == 'circulating' else "sump volume max gal"
        sump_col = self._find_column(disposables_df.columns, sump_col_name)

        if sump_col and context.get('v_oil', 0) > 0:
            disposables_df[sump_col] = pd.to_numeric(disposables_df[sump_col], errors='coerce').fillna(99999)
            disposables_df['Sump_Margin'] = disposables_df[sump_col] - context['v_oil']
            
            disposables_sorted = disposables_df.sort_values(by=['Sump_Margin', 'CFM_Margin', 'Adsorption Capacity (mL)'], ascending=[True, True, True])
        else:
            disposables_sorted = disposables_df.sort_values(by=['CFM_Margin', 'Adsorption Capacity (mL)'], ascending=[True, True])
        
        cb_choice = disposables_sorted.iloc[0].to_dict()
        logger.info(f"Cost Benefit breather selected (Best Fit Disposable): {cb_choice.get('Brand')} {cb_choice.get('Model')}")
        return cb_choice

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
        return self._no_solution_result() if not recommendations else {'selected_breather': recommendations, 'installation_notes': '\n'.join(notes), 'trace': "Rule 7.A: Criticality A logic applied (Rebuildable + Disposable options)"}

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