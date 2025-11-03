# core/calculations.py (Versión Final Definitiva - Prioriza Oil Capacity)

import pandas as pd
import numpy as np
import re
from typing import Dict, Tuple, Optional, Any
import logging

logger = logging.getLogger(__name__)

class ThermalCalculator:
    OIL_EXPANSION_COEFFICIENT = 0.0003611
    AIR_EXPANSION_COEFFICIENT = 0.001894
    CFM_SAFETY_FACTOR = 1.4
    GALLONS_TO_CUBIC_FEET = 7.48
    LITERS_TO_GALLONS = 0.264172
    INCHES_CUBED_TO_GALLONS = 0.004329
    DEFAULT_OIL_PERCENTAGE = 0.30

    def __init__(self, safety_factor: float = None):
        self.safety_factor = safety_factor or self.CFM_SAFETY_FACTOR

    def calculate_volumes(self, row: pd.Series) -> Dict[str, Any]:
        """
        Calcula los volúmenes con una jerarquía de precisión:
        1. (Prioridad Máxima) Usa (D) Oil Capacity si está disponible, convirtiendo de litros a galones.
        2. (Fallback) Si no, usa dimensiones físicas completas.
        """
        
        # --- LÓGICA DE PRIORIZACIÓN CORREGIDA ---
        # PRIORIDAD 1: Usar (D) Oil Capacity si existe.
        oil_cap_value = row.get('(D) Oil Capacity')
        if pd.notna(oil_cap_value) and oil_cap_value > 0:
            logger.info(f"Asset {row.name}: Using (D) Oil Capacity as primary source.")
            
            unit = str(row.get('(DU) Oil Capacity', 'liters')).lower().strip()
            v_oil = 0
            
            # Por defecto, asumimos que el valor está en litros si la unidad está vacía o dice 'liters'
            if 'gallon' in unit or 'gal' in unit:
                v_oil = oil_cap_value
                logger.info(f"Asset {row.name}: Unit is '{unit}'. Using value directly: {v_oil:.2f} gallons.")
            else: # Asumir litros por defecto
                v_oil = oil_cap_value * self.LITERS_TO_GALLONS
                logger.info(f"Asset {row.name}: Assuming unit is liters. Converting {oil_cap_value}L to {v_oil:.2f} gallons.")

            # Estimar el resto de los volúmenes
            v_sump = v_oil / self.DEFAULT_OIL_PERCENTAGE if self.DEFAULT_OIL_PERCENTAGE > 0 else 0
            v_air = v_sump - v_oil
            return {
                'v_sump': v_sump, 'v_oil': v_oil, 'v_air': v_air,
                'calculation_method': 'oil_capacity_priority', 'volume_warning': ''
            }

        # PRIORIDAD 2 (FALLBACK): Intenta el cálculo por dimensiones si no hay Oil Capacity.
        if self._has_full_dimensional_data(row):
            logger.info(f"Asset {row.name}: No (D) Oil Capacity found. Using calculation by dimensions (Fallback).")
            
            oil_height_mm = row.get('(D) Distance from Drain Port to Oil Level')
            width_mm = row.get('(D) Width')
            length_mm = row.get('(D) Length')
            total_height_mm = row.get('(D) Height')

            shl_in = self._convert_mm_to_inches(oil_height_mm)
            sw_in = self._convert_mm_to_inches(width_mm)
            sl_in = self._convert_mm_to_inches(length_mm)
            sh_in = self._convert_mm_to_inches(total_height_mm)

            v_oil = shl_in * sw_in * sl_in * self.INCHES_CUBED_TO_GALLONS
            v_sump = sh_in * sw_in * sl_in * self.INCHES_CUBED_TO_GALLONS
            v_air = v_sump - v_oil

            logger.info(f"Asset {row.name}: Calculated v_oil = {v_oil:.2f} gallons from dimensions.")

            return {
                'v_sump': v_sump, 'v_oil': v_oil, 'v_air': max(v_air, 0),
                'calculation_method': 'dimensions_fallback', 'volume_warning': ''
            }
            
        # Si no hay ningún dato
        logger.warning(f"Asset {row.name}: Insufficient data to calculate volume.")
        return {
            'v_sump': 0.0, 'v_oil': 0.0, 'v_air': 0.0,
            'calculation_method': 'insufficient_data', 
            'volume_warning': 'Insufficient data for volume calculation'
        }

    def _has_full_dimensional_data(self, row: pd.Series) -> bool:
        required_cols = ['(D) Height', '(D) Width', '(D) Length', '(D) Distance from Drain Port to Oil Level']
        for col in required_cols:
            val = row.get(col)
            if pd.isna(val) or val <= 0:
                return False
        return True

    def _convert_mm_to_inches(self, value) -> float:
        if pd.isna(value): return 0.0
        return float(value) / 25.4

    def extract_temperatures(self, operating_temp_str: str) -> Tuple[Optional[float], Optional[float]]:
        if pd.isna(operating_temp_str) or not operating_temp_str: return None, None
        try:
            matches = re.findall(r'(\d+\.?\d*)', str(operating_temp_str))
            if matches:
                temps = [float(m) for m in matches]
                return min(temps), max(temps)
            return None, None
        except Exception:
            return None, None
    
    def calculate_temperature_differential(self, operating_temps: Tuple[Optional[float], Optional[float]], ambient_temps: Tuple[Optional[float], Optional[float]]) -> float:
        min_op, max_op = operating_temps
        min_amb, max_amb = ambient_temps
        all_temps = [t for t in [min_op, max_op, min_amb, max_amb] if t is not None]
        if not all_temps or len(all_temps) < 2: return 40.0
        delta_t = max(all_temps) - min(all_temps)
        return delta_t if delta_t >= 10.0 else 40.0

    def calculate_thermal_expansion(self, volumes: Dict[str, float], delta_t: float) -> Dict[str, float]:
        v_oil = volumes.get('v_oil', 0.0)
        v_air = volumes.get('v_air', 0.0)
        delta_v_oil = self.OIL_EXPANSION_COEFFICIENT * v_oil * delta_t
        delta_v_air = self.AIR_EXPANSION_COEFFICIENT * v_air * delta_t
        v_total_exp = delta_v_oil + delta_v_air
        cfm_required = (v_total_exp / self.GALLONS_TO_CUBIC_FEET) * self.safety_factor
        return {'delta_t': delta_t, 'delta_v_oil': delta_v_oil, 'delta_v_air': delta_v_air, 'v_total_exp': v_total_exp, 'cfm_required': cfm_required, 'safety_factor_used': self.safety_factor}
    
    def calculate_complete_thermal_analysis(self, row: pd.Series, ambient_temps: Tuple[Optional[float], Optional[float]]) -> Dict:
        results = {'success': False, 'error_message': '', 'cfm_required': 0.0}
        try:
            volumes = self.calculate_volumes(row)
            results['volumes'] = volumes
            if volumes['calculation_method'] == 'insufficient_data':
                results['error_message'] = volumes['volume_warning']
                return results
            operating_temp_str = row.get('(D) Operating Temperature', '')
            operating_temps = self.extract_temperatures(operating_temp_str)
            delta_t = self.calculate_temperature_differential(operating_temps, ambient_temps)
            expansion = self.calculate_thermal_expansion(volumes, delta_t)
            results.update(expansion)
            results['success'] = True
        except Exception as e:
            logger.error(f"Error in complete thermal analysis for Asset {row.name}: {str(e)}")
            results['error_message'] = str(e)
        return results