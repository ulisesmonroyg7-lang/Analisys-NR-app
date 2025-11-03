# utils/excel_handler.py (Versión Completa y Correcta)

"""
Excel Handler for NoRia Analysis Tool - VERSIÓN CORREGIDA Y AMPLIADA
- ✅ CORRECCIÓN CRÍTICA: Estandariza '(D) Flow rate' → '(D) Flow Rate' al cargar
- ✅ **NUEVO**: La sanitización de columnas numéricas ahora incluye TODAS las columnas
         necesarias para el análisis de grasa, asegurando cálculos correctos.
- Mantiene compatibilidad con ambas variantes en el Excel original
"""

import pandas as pd
import os
from typing import Dict, Tuple
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ExcelHandler:
    """Handles all Excel file operations for the analysis tool - CORRECTED VERSION"""

    def __init__(self):
        self.data_report_df = None
        self.breather_catalog_df = None

    def _convert_to_boolean(self, value):
        """Convierte valores diversos a boolean de forma robusta."""
        if pd.isna(value):
            return False
        str_val = str(value).strip().lower()
        return str_val in ['x', 'yes', 'true', '1', 'y', '1.0', 'si', 'sí']

    def load_breather_catalog(self, catalog_path: str = "data/breathers_catalog.xlsx") -> bool:
        """
        Load the breather catalog from Excel file with robust data type conversion.
        """
        try:
            if not os.path.exists(catalog_path):
                logger.error(f"Breather catalog not found: {catalog_path}")
                return False

            try:
                self.breather_catalog_df = pd.read_excel(catalog_path, sheet_name="Breathers Specs", header=1)
            except (ValueError, Exception):
                 self.breather_catalog_df = pd.read_excel(catalog_path, header=1)

            self.breather_catalog_df.columns = (
                self.breather_catalog_df.columns.str.strip().str.replace('\r\n', ' ').str.replace('\n', ' ').str.replace('  ', ' ')
            )

            numeric_cols_with_commas = [
                'Adsorption Capacity (mL)', 'Max Fluid Flow (gpm)',
                'Gearbox, pump, storage Sump Volume MAX gal',
                'Circulating/Hyd sump volume max gal.'
            ]
            for col in numeric_cols_with_commas:
                if col in self.breather_catalog_df.columns:
                    self.breather_catalog_df[col] = pd.to_numeric(
                        self.breather_catalog_df[col].astype(str).str.replace(',', ''),
                        errors='coerce'
                    )

            string_columns = ['Brand', 'Model', 'Series', 'Type', 'Connection']
            for col in string_columns:
                if col in self.breather_catalog_df.columns:
                    self.breather_catalog_df[col] = self.breather_catalog_df[col].fillna('N/A')

            boolean_columns = [
                'Extended Service', 'Mobile applications', 'Integrated oil mist control',
                'High vibration', 'Rh 25 to 75%', 'Rh >75%', 'Water contact conditions Low',
                'Water contact conditions Medium', 'Water contact conditions High',
                'Contamination Index Particles Medium', 'Contamination Index Particles High'
            ]

            for col in boolean_columns:
                if col in self.breather_catalog_df.columns:
                    self.breather_catalog_df[col] = (self.breather_catalog_df[col].apply(self._convert_to_boolean))
                else:
                    logger.warning(f"Boolean column '{col}' not found in catalog")

            logger.info(f"Successfully loaded {len(self.breather_catalog_df)} breathers from catalog")
            return True

        except Exception as e:
            logger.error(f"Error loading breather catalog: {str(e)}")
            return False

    def load_data_report(self, file_path) -> Tuple[bool, str]:
        """
        Load and validate the Data Report with complete data sanitization.
        """
        try:
            df = pd.read_excel(file_path, sheet_name="MPs")

            if len(df.columns) < 9:
                return False, f"Data file must have at least 9 columns. Found {len(df.columns)}."

            self.data_report_df = df.copy()

            flow_rate_col_found = None
            for col in self.data_report_df.columns:
                if str(col).lower().strip() == '(d) flow rate':
                    flow_rate_col_found = col
                    break
            
            if flow_rate_col_found and flow_rate_col_found != '(D) Flow Rate':
                self.data_report_df.rename(columns={flow_rate_col_found: '(D) Flow Rate'}, inplace=True)

            if '(D) Flow Rate' in self.data_report_df.columns:
                self.data_report_df['(D) Flow Rate'] = (
                    self.data_report_df['(D) Flow Rate']
                    .astype(str)
                    .str.extract(r'(\d+\.?\d*)', expand=False)
                )
            
            numeric_columns_to_sanitize = [
                '(D) Oil Capacity', '(D) Height', '(D) Width', '(D) Length',
                '(D) Distance from Drain Port to Oil Level', '(D) Flow Rate',
                '(D) Bearing OD', '(D) Bearing Width', '(D) Shaft Diameter',
                '(D) Dinamic clearance', '(D) RPM', '(D) Average Relative Humidity'
            ]

            logger.info("Sanitizing numeric columns from Data Report...")
            for col in numeric_columns_to_sanitize:
                if col in self.data_report_df.columns:
                    self.data_report_df[col] = pd.to_numeric(self.data_report_df[col], errors='coerce')

            if self.data_report_df.empty:
                return False, "No records found in data report."

            logger.info(f"Successfully loaded {len(self.data_report_df)} total records")
            return True, ""

        except Exception as e:
            logger.error(f"Error loading data report: {str(e)}")
            return False, f"Error loading file: {str(e)}"

    def log_maintenance_point_summary(self):
        if self.data_report_df is None or self.data_report_df.empty: 
            return
        column_i = self.data_report_df.iloc[:, 8]
        maintenance_types = column_i.value_counts()
        logger.info("Maintenance Point Types found:")
        for maint_type, count in maintenance_types.head(10).items():
            logger.info(f"  - {maint_type}: {count} records")

    def get_all_data(self) -> pd.DataFrame:
        if self.data_report_df is None: return pd.DataFrame()
        return self.data_report_df.copy()

    def get_gearbox_data(self) -> pd.DataFrame:
        if self.data_report_df is None: return pd.DataFrame()
        return self._filter_data_by_keywords(
            keywords=['Gearbox Housing (Oil)', 'Bearing (Oil)', 'Pump (Oil)', 'Electric Motor Bearing (Oil)', 'Blower (Oil)'],
            regex_keywords=[r'gearbox.*housing.*oil', r'^bearing.*oil$', r'^pump.*oil$', r'electric.*motor.*bearing.*oil', r'^blower.*oil$']
        )

    def get_circulating_data(self) -> pd.DataFrame:
        if self.data_report_df is None: return pd.DataFrame()
        return self._filter_data_by_keywords(
            keywords=['Piping (Circulating)', 'Circulating System Reservoir (Oil)', 'Pump (Oil)', 'Gearbox (Circulating)', 'Pump Bearings (Circulating)', 'Bearing (Circulating)', 'Hydraulic System Reservoir (Oil)', 'Piping (Hydraulic)', 'Turbine Bearing (Circulating)', 'Sealed Pump'],
            regex_keywords=['circulating', 'pump', 'bomba', 'hydraulic', 'reservoir']
        )

    def get_bearing_grease_data(self) -> pd.DataFrame:
        if self.data_report_df is None: return pd.DataFrame()
        return self._filter_data_by_keywords(
            keywords=['Bearing (Grease)', 'Bushing (Grease)', 'Electric Motor (Grease)'],
            regex_keywords=[]
        )

    def _filter_data_by_keywords(self, keywords: list, regex_keywords: list) -> pd.DataFrame:
        column_i = self.data_report_df.iloc[:, 8].astype(str)
        mask_exact = column_i.str.strip().isin(keywords)
        final_mask = mask_exact
        if regex_keywords:
            mask_kw = pd.Series([False] * len(self.data_report_df), index=self.data_report_df.index)
            for kw in regex_keywords: mask_kw |= column_i.str.contains(kw, case=False, na=False, regex=True)
            final_mask = mask_exact | mask_kw
        return self.data_report_df[final_mask].copy()

    def get_breather_catalog(self) -> pd.DataFrame:
        if self.breather_catalog_df is None: 
            return pd.DataFrame()
        return self.breather_catalog_df.copy()

    def save_results_with_merge(self, results_df: pd.DataFrame, output_path_or_buffer) -> Tuple[bool, str]:
        if self.data_report_df is None: return False, "No original data to merge results with."
        if results_df.empty: return False, "No results data to save."
        try:
            original_with_index = self.data_report_df.copy()
            if 'original_index' not in results_df.columns:
                results_df.reset_index(inplace=True)
                results_df.rename(columns={'index':'original_index'}, inplace=True)
            
            final_df = pd.merge(original_with_index, results_df, left_index=True, right_on='original_index', how='left')
            final_df.to_excel(output_path_or_buffer, index=False, engine='openpyxl')
            return True, ""
        except Exception as e:
            return False, f"An unexpected error occurred while saving: {str(e)}"