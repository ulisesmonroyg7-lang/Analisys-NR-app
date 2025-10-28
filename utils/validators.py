"""
Validation utilities for NoRia Breather Selection App
Data validation, format checking, and error handling
"""

import pandas as pd
import numpy as np
import re
from typing import Dict, List, Tuple, Optional, Any
import logging

logger = logging.getLogger(__name__)

class DataValidator:
    """Handles validation of input data and configuration"""
    
    # Required columns in Data Report for basic functionality
    REQUIRED_COLUMNS = [
        'ComponentTemplate',
        '(D) Oil Capacity'
    ]
    
    # Optional columns that enhance functionality
    OPTIONAL_COLUMNS = [
        '(D) Height',
        '(D) Width', 
        '(D) Length',
        '(D) Distance from Drain Port to Oil Level',
        '(D) Operating Temperature',
        '(D) Contaminant Likelihood',
        '(D) Water Contact Conditions',
        '(D) Oil Mist Evidence on Headspace',
        '(D) Average Relative Humidity',
        '(D) Vibration',
        '(D) Breather/Fill Port Clearance'
    ]
    
    # Expected breather catalog columns
    BREATHER_CATALOG_COLUMNS = [
        'Brand',
        'Model',
        'Type',
        'Max Air Flow (cfm)',
        'Height (in)',
        'Diameter (in)'
    ]
    
    def __init__(self):
        self.validation_errors = []
        self.validation_warnings = []
    
    def validate_data_report(self, df: pd.DataFrame) -> Tuple[bool, List[str], List[str]]:
        """
        Validate Data Report DataFrame
        
        Args:
            df: Data Report DataFrame
            
        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        self.validation_errors = []
        self.validation_warnings = []
        
        # Check if DataFrame is empty
        if df.empty:
            self.validation_errors.append("Data Report is empty")
            return False, self.validation_errors, self.validation_warnings
        
        # Check required columns
        self._check_required_columns(df, self.REQUIRED_COLUMNS)
        
        # Check for gearbox records
        self._check_gearbox_records(df)
        
        # Validate data types and formats
        self._validate_data_formats(df)
        
        # Check data completeness
        self._check_data_completeness(df)
        
        # Validate specific field formats
        self._validate_temperature_format(df)
        self._validate_oil_capacity_format(df)
        self._validate_dimensional_data(df)
        
        is_valid = len(self.validation_errors) == 0
        return is_valid, self.validation_errors, self.validation_warnings
    
    def validate_breather_catalog(self, df: pd.DataFrame) -> Tuple[bool, List[str], List[str]]:
        """
        Validate Breather Catalog DataFrame
        
        Args:
            df: Breather catalog DataFrame
            
        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        self.validation_errors = []
        self.validation_warnings = []
        
        if df.empty:
            self.validation_errors.append("Breather catalog is empty")
            return False, self.validation_errors, self.validation_warnings
        
        # Check required columns
        self._check_required_columns(df, self.BREATHER_CATALOG_COLUMNS)
        
        # Validate breather data
        self._validate_breather_data(df)
        
        is_valid = len(self.validation_errors) == 0
        return is_valid, self.validation_errors, self.validation_warnings
    
    def validate_configuration(self, config: Dict) -> Tuple[bool, List[str], List[str]]:
        """
        Validate configuration parameters
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        self.validation_errors = []
        self.validation_warnings = []
        
        # Validate criticality
        criticality = config.get('criticality')
        if criticality not in ['A', 'B1', 'B2', 'C']:
            self.validation_errors.append(f"Invalid criticality: {criticality}")
        
        # Validate temperature settings
        if not config.get('auto_temp_lookup', True):
            self._validate_manual_temperatures(config)
        
        # Validate safety factor
        safety_factor = config.get('safety_factor', 1.4)
        if not isinstance(safety_factor, (int, float)) or safety_factor < 1.0 or safety_factor > 2.0:
            self.validation_errors.append(f"Safety factor must be between 1.0 and 2.0, got: {safety_factor}")
        
        # Validate boolean flags
        boolean_configs = ['mobile_application', 'high_particle_removal', 'auto_temp_lookup']
        for key in boolean_configs:
            value = config.get(key, False)
            if not isinstance(value, bool):
                self.validation_warnings.append(f"Config '{key}' should be boolean, got: {type(value)}")
        
        is_valid = len(self.validation_errors) == 0
        return is_valid, self.validation_errors, self.validation_warnings
    
    def _check_required_columns(self, df: pd.DataFrame, required_columns: List[str]):
        """Check if required columns are present"""
        missing_columns = []
        for col in required_columns:
            if col not in df.columns:
                missing_columns.append(col)
        
        if missing_columns:
            self.validation_errors.append(f"Missing required columns: {', '.join(missing_columns)}")
    
    def _check_gearbox_records(self, df: pd.DataFrame):
        """Check for valid gearbox records"""
        if 'ComponentTemplate' not in df.columns:
            return
        
        gearbox_mask = df['ComponentTemplate'] == 'Gearbox (Oil)'
        gearbox_count = gearbox_mask.sum()
        
        if gearbox_count == 0:
            self.validation_errors.append("No gearbox records found with ComponentTemplate='Gearbox (Oil)'")
        else:
            logger.info(f"Found {gearbox_count} gearbox records out of {len(df)} total records")
            
            if gearbox_count < len(df):
                other_count = len(df) - gearbox_count
                self.validation_warnings.append(f"{other_count} non-gearbox records will be ignored")
    
    def _validate_data_formats(self, df: pd.DataFrame):
        """Validate data types and formats"""
        
        # Check numeric columns
        numeric_columns = [
            '(D) Oil Capacity',
            '(D) Height',
            '(D) Width',
            '(D) Length',
            '(D) Distance from Drain Port to Oil Level',
            '(D) Average Relative Humidity'
        ]
        
        for col in numeric_columns:
            if col in df.columns:
                non_numeric = df[col].apply(lambda x: pd.notna(x) and not self._is_numeric(x))
                if non_numeric.any():
                    invalid_count = non_numeric.sum()
                    self.validation_warnings.append(f"Column '{col}' has {invalid_count} non-numeric values")
    
    def _validate_temperature_format(self, df: pd.DataFrame):
        """Validate operating temperature format"""
        temp_col = '(D) Operating Temperature'
        if temp_col not in df.columns:
            return
        
        invalid_temps = 0
        for idx, temp_str in df[temp_col].dropna().items():
            if not self._is_valid_temperature_format(str(temp_str)):
                invalid_temps += 1
        
        if invalid_temps > 0:
            self.validation_warnings.append(f"{invalid_temps} records have invalid temperature format")
    
    def _validate_oil_capacity_format(self, df: pd.DataFrame):
        """Validate oil capacity data"""
        oil_col = '(D) Oil Capacity'
        if oil_col not in df.columns:
            return
        
        # Check for reasonable oil capacity values (assuming liters)
        oil_values = pd.to_numeric(df[oil_col], errors='coerce')
        
        # Check for unreasonable values
        too_small = (oil_values < 0.1) & (oil_values.notna())
        too_large = (oil_values > 10000) & (oil_values.notna())
        
        if too_small.any():
            self.validation_warnings.append(f"{too_small.sum()} records have very small oil capacity (<0.1L)")
        
        if too_large.any():
            self.validation_warnings.append(f"{too_large.sum()} records have very large oil capacity (>10000L)")
    
    def _validate_dimensional_data(self, df: pd.DataFrame):
        """Validate dimensional data consistency"""
        dim_cols = ['(D) Height', '(D) Width', '(D) Length']
        
        if not all(col in df.columns for col in dim_cols):
            return
        
        # Check for records with partial dimensional data
        dim_data = df[dim_cols]
        partial_data = dim_data.notna().sum(axis=1)
        
        # Records with some but not all dimensions
        partial_mask = (partial_data > 0) & (partial_data < 3)
        if partial_mask.any():
            partial_count = partial_mask.sum()
            self.validation_warnings.append(f"{partial_count} records have incomplete dimensional data")
        
        # Check for unreasonable dimension values
        for col in dim_cols:
            values = pd.to_numeric(df[col], errors='coerce')
            
            # Assuming dimensions could be in mm or inches
            too_small = (values < 1) & (values.notna())
            too_large = (values > 5000) & (values.notna())
            
            if too_small.any():
                self.validation_warnings.append(f"Column '{col}' has {too_small.sum()} very small values (<1)")
            
            if too_large.any():
                self.validation_warnings.append(f"Column '{col}' has {too_large.sum()} very large values (>5000)")
    
    def _validate_breather_data(self, df: pd.DataFrame):
        """Validate breather catalog data"""
        
        # Check CFM values
        cfm_col = 'Max Air Flow (cfm)'
        if cfm_col in df.columns:
            cfm_values = pd.to_numeric(df[cfm_col], errors='coerce')
            invalid_cfm = cfm_values.isna() | (cfm_values <= 0)
            
            if invalid_cfm.any():
                self.validation_errors.append(f"{invalid_cfm.sum()} breathers have invalid CFM values")
        
        # Check dimensions
        for dim_col in ['Height (in)', 'Diameter (in)']:
            if dim_col in df.columns:
                dim_values = pd.to_numeric(df[dim_col], errors='coerce')
                invalid_dims = dim_values.isna() | (dim_values <= 0)
                
                if invalid_dims.any():
                    self.validation_warnings.append(f"{invalid_dims.sum()} breathers have invalid {dim_col}")
        
        # Check for duplicate models
        if 'Model' in df.columns:
            duplicates = df['Model'].duplicated()
            if duplicates.any():
                self.validation_warnings.append(f"{duplicates.sum()} duplicate breather models found")
    
    def _check_data_completeness(self, df: pd.DataFrame):
        """Check completeness of critical data"""
        
        # Filter to gearbox records only
        if 'MaintPointTemplate' in df.columns:
            gearbox_df = df[df['MaintPointTemplate'] == 'Gearbox Housing (Oil)']
        else:
            gearbox_df = df
        
        if gearbox_df.empty:
            return
        
        # Check oil capacity completeness
        oil_col = '(D) Oil Capacity'
        if oil_col in gearbox_df.columns:
            missing_oil = gearbox_df[oil_col].isna().sum()
            if missing_oil > 0:
                self.validation_errors.append(f"{missing_oil} gearbox records missing oil capacity data")
        
        # Check for records with no dimensional or oil capacity data
        dim_cols = ['(D) Height', '(D) Width', '(D) Length']
        has_dimensions = False
        has_oil_capacity = False
        
        if all(col in gearbox_df.columns for col in dim_cols):
            has_dimensions = gearbox_df[dim_cols].notna().all(axis=1).any()
        
        if oil_col in gearbox_df.columns:
            has_oil_capacity = gearbox_df[oil_col].notna().any()
        
        if not has_dimensions and not has_oil_capacity:
            self.validation_errors.append("No records have sufficient data for volume calculations")
    
    def _validate_manual_temperatures(self, config: Dict):
        """Validate manual temperature settings"""
        max_temp = config.get('max_amb_temp')
        min_temp = config.get('min_amb_temp')
        
        if max_temp is not None:
            if not isinstance(max_temp, (int, float)):
                self.validation_errors.append("Maximum ambient temperature must be numeric")
            elif max_temp < -50 or max_temp > 200:
                self.validation_errors.append("Maximum ambient temperature out of reasonable range (-50°F to 200°F)")
        
        if min_temp is not None:
            if not isinstance(min_temp, (int, float)):
                self.validation_errors.append("Minimum ambient temperature must be numeric")
            elif min_temp < -50 or min_temp > 200:
                self.validation_errors.append("Minimum ambient temperature out of reasonable range (-50°F to 200°F)")
        
        if max_temp is not None and min_temp is not None:
            if max_temp <= min_temp:
                self.validation_errors.append("Maximum ambient temperature must be greater than minimum")
    
    def _is_numeric(self, value) -> bool:
        """Check if value can be converted to numeric"""
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False
    
    def _is_valid_temperature_format(self, temp_str: str) -> bool:
        """Check if temperature string has valid format"""
        if not temp_str or pd.isna(temp_str):
            return False
        
        # Look for temperature patterns like "125°F", "125°F - 150°F", etc.
        patterns = [
            r'\d+(?:\.\d+)?°F',  # Single temperature
            r'\d+(?:\.\d+)?°F.*\d+(?:\.\d+)?°F',  # Temperature range
        ]
        
        for pattern in patterns:
            if re.search(pattern, str(temp_str)):
                return True
        
        return False

class ConfigValidator:
    """Specialized validator for configuration parameters"""
    
    @staticmethod
    def validate_criticality(criticality: str) -> bool:
        """Validate criticality setting"""
        return criticality in ['A', 'B1', 'B2', 'C']
    
    @staticmethod
    def validate_temperature_range(min_temp: float, max_temp: float) -> Tuple[bool, str]:
        """Validate temperature range"""
        if min_temp >= max_temp:
            return False, "Maximum temperature must be greater than minimum temperature"
        
        if min_temp < -50 or max_temp > 200:
            return False, "Temperatures must be within -50°F to 200°F range"
        
        if max_temp - min_temp < 5:
            return False, "Temperature range should be at least 5°F"
        
        return True, ""
    
    @staticmethod
    def validate_safety_factor(factor: float) -> Tuple[bool, str]:
        """Validate CFM safety factor"""
        if not isinstance(factor, (int, float)):
            return False, "Safety factor must be numeric"
        
        if factor < 1.0 or factor > 2.0:
            return False, "Safety factor must be between 1.0 and 2.0"
        
        return True, ""

def validate_file_format(file_path: str) -> Tuple[bool, str]:
    """
    Validate file format and accessibility
    
    Args:
        file_path: Path to file to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    import os
    
    if not os.path.exists(file_path):
        return False, "File does not exist"
    
    if not file_path.lower().endswith(('.xlsx', '.xls')):
        return False, "File must be an Excel file (.xlsx or .xls)"
    
    try:
        # Try to open file to check if it's corrupted
        pd.read_excel(file_path, nrows=1)
        return True, ""
    except Exception as e:
        return False, f"Cannot read Excel file: {str(e)}"

def sanitize_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sanitize DataFrame by cleaning common data issues
    
    Args:
        df: Input DataFrame
        
    Returns:
        Cleaned DataFrame
    """
    df_clean = df.copy()
    
    # Strip whitespace from string columns
    string_columns = df_clean.select_dtypes(include=['object']).columns
    for col in string_columns:
        df_clean[col] = df_clean[col].astype(str).str.strip()
        # Replace 'nan' strings with actual NaN
        df_clean[col] = df_clean[col].replace('nan', np.nan)
    
    # Clean numeric columns
    numeric_columns = [
        '(D) Oil Capacity',
        '(D) Height',
        '(D) Width',
        '(D) Length',
        '(D) Distance from Drain Port to Oil Level',
        '(D) Average Relative Humidity'
    ]
    
    for col in numeric_columns:
        if col in df_clean.columns:
            # Convert to numeric, setting errors to NaN
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    
    return df_clean