"""
ThermalCalculator con DEBUG MEJORADO para identificar problemas con Oil Capacity
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
        
    def calculate_volumes(self, row: pd.Series) -> Dict[str, Any]:
        """
        Calculate sump, oil, and air volumes with ENHANCED DEBUGGING
        """
        # Get all relevant values
        height_val = row.get('(D) Height')
        width_val = row.get('(D) Width')
        length_val = row.get('(D) Length')
        oil_level_val = row.get('(D) Distance from Drain Port to Oil Level')
        oil_cap_val = row.get('(D) Oil Capacity')

        logger.info(f"=== DEBUGGING Asset Index [{row.name}] ===")
        logger.info(f"Raw values from row:")
        logger.info(f"  - Height: {height_val} (type: {type(height_val)})")
        logger.info(f"  - Width: {width_val} (type: {type(width_val)})")
        logger.info(f"  - Length: {length_val} (type: {type(length_val)})")
        logger.info(f"  - Oil Level: {oil_level_val} (type: {type(oil_level_val)})")
        logger.info(f"  - Oil Capacity: {oil_cap_val} (type: {type(oil_cap_val)})")

        # Step 1: Check for full dimensional data
        has_dimensions = self._has_full_dimensional_data(row)
        logger.info(f"Step 1 - Has full dimensions: {has_dimensions}")
        
        if has_dimensions:
            logger.info("  -> Using DIMENSIONS for volume calculation (Primary Method).")
            
            height = self._convert_to_inches(height_val)
            width = self._convert_to_inches(width_val)
            length = self._convert_to_inches(length_val)
            oil_height = self._convert_to_inches(oil_level_val)
            
            v_sump = height * width * length * self.INCHES_CUBED_TO_GALLONS
            v_oil = oil_height * width * length * self.INCHES_CUBED_TO_GALLONS
            v_air = v_sump - v_oil

            warning_msg = self._perform_sanity_check(row, v_oil)
            logger.info(f"  -> Calculated: v_sump={v_sump:.2f}, v_oil={v_oil:.2f}, v_air={v_air:.2f}")

            return {
                'v_sump': v_sump, 'v_oil': v_oil, 'v_air': max(v_air, 0),
                'calculation_method': 'dimensions', 'volume_warning': warning_msg
            }
            
        # Step 2: Check for oil capacity (WITH ENHANCED DEBUG)
        has_oil_capacity = self._has_oil_capacity_debug(row)
        logger.info(f"Step 2 - Has oil capacity: {has_oil_capacity}")
        
        if has_oil_capacity:
            logger.info("  -> Using OIL CAPACITY for volume calculation (Fallback Method).")
            
            # Convert to gallons
            v_oil = oil_cap_val * self.LITERS_TO_GALLONS
            v_sump = v_oil / self.DEFAULT_OIL_PERCENTAGE if self.DEFAULT_OIL_PERCENTAGE > 0 else 0
            v_air = v_sump - v_oil
            
            logger.info(f"  -> Oil Capacity Calculation:")
            logger.info(f"     • Input: {oil_cap_val}L")
            logger.info(f"     • v_oil = {oil_cap_val} * {self.LITERS_TO_GALLONS} = {v_oil:.2f} gal")
            logger.info(f"     • v_sump = {v_oil:.2f} / {self.DEFAULT_OIL_PERCENTAGE} = {v_sump:.2f} gal")
            logger.info(f"     • v_air = {v_sump:.2f} - {v_oil:.2f} = {v_air:.2f} gal")
            
            return {
                'v_sump': v_sump, 'v_oil': v_oil, 'v_air': v_air,
                'calculation_method': 'oil_capacity', 'volume_warning': ''
            }
            
        # Step 3: No data available
        logger.warning(f"  -> No calculation method available for Asset Index [{row.name}]")
        return {
            'v_sump': 0.0, 'v_oil': 0.0, 'v_air': 0.0,
            'calculation_method': 'insufficient_data', 
            'volume_warning': 'Insufficient data for volume calculation - no dimensions or oil capacity'
        }

    def _has_full_dimensional_data(self, row: pd.Series) -> bool:
        """Checks if ALL required dimensional data is present with DEBUG"""
        required_cols = ['(D) Height', '(D) Width', '(D) Length', '(D) Distance from Drain Port to Oil Level']
        
        results = {}
        for col in required_cols:
            has_col = col in row
            is_not_na = pd.notna(row[col]) if has_col else False
            is_positive = row[col] > 0 if has_col and is_not_na else False
            
            results[col] = {
                'exists': has_col,
                'not_na': is_not_na, 
                'positive': is_positive,
                'value': row.get(col, 'MISSING')
            }
            
        all_good = all(r['exists'] and r['not_na'] and r['positive'] for r in results.values())
        
        logger.info(f"Dimensional data check:")
        for col, result in results.items():
            status = "✅" if result['exists'] and result['not_na'] and result['positive'] else "❌"
            logger.info(f"  {status} {col}: {result['value']} (exists: {result['exists']}, not_na: {result['not_na']}, positive: {result['positive']})")
            
        return all_good

    def _has_oil_capacity_debug(self, row: pd.Series) -> bool:
        """Check oil capacity with ENHANCED DEBUG"""
        col = '(D) Oil Capacity'
        
        # Check if column exists
        col_exists = col in row
        logger.info(f"Oil capacity debug:")
        logger.info(f"  • Column '{col}' exists in row: {col_exists}")
        
        if not col_exists:
            logger.info(f"  • Available columns: {list(row.index)}")
            return False
            
        # Get the value
        value = row[col]
        logger.info(f"  • Raw value: {repr(value)} (type: {type(value)})")
        
        # Check if not NaN
        is_not_na = pd.notna(value)
        logger.info(f"  • Is not NaN: {is_not_na}")
        
        if not is_not_na:
            return False
            
        # Try to convert to float if it's a string
        try:
            if isinstance(value, str):
                # Handle potential comma separators
                clean_value = value.replace(',', '')
                float_value = float(clean_value)
                logger.info(f"  • Converted string '{value}' to float: {float_value}")
            else:
                float_value = float(value)
                logger.info(f"  • Converted to float: {float_value}")
                
            is_positive = float_value > 0
            logger.info(f"  • Is positive: {is_positive}")
            
            return is_positive
            
        except (ValueError, TypeError) as e:
            logger.info(f"  • Failed to convert to float: {e}")
            return False

    def _perform_sanity_check(self, row: pd.Series, v_oil_calculated: float) -> str:
        """Compares calculated oil volume with reported capacity"""
        reported_oil_capacity_liters = row.get('(D) Oil Capacity')
        if pd.notna(reported_oil_capacity_liters) and reported_oil_capacity_liters > 0:
            v_oil_reported_gal = reported_oil_capacity_liters * self.LITERS_TO_GALLONS
            
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
        """Calculates CFM requirement based on thermal expansion WITH DEBUG"""
        v_oil = volumes.get('v_oil', 0.0)
        v_air = volumes.get('v_air', 0.0)
        
        delta_v_oil = self.OIL_EXPANSION_COEFFICIENT * v_oil * delta_t
        delta_v_air = self.AIR_EXPANSION_COEFFICIENT * v_air * delta_t
        v_total_exp = delta_v_oil + delta_v_air
        
        cfm_required = (v_total_exp / self.GALLONS_TO_CUBIC_FEET) * self.safety_factor
        
        logger.info(f"Thermal expansion calculation:")
        logger.info(f"  • v_oil: {v_oil:.2f} gal, v_air: {v_air:.2f} gal")
        logger.info(f"  • ΔT: {delta_t:.1f}°F")
        logger.info(f"  • ΔV_oil: {delta_v_oil:.4f} gal")
        logger.info(f"  • ΔV_air: {delta_v_air:.4f} gal")
        logger.info(f"  • V_total_exp: {v_total_exp:.4f} gal")
        logger.info(f"  • CFM required: {cfm_required:.3f} CFM")
        
        return {
            'delta_t': delta_t,
            'delta_v_oil': delta_v_oil,
            'delta_v_air': delta_v_air,
            'v_total_exp': v_total_exp,
            'cfm_required': cfm_required,
            'safety_factor_used': self.safety_factor
        }
    
    def calculate_complete_thermal_analysis(self, row: pd.Series, 
                                          ambient_temps: Tuple[Optional[float], Optional[float]]) -> Dict:
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
            logger.error(f"Error in complete thermal analysis for Asset Index [{row.name}]: {str(e)}")
            results['error_message'] = str(e)
        
        return results