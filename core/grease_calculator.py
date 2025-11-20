# core/grease_calculator.py (FINAL VERSION - Corrected frequency logic and translated strings)

import pandas as pd
import numpy as np
import re
from typing import Dict, Any, Tuple

class GreaseCalculator:
    CONVERSION_OZ_TO_GRAMS = 28.3495
    CONVERSION_MM_TO_INCHES = 1 / 25.4
    FILM_THICKNESS_INCHES_CONSTANT = 0.001

    FRAME_SIZE_TABLE_MANUAL = {"145-215": 0.28, "254-286": 0.55, "324-365": 0.82, "404-449": 1.35, "5000": 1.39, "5800": 1.66, "6000": 1.52, "6100": 1.85, "6200": 2.16, "6700-6800": 2.94, "6900": 3.68, "7100-9500": 2.22}
    FRAME_SIZE_TABLE_AUTOMATED = {"145-215": 0.17, "254-286": 0.33, "324-365": 0.49, "404-449": 0.81, "5000": 0.83, "5800": 1.00, "6000": 0.91, "6100": 1.11, "6200": 1.30, "6700-6800": 1.76, "6900": 2.21, "7100-9500": 1.33}
    SHAFT_DIAMETER_FROM_FS = {"145-215": "1-3/8", "254-286": "1-7/8", "324-365": "2-1/8", "404-449": "3-3/8", "5000": "3-7/8", "5800": "4.875", "6700-6800": "4.875", "6900": "6", "7100-9500": "6.5"}

    def _get_dimension_in_inches(self, row: pd.Series, value_col: str, unit_col: str) -> float:
        value = pd.to_numeric(row.get(value_col), errors='coerce')
        unit = str(row.get(unit_col, 'in')).lower().strip()
        if pd.isna(value): return np.nan
        if 'mm' in unit: return value * self.CONVERSION_MM_TO_INCHES
        return value

    def _get_dimension_in_mm(self, row: pd.Series, value_col: str, unit_col: str) -> float:
        value = pd.to_numeric(row.get(value_col), errors='coerce')
        unit = str(row.get(unit_col, 'in')).lower().strip()
        if pd.isna(value): return np.nan
        if 'in' in unit: return value * 25.4
        return value

    def _parse_fraction(self, value: Any) -> float:
        if pd.isna(value): return np.nan
        try: return float(value)
        except (ValueError, TypeError):
            if isinstance(value, str) and ('-' in value or '/' in value):
                parts = value.split('-'); total = 0.0
                for part in parts:
                    if '/' in part: num, den = part.split('/'); total += float(num) / float(den)
                    else: total += float(part)
                return total
            return np.nan

    def calculate_complete_analysis(self, row: pd.Series) -> Dict[str, Any]:
        quantity_result = self._calculate_quantity(row)
        frequency_result = self._calculate_frequency(row, quantity_result)
        return {**quantity_result, **frequency_result}

    def _calculate_quantity(self, row: pd.Series) -> Dict[str, Any]:
        result = {'gq_grams': 0.0, 'quantity_method': 'Calculation Impossible', 'error': ''}
        bearing_type = str(row.get('(D) Bearing Type', '')).lower()
        maint_point_template = str(row.iloc[8]).lower()
        if 'journal' in bearing_type or 'bushing' in maint_point_template:
            return self._calculate_quantity_for_journal(row)
        d_outer = self._get_dimension_in_inches(row, '(D) Bearing OD', '(DU) Bearing OD')
        b_width = self._get_dimension_in_inches(row, '(D) Bearing Width', '(DU) Bearing Width')
        if pd.notna(d_outer) and d_outer > 0 and pd.notna(b_width) and b_width > 0:
            return self._calculate_quantity_from_dimensions(d_outer, b_width, row)
        frame_size = str(row.get('(D) Frame', '')).strip()
        if 'motor' in maint_point_template and frame_size:
            return self._calculate_quantity_from_frame_size(frame_size, row)
        result['error'] = "Missing bearing dimensions or motor Frame Size."
        return result

    def _calculate_quantity_for_journal(self, row: pd.Series) -> Dict[str, Any]:
        d_inner = self._get_dimension_in_inches(row, '(D) Shaft Diameter', '(DU) Shaft Diameter')
        w_width = self._get_dimension_in_inches(row, '(D) Bearing Width', '(DU) Bearing Width')
        missing_fields = []
        if not (pd.notna(d_inner) and d_inner > 0): missing_fields.append('Shaft Diameter')
        if not (pd.notna(w_width) and w_width > 0): missing_fields.append('Bearing Width')
        if missing_fields:
            return {'gq_grams': 0.0, 'quantity_method': 'Calculation Impossible', 'error': f"Missing data for Journal Bearing: {', '.join(missing_fields)}."}
        dc_clearance = 2 * self.FILM_THICKNESS_INCHES_CONSTANT
        area = np.pi * d_inner * w_width
        gq_grams = (dc_clearance * area * 0.5) * self.CONVERSION_OZ_TO_GRAMS
        return {'gq_grams': gq_grams, 'quantity_method': 'Journal Bearing Formula (Fixed FT)', 'error': ''}

    def _calculate_quantity_from_dimensions(self, d_outer: float, b_width: float, row: pd.Series) -> Dict[str, Any]:
        bn = str(row.get('(D) Bearing/Housing Number (DE - if more than 1)', '')).strip().upper()
        lub_system = str(row.get('(D) Single Point Lubricator', '')).strip()
        if bn.endswith('W33'):
            gq_oz = 0.0456 * d_outer * b_width; method = "Formula (W33)"
        elif lub_system in ["Not equipped but needed", "Equipped and Needed"]:
            gq_oz = 0.0456 * d_outer * b_width; method = "Formula (Automatic)"
        else:
            gq_oz = 0.114 * d_outer * b_width; method = "Formula (Manual)"
        return {'gq_grams': gq_oz * self.CONVERSION_OZ_TO_GRAMS, 'quantity_method': method, 'error': ''}

    def _calculate_quantity_from_frame_size(self, frame_size: str, row: pd.Series) -> Dict[str, Any]:
        lub_system = str(row.get('(D) Single Point Lubricator', '')).strip()
        table = self.FRAME_SIZE_TABLE_AUTOMATED if lub_system in ["Not equipped but needed", "Equipped and Needed"] else self.FRAME_SIZE_TABLE_MANUAL
        method = f"Frame Size Table ({'Automatic' if table == self.FRAME_SIZE_TABLE_AUTOMATED else 'Manual'})"
        gq_oz = table.get(frame_size)
        if gq_oz is not None:
            return {'gq_grams': gq_oz * self.CONVERSION_OZ_TO_GRAMS, 'quantity_method': method, 'error': ''}
        else:
            return {'gq_grams': 0.0, 'quantity_method': 'Calculation Impossible', 'error': f"Frame Size '{frame_size}' not found in table."}

    def _calculate_frequency(self, row: pd.Series, quantity_result: Dict) -> Dict[str, Any]:
        freq_result = {'frequency_hours': 0.0, 'frequency_unit': 'N/A', 'K_factor': 0.0, 'factors': {}}
        factors = self._get_correction_factors(row)
        freq_result['factors'] = factors
        K = np.prod(list(factors.values())) if factors else 0
        freq_result['K_factor'] = K
        MAX_FREQUENCY_HOURS = 8760
        
        bearing_type = str(row.get('(D) Bearing Type', '')).lower()
        if 'journal' in bearing_type or 'bushing' in str(row.iloc[8]).lower():
            d_inner = self._get_dimension_in_inches(row, '(D) Shaft Diameter', '(DU) Shaft Diameter')
            w_width = self._get_dimension_in_inches(row, '(D) Bearing Width', '(DU) Bearing Width')
            dc_clearance = 2 * self.FILM_THICKNESS_INCHES_CONSTANT
            runtime_text = str(row.get('(D) Runtime (%)', '')).strip()
            rp_map = {"<10%": 0.1, "10 to 30%": 0.3, "30 to 60%": 0.6, "60 to 90%": 0.9, ">90%": 1.0}
            rp = rp_map.get(runtime_text, 0.9)
            Oh = 168 * rp
            if not all(pd.notna(x) and x > 0 for x in [d_inner, w_width, Oh, K]): 
                return freq_result
            area = np.pi * d_inner * w_width
            t_grease_jb = (dc_clearance * area * Oh * 0.5) / K
            if t_grease_jb > MAX_FREQUENCY_HOURS:
                t_grease_jb = MAX_FREQUENCY_HOURS
            freq_result['frequency_hours'], freq_result['frequency_unit'] = t_grease_jb, 'Hours'
        else:
            n_rpm = pd.to_numeric(row.get('(D) RPM'), errors='coerce')
            d_shaft_mm = self._get_dimension_in_mm(row, '(D) Shaft Diameter', '(DU) Shaft Diameter')
            if pd.isna(d_shaft_mm) or d_shaft_mm == 0:
                if quantity_result.get('quantity_method', '').startswith('Frame Size Table'):
                    frame_size = str(row.get('(D) Frame', '')).strip()
                    shaft_diameter_str = self.SHAFT_DIAMETER_FROM_FS.get(frame_size)
                    d_shaft_in = self._parse_fraction(shaft_diameter_str)
                    if pd.notna(d_shaft_in):
                        d_shaft_mm = d_shaft_in * 25.4
            if not (pd.notna(n_rpm) and n_rpm > 0 and pd.notna(d_shaft_mm) and d_shaft_mm > 0): return freq_result
            sqrt_term = n_rpm * np.sqrt(d_shaft_mm)
            if sqrt_term == 0: return freq_result
            base_calc = (14000000 / sqrt_term) - (4 * d_shaft_mm)
            if base_calc <= 0: return freq_result
            t_grease_b = K * base_calc
            if t_grease_b > MAX_FREQUENCY_HOURS:
                t_grease_b = MAX_FREQUENCY_HOURS
            freq_result['frequency_hours'], freq_result['frequency_unit'] = t_grease_b, 'Hours'
        return freq_result
    
    def _get_correction_factors(self, row: pd.Series) -> Dict[str, float]:
        return {'Ft': self._get_ft(row), 'Fc': self._get_fc(row), 'Fh': self._get_fh(row), 'Fv': self._get_fv(row), 'Fp': self._get_fp(row), 'Fd': self._get_fd(row)}

    def _get_ft(self, row: pd.Series) -> float:
        temp_str = str(row.get('(D) Operating Temperature', '')).strip()
        temps_f = [float(t) for t in re.findall(r'(\d+\.?\d*)', temp_str)]
        if not temps_f: return 1.0
        avg_temp = sum(temps_f) / len(temps_f)
        if avg_temp < 150: return 1.0
        if 150 <= avg_temp <= 175: return 0.5
        if 175 < avg_temp <= 200: return 0.2
        return 0.1

    def _get_fc(self, row: pd.Series) -> float:
        ci_text = str(row.get('(D) Contaminant Abrasive Index', '')).lower()
        cl_text = str(row.get('(D) Contaminant Likelihood', '')).lower()
        ci_type = None
        if 'earthen' in ci_text or 'paper' in ci_text: ci_type = 'earthen'
        elif 'organic' in ci_text or 'food' in ci_text: ci_type = 'organic'
        elif 'heavy' in ci_text or 'mining' in ci_text: ci_type = 'heavy'
        elif 'metal' in ci_text or 'foundry' in ci_text: ci_type = 'metal'
        is_severe = 'severe' in cl_text or 'extreme' in cl_text or 'high' in cl_text
        if is_severe:
            if ci_type in ['earthen', 'organic']: return 0.7
            if ci_type in ['heavy', 'metal']: return 0.2
        else:
            if ci_type in ['earthen', 'organic']: return 1.0
            if ci_type in ['heavy', 'metal']: return 0.4
        return 1.0

    def _get_fh(self, row: pd.Series) -> float:
        arh_text = str(row.get('(D) Average Relative Humidity', '')).strip().replace('%', '')
        wcc_text = str(row.get('(D) Water Contact Conditions', '')).lower()
        if any(term in wcc_text for term in ["washdowns", "severe water", "submerged"]): return 0.1
        if any(term in wcc_text for term in ["steam/spray", "mild water", "moderate water"]): return 0.4
        try: humidity = float(re.findall(r'(\d+\.?\d*)', arh_text)[0])
        except (IndexError, ValueError): humidity = 0
        if humidity >= 75: return 0.7
        return 1.0

    def _get_fv(self, row: pd.Series) -> float:
        vib_text = str(row.get('(D) Vibration', '')).strip()
        if "> 0.4 ips" in vib_text: return 0.3
        if "0.2 to 0.4 ips" in vib_text: return 0.6
        return 1.0

    def _get_fp(self, row: pd.Series) -> float:
        pos_text = str(row.get('(D) Position', '')).lower()
        if 'vertical' in pos_text: return 0.3
        if '45' in pos_text: return 0.5
        return 1.0

    def _get_fd(self, row: pd.Series) -> float:
        design_text = str(row.get('(D) Bearing Type', '')).lower()
        if 'ball' in design_text: return 10.0
        if 'cylindrical' in design_text or 'needle' in design_text: return 5.0
        if 'tapered' in design_text or 'spherical' in design_text: return 1.0
        if 'journal' in design_text: return 1.0
        return 1.0