# utils/excel_handler.py (FINAL VERSION with validation for processed files and robust merging)

import os
import sys
import logging
from typing import Dict, Tuple, Any
import pandas as pd

def resource_path(relative_path: str) -> str:
    """
    Returns a valid path for both normal execution and PyInstaller bundled apps.
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class ExcelHandler:
    """Handles all Excel file operations for the analysis tool."""

    def __init__(self):
        self.data_report_df: pd.DataFrame | None = None
        self.breather_catalog_df: pd.DataFrame | None = None

    def _convert_to_boolean(self, value):
        """Robustly converts various values to boolean."""
        if pd.isna(value):
            return False
        str_val = str(value).strip().lower()
        return str_val in ['x', 'yes', 'true', '1', 'y', '1.0', 'si', 'sí']

    def load_breather_catalog(self, catalog_source: Any) -> bool:
        """
        Loads the breather catalog from a file path (str) or an in-memory file object.
        """
        try:
            df = None
            if isinstance(catalog_source, str):
                catalog_path = resource_path(catalog_source)
                if not os.path.exists(catalog_path):
                    logger.error(f"Breather catalog not found: {catalog_path}")
                    return False
                df = pd.read_excel(catalog_path, sheet_name="Breathers Specs", header=1)
            else:
                if hasattr(catalog_source, 'seek'):
                    catalog_source.seek(0)
                df = pd.read_excel(catalog_source, sheet_name="Breathers Specs", header=1)
            
            self.breather_catalog_df = df
        except Exception as e:
            logger.warning(f"Could not find 'Breathers Specs' sheet: {e}. Falling back to first sheet.")
            try:
                if isinstance(catalog_source, str):
                    df = pd.read_excel(resource_path(catalog_source), header=1)
                else:
                    if hasattr(catalog_source, 'seek'):
                        catalog_source.seek(0)
                    df = pd.read_excel(catalog_source, header=1)
                self.breather_catalog_df = df
            except Exception as inner_e:
                logger.error(f"Fallback loading of catalog also failed: {inner_e}")
                return False

        # Cleaning logic
        self.breather_catalog_df.columns = (
            self.breather_catalog_df.columns.str.strip()
            .str.replace('\r\n', ' ', regex=False).str.replace('\n', ' ', regex=False)
            .str.replace('  ', ' ', regex=False)
        )
        numeric_cols = ['Adsorption Capacity (mL)', 'Max Fluid Flow (gpm)', 'Gearbox, pump, storage Sump Volume MAX gal', 'Circulating/Hyd sump volume max gal.']
        for col in numeric_cols:
            if col in self.breather_catalog_df.columns:
                self.breather_catalog_df[col] = pd.to_numeric(self.breather_catalog_df[col].astype(str).str.replace(',', ''), errors='coerce')
        
        bool_cols = ['Extended Service', 'Mobile applications', 'Integrated oil mist control', 'High vibration', 'Rh 25 to 75%', 'Rh >75%', 'Water contact conditions Low', 'Water contact conditions Medium', 'Water contact conditions High', 'Contamination Index Particles Medium', 'Contamination Index Particles High']
        for col in bool_cols:
            if col in self.breather_catalog_df.columns:
                self.breather_catalog_df[col] = self.breather_catalog_df[col].apply(self._convert_to_boolean)

        logger.info(f"Successfully loaded {len(self.breather_catalog_df)} breathers from catalog")
        return True

    def load_data_report(self, file_source: Any) -> Tuple[bool, str]:
        """
        Loads and validates the Data Report from a path or file object,
        and checks if it has already been processed.
        """
        try:
            if not file_source:
                return False, "No file source provided."

            if hasattr(file_source, 'seek'):
                file_source.seek(0)
            df = pd.read_excel(file_source, sheet_name=None)
            
            sheet_name = "MPs" if "MPs" in df else list(df.keys())[0]
            df = df[sheet_name]

            # Validation "lock" for already processed files
            processed_columns = ['original_index', 'Breather_Model', 'Grease_g', 'CFM_Required', 'GPM_Source']
            if any(col in df.columns for col in processed_columns):
                return False, "Invalid Format: This file appears to be an already processed report. Please upload the original Data Report."

            if len(df.columns) < 9:
                return False, f"Data file must have at least 9 columns. Found {len(df.columns)}."
            self.data_report_df = df.copy()

            # Standardize Flow Rate column name
            flow_rate_col_found = next((col for col in self.data_report_df.columns if str(col).lower().strip() == '(d) flow rate'), None)
            if flow_rate_col_found and flow_rate_col_found != '(D) Flow Rate':
                self.data_report_df.rename(columns={flow_rate_col_found: '(D) Flow Rate'}, inplace=True)
            
            # Clean unit columns
            for col in ['(DU) Flow Rate', '(DU) Oil Capacity']:
                if col in self.data_report_df.columns:
                    self.data_report_df[col] = self.data_report_df[col].astype(str).fillna('').str.strip().str.lower()
            
            # Extract numeric from flow rate
            if '(D) Flow Rate' in self.data_report_df.columns:
                self.data_report_df['(D) Flow Rate'] = self.data_report_df['(D) Flow Rate'].astype(str).str.extract(r'(\d+\.?\d*)', expand=False)
            
            # Sanitize key numeric columns
            numeric_cols_to_sanitize = ['(D) Oil Capacity', '(D) Height', '(D) Width', '(D) Length', '(D) Distance from Drain Port to Oil Level', '(D) Flow Rate']
            for col in numeric_cols_to_sanitize:
                if col in self.data_report_df.columns:
                    self.data_report_df[col] = pd.to_numeric(self.data_report_df[col], errors='coerce')

            if self.data_report_df.empty:
                return False, "No records found in data report."
            
            logger.info(f"Successfully loaded {len(self.data_report_df)} total records")
            return True, ""
        except Exception as e:
            logger.error(f"Error loading data report: {str(e)}")
            return False, f"Error loading file: {str(e)}"

    def get_all_data(self) -> pd.DataFrame:
        return self.data_report_df.copy() if self.data_report_df is not None else pd.DataFrame()

    def get_gearbox_data(self) -> pd.DataFrame:
        if self.data_report_df is None: return pd.DataFrame()
        column_i = self.data_report_df.iloc[:, 8].astype(str)
        splash_types = ['Gearbox Housing (Oil)', 'Bearing (Oil)', 'Pump (Oil)', 'Electric Motor Bearing (Oil)', 'Blower (Oil)']
        mask = column_i.str.strip().isin(splash_types)
        return self.data_report_df[mask].copy()

    def get_circulating_data(self) -> pd.DataFrame:
        if self.data_report_df is None: return pd.DataFrame()
        column_i = self.data_report_df.iloc[:, 8].astype(str)
        circ_types = ['Circulating System Reservoir (Oil)', 'Hydraulic System Reservoir (Oil)']
        mask = column_i.str.strip().isin(circ_types)
        return self.data_report_df[mask].copy()

    def get_bearing_grease_data(self) -> pd.DataFrame:
        if self.data_report_df is None: return pd.DataFrame()
        column_i = self.data_report_df.iloc[:, 8].astype(str)
        mask = column_i.str.contains('Bearing.*Grease', case=False, na=False, regex=True)
        return self.data_report_df[mask].copy()
        
    def get_breather_catalog(self) -> pd.DataFrame:
        return self.breather_catalog_df.copy() if self.breather_catalog_df is not None else pd.DataFrame()

    def merge_results_with_original(self, results_df: pd.DataFrame) -> pd.DataFrame:
        """
        Merges the results DataFrame with the original data report DataFrame.
        """
        if self.data_report_df is None:
            logger.warning("Original data report not available for merging. Returning results only.")
            return results_df

        if 'original_index' not in results_df.columns:
            logger.error("Results DataFrame is missing 'original_index' for merging.")
            # Fallback: Try to merge on the regular index if it seems to match
            if self.data_report_df.index.equals(results_df.index):
                return pd.concat([self.data_report_df, results_df], axis=1)
            return self.data_report_df

        original_with_index = self.data_report_df.reset_index().rename(columns={'index': 'original_index'})
        
        # Drop any existing columns from original that are in results to avoid duplication issues
        cols_to_drop = [col for col in results_df.columns if col in original_with_index.columns and col != 'original_index']
        original_df_cleaned = original_with_index.drop(columns=cols_to_drop, errors='ignore')

        final_df = pd.merge(original_df_cleaned, results_df, on='original_index', how='left')
        
        final_df = final_df.drop(columns=['original_index'])
        
        return final_df