"""
ThermalCalculator con LÓGICA CONDICIONAL para Circulating vs Splash
- CORREGIDO: calculate_volumes ahora acepta `system_type` para cambiar la prioridad.
- Para 'circulating', se prioriza '(D) Oil Capacity'.
- Para 'splash' (default), se mantienen las dimensiones como prioridad.
"""

import pandas as pd
import numpy as np
import re
from typing import Dict, Tuple, Optional, Any
import logging

logger = logging.getLogger(__name__)

class ThermalCalculator:
    """Handles thermal expansion calculations for breather selection"""
    
    # Constants from Noria methodology
    OIL_EXPANSION_COEFFICIENT = 0.0003611  # γ (°F⁻¹)
    AIR_EXPANSION_COEFFICIENT = 0.001894   # β (°F⁻¹)
    CFM_SAFETY_FACTOR = 1.4               # Default safety factor
    GALLONS_TO_CUBIC_FEET = 7.48
    
    # Unit conversion factors
    LITERS_TO_GALLONS = 0.264172
    INCHES_CUBED_TO_GALLONS = 0.004329
    
    # Default oil percentage for splash/oil bath systems
    DEFAULT_OIL_PERCENTAGE = 0.30  # 30%
    
    def __init__(self, safety_factor: float = None):
        self.safety_factor = safety_factor or self.CFM_SAFETY_FACTOR
        
    def calculate_volumes(self, row: pd.Series, system_type: str = 'splash') -> Dict[str, Any]:
        """
        Calculate sump, oil, and air volumes with LOGIC PER SYSTEM TYPE.
        - 'circulating': Prioritizes (D) Oil Capacity.
        - 'splash': Prioritizes dimensions.
        """
        logger.info(f"=== Calculating Volume for Asset [{row.name}] | System Type: {system_type} ===")

        # --- LÓGICA PARA SISTEMAS CIRCULANTES ---
        if system_type == 'circulating':
            # Prioridad 1: Usar (D) Oil Capacity si existe
            has_oil_capacity, oil_cap_val = self._get_oil_capacity(row)
            if has_oil_capacity:
                logger.info("  -> [Circulating] Using OIL CAPACITY (Primary Method).")
                v_oil = oil_cap_val * self.LITERS_TO_GALLONS
                v_sump = v_oil / self.DEFAULT_OIL_PERCENTAGE if self.DEFAULT_OIL_PERCENTAGE > 0 else 0
                v_air = v_sump - v_oil
                return {
                    'v_sump': v_sump, 'v_oil': v_oil, 'v_air': v_air,
                    'calculation_method': 'oil_capacity_priority', 'volume_warning': ''
                }
            
            # Prioridad 2 (Fallback): Usar dimensiones si no hay Oil Capacity
            if self._has_full_dimensional_data(row):
                logger.info("  -> [Circulating] Using DIMENSIONS (Fallback Method).")
                return self._calculate_from_dimensions(row)

        # --- LÓGICA PARA SPLASH/OIL BATH (Y POR DEFECTO) ---
        else:
            # Prioridad 1: Usar dimensiones si existen
            if self._has_full_dimensional_data(row):
                logger.info("  -> [Splash] Using DIMENSIONS (Primary Method).")
                return self._calculate_from_dimensions(row)
            
            # Prioridad 2 (Fallback): Usar Oil Capacity si no hay dimensiones
            has_oil_capacity, oil_cap_val = self._get_oil_capacity(row)
            if has_oil_capacity:
                logger.info("  -> [Splash] Using OIL CAPACITY (Fallback Method).")
                v_oil = oil_cap_val * self.LITERS_TO_GALLONS
                v_sump = v_oil / self.DEFAULT_OIL_PERCENTAGE if self.DEFAULT_OIL_PERCENTAGE > 0 else 0
                v_air = v_sump - v_oil
                return {
                    'v_sump': v_sump, 'v_oil': v_oil, 'v_air': v_air,
                    'calculation_method': 'oil_capacity_fallback', 'volume_warning': ''
                }
        
        # Si ninguna de las lógicas funciona, se reporta error
        logger.warning(f"  -> No calculation method available for Asset Index [{row.name}]")
        return {
            'v_sump': 0.0, 'v_oil': 0.0, 'v_air': 0.0,
            'calculation_method': 'insufficient_data', 
            'volume_warning': 'Insufficient data for volume calculation'
        }

    def _calculate_from_dimensions(self, row: pd.Series) -> Dict[str, Any]:
        """Helper function to calculate volume from dimensional data."""
        height_val = row.get('(D) Height')
        width_val = row.get('(D) Width')
        length_val = row.get('(D) Length')
        oil_level_val = row.get('(D) Distance from Drain Port to Oil Level')

        height = self._convert_to_inches(height_val)
        width = self._convert_to_inches(width_val)
        length = self._convert_to_inches(length_val)
        oil_height = self._convert_to_inches(oil_level_val)
        
        v_sump = height * width * length * self.INCHES_CUBED_TO_GALLONS
        v_oil = oil_height * width * length * self.INCHES_CUBED_TO_GALLONS
        v_air = v_sump - v_oil

        warning_msg = self._perform_sanity_check(row, v_oil)
        
        return {
            'v_sump': v_sump, 'v_oil': v_oil, 'v_air': max(v_air, 0),
            'calculation_method': 'dimensions', 'volume_warning': warning_msg
        }

    def _has_full_dimensional_data(self, row: pd.Series) -> bool:
        """Checks if ALL required dimensional data is present."""
        required_cols = ['(D) Height', '(D) Width', '(D) Length', '(D) Distance from Drain Port to Oil Level']
        for col in required_cols:
            if col not in row or pd.isna(row[col]):
                return False
            try:
                if not float(row[col]) > 0: return False
            except (ValueError, TypeError):
                return False
        return True

    def _get_oil_capacity(self, row: pd.Series) -> Tuple[bool, float]:
        """Checks for a valid oil capacity value and returns it."""
        col = '(D) Oil Capacity'
        if col not in row or pd.isna(row[col]):
            return False, 0.0
        try:
            value = float(row[col])
            return value > 0, value
        except (ValueError, TypeError):
            return False, 0.0

    def _perform_sanity_check(self, row: pd.Series, v_oil_calculated: float) -> str:
        """Compares calculated oil volume with reported capacity."""
        has_cap, cap_val = self._get_oil_capacity(row)
        if has_cap:
            v_oil_reported_gal = cap_val * self.LITERS_TO_GALLONS
            
            if v_oil_calculated > 0.01 and v_oil_reported_gal > 0.01:
                diff_percentage = (v_oil_calculated - v_oil_reported_gal) / v_oil_reported_gal
                
                if abs(diff_percentage) > 0.25:
                    warning_msg = (
                        f"Warning: Calculated oil volume ({v_oil_calculated:.2f} gal) "
                        f"differs by {diff_percentage:+.0%} from reported capacity ({v_oil_reported_gal:.2f} gal). "
                        "Using calculated value for CFM."
                    )
                    logger.warning(f"For Asset Index [{row.name}], {warning_msg}")
                    return warning_msg
        return ""
    
    def _convert_to_inches(self, value) -> float:
        """Convert dimension to inches (assuming mm input if > 50)."""
        if pd.isna(value): return 0.0
        numeric_value = float(value)
        return numeric_value / 25.4 if numeric_value > 50 else numeric_value
    
    def extract_temperatures(self, operating_temp_str: str) -> Tuple[Optional[float], Optional[float]]:
        if pd.isna(operating_temp_str) or not operating_temp_str: return None, None
        try:
            pattern = r'(\d+(?:\.\d+)?)°F'
            matches = re.findall(pattern, str(operating_temp_str))
            if len(matches) >= 2:
                temps = [float(match) for match in matches]
                return min(temps), max(temps)
            elif len(matches) == 1:
                temp = float(matches[0])
                return temp, temp
            return None, None
        except Exception:
            return None, None
    
    def calculate_temperature_differential(self, 
                                        operating_temps: Tuple[Optional[float], Optional[float]],
                                        ambient_temps: Tuple[Optional[float], Optional[float]]) -> float:
        min_op, max_op = operating_temps
        min_amb, max_amb = ambient_temps
        
        all_temps = [t for t in [min_op, max_op, min_amb, max_amb] if t is not None]
        
        if not all_temps or len(all_temps) < 2: 
            return 40.0
            
        delta_t = max(all_temps) - min(all_temps)
        return delta_t if delta_t >= 10.0 else 40.0

    def calculate_thermal_expansion(self, volumes: Dict[str, float], delta_t: float) -> Dict[str, float]:
        """Calculates CFM requirement based on thermal expansion."""
        v_oil = volumes.get('v_oil', 0.0)
        v_air = volumes.get('v_air', 0.0)
        
        delta_v_oil = self.OIL_EXPANSION_COEFFICIENT * v_oil * delta_t
        delta_v_air = self.AIR_EXPANSION_COEFFICIENT * v_air * delta_t
        v_total_exp = delta_v_oil + delta_v_air
        
        cfm_required = (v_total_exp / self.GALLONS_TO_CUBIC_FEET) * self.safety_factor
        
        return {
            'delta_t': delta_t,
            'delta_v_oil': delta_v_oil,
            'delta_v_air': delta_v_air,
            'v_total_exp': v_total_exp,
            'cfm_required': cfm_required,
            'safety_factor_used': self.safety_factor
        }
    
    def calculate_complete_thermal_analysis(self, row: pd.Series, 
                                          ambient_temps: Tuple[Optional[float], Optional[float]],
                                          system_type: str = 'splash') -> Dict:
        results = {'success': False, 'error_message': '', 'cfm_required': 0.0}
        try:
            volumes = self.calculate_volumes(row, system_type=system_type)
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
            logger.error(f"Error in complete thermal analysis for Asset Index [{row.name}]: {str(e)}")
            results['error_message'] = str(e)
        
        return results