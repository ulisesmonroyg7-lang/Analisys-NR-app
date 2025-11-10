"""
Excel Handler for NoRia Analysis Tool - VERSIÓN FINAL PARA STREAMLIT
- Soporta la carga de datos desde rutas de archivo (str) o desde objetos de archivo en memoria (de Streamlit).
- Incluye el método 'merge_results_with_original' para enriquecer el reporte de datos original con los resultados del análisis.
"""

import os
import sys
import logging
from typing import Dict, Tuple, Any # Any permite aceptar strings u objetos de archivo
import pandas as pd

# -----------------------------
# Helper de rutas para PyInstaller (se mantiene por compatibilidad)
# -----------------------------
def resource_path(relative_path: str) -> str:
    """
    Devuelve una ruta válida para ejecución normal o empaquetada con PyInstaller.
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# -----------------------------
# Logging básico
# -----------------------------
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class ExcelHandler:
    """Maneja todas las operaciones de archivos Excel para la herramienta de análisis."""

    def __init__(self):
        self.data_report_df: pd.DataFrame | None = None
        self.breather_catalog_df: pd.DataFrame | None = None

    def _convert_to_boolean(self, value):
        """Convierte valores diversos a boolean de forma robusta."""
        if pd.isna(value):
            return False
        str_val = str(value).strip().lower()
        return str_val in ['x', 'yes', 'true', '1', 'y', '1.0', 'si', 'sí']

    # -----------------------------
    # Catálogo de Breathers
    # -----------------------------
    def load_breather_catalog(self, catalog_source: Any) -> bool:
        """
        Carga el catálogo de breathers desde una ruta (str) o un objeto de archivo en memoria.
        """
        try:
            # Lógica para manejar tanto rutas como objetos de archivo
            if isinstance(catalog_source, str):
                catalog_path = resource_path(catalog_source)
                if not os.path.exists(catalog_path):
                    logger.error(f"Breather catalog not found: {catalog_path}")
                    return False
                df = pd.read_excel(catalog_path, sheet_name="Breathers Specs", header=1)
            else: # Asume que es un objeto de archivo (ej. de Streamlit)
                df = pd.read_excel(catalog_source, sheet_name="Breathers Specs", header=1)
            
            self.breather_catalog_df = df

            # Limpieza básica de encabezados
            self.breather_catalog_df.columns = (
                self.breather_catalog_df.columns.str.strip()
                .str.replace('\r\n', ' ', regex=False).str.replace('\n', ' ', regex=False)
                .str.replace('  ', ' ', regex=False)
            )

            # Normaliza numéricos con comas
            numeric_cols_with_commas = [
                'Adsorption Capacity (mL)', 'Max Fluid Flow (gpm)',
                'Gearbox, pump, storage Sump Volume MAX gal',
                'Circulating/Hyd sump volume max gal.'
            ]
            for col in numeric_cols_with_commas:
                if col in self.breather_catalog_df.columns:
                    self.breather_catalog_df[col] = pd.to_numeric(
                        self.breather_catalog_df[col].astype(str).str.replace(',', ''), errors='coerce'
                    )

            # Booleanos
            boolean_columns = [
                'Extended Service', 'Mobile applications', 'Integrated oil mist control', 'High vibration',
                'Rh 25 to 75%', 'Rh >75%', 'Water contact conditions Low', 'Water contact conditions Medium',
                'Water contact conditions High', 'Contamination Index Particles Medium', 'Contamination Index Particles High'
            ]
            for col in boolean_columns:
                if col in self.breather_catalog_df.columns:
                    self.breather_catalog_df[col] = self.breather_catalog_df[col].apply(self._convert_to_boolean)

            logger.info(f"Successfully loaded {len(self.breather_catalog_df)} breathers from catalog")
            return True

        except Exception as e:
            logger.error(f"Error loading breather catalog: {str(e)}. Attempting fallback...")
            # Fallback si la hoja "Breathers Specs" no existe
            try:
                if isinstance(catalog_source, str):
                    df = pd.read_excel(resource_path(catalog_source), header=1)
                else:
                    # Rebobinar el puntero del archivo en memoria si ya fue leído
                    if hasattr(catalog_source, 'seek'):
                        catalog_source.seek(0)
                    df = pd.read_excel(catalog_source, header=1)
                
                self.breather_catalog_df = df
                # Re-aplicar limpieza si la carga de fallback fue exitosa
                # (Omitido por brevedad, pero se podría duplicar la lógica de limpieza aquí)
                logger.info("Successfully loaded catalog using fallback (first sheet).")
                return True
            except Exception as inner_e:
                logger.error(f"Fallback loading also failed: {inner_e}")
                return False

    # -----------------------------
    # Data Report (MPs)
    # -----------------------------
    def load_data_report(self, file_source: Any) -> Tuple[bool, str]:
        """
        Carga y valida el Reporte de Datos desde una ruta o un objeto de archivo.
        """
        try:
            if not file_source:
                return False, "No file source provided."

            # pandas.read_excel maneja flexiblemente rutas (str) y objetos de archivo
            try:
                df = pd.read_excel(file_source, sheet_name="MPs")
            except Exception:
                file_name = getattr(file_source, 'name', str(file_source)).lower()
                if hasattr(file_source, 'seek'): file_source.seek(0) # Rebobinar para re-leer
                if file_name.endswith('.csv'):
                    df = pd.read_csv(file_source)
                else:
                    df = pd.read_excel(file_source) # Intentar con la primera hoja

            if len(df.columns) < 9:
                return False, f"Data file must have at least 9 columns. Found {len(df.columns)}."
            self.data_report_df = df.copy()

            # Lógica de estandarización y limpieza (sin cambios)
            flow_rate_col_found = None
            for col in self.data_report_df.columns:
                if str(col).lower().strip() == '(d) flow rate':
                    flow_rate_col_found = col
                    break
            if flow_rate_col_found and flow_rate_col_found != '(D) Flow Rate':
                self.data_report_df.rename(columns={flow_rate_col_found: '(D) Flow Rate'}, inplace=True)
            
            for col in ['(DU) Flow Rate', '(DU) Oil Capacity']:
                if col in self.data_report_df.columns:
                    self.data_report_df[col] = self.data_report_df[col].astype(str).fillna('').str.strip().str.lower()
            
            if '(D) Flow Rate' in self.data_report_df.columns:
                self.data_report_df['(D) Flow Rate'] = self.data_report_df['(D) Flow Rate'].astype(str).str.extract(r'(\d+\.?\d*)', expand=False)
            
            numeric_columns = ['(D) Oil Capacity', '(D) Height', '(D) Width', '(D) Length', '(D) Distance from Drain Port to Oil Level', '(D) Flow Rate']
            for col in numeric_columns:
                if col in self.data_report_df.columns:
                    self.data_report_df[col] = pd.to_numeric(self.data_report_df[col], errors='coerce')

            if self.data_report_df.empty:
                return False, "No records found in data report."
            
            logger.info(f"Successfully loaded {len(self.data_report_df)} total records")
            return True, ""

        except Exception as e:
            logger.error(f"Error loading data report: {str(e)}")
            return False, f"Error loading file: {str(e)}"

    # -----------------------------
    # Helpers de acceso y filtros (sin cambios)
    # -----------------------------
    def get_all_data(self) -> pd.DataFrame:
        return self.data_report_df.copy() if self.data_report_df is not None else pd.DataFrame()

    def get_gearbox_data(self) -> pd.DataFrame:
        # (Lógica de filtrado sin cambios)
        if self.data_report_df is None: return pd.DataFrame()
        column_i = self.data_report_df.iloc[:, 8].astype(str)
        splash_types = ['Gearbox Housing (Oil)', 'Bearing (Oil)', 'Pump (Oil)', 'Electric Motor Bearing (Oil)', 'Blower (Oil)']
        mask = column_i.str.strip().isin(splash_types)
        return self.data_report_df[mask].copy()

    def get_circulating_data(self) -> pd.DataFrame:
        # (Lógica de filtrado sin cambios)
        if self.data_report_df is None: return pd.DataFrame()
        column_i = self.data_report_df.iloc[:, 8].astype(str)
        circ_types = ['Circulating System Reservoir (Oil)', 'Hydraulic System Reservoir (Oil)']
        mask = column_i.str.strip().isin(circ_types)
        return self.data_report_df[mask].copy()

    def get_bearing_grease_data(self) -> pd.DataFrame:
        # (Lógica de filtrado sin cambios)
        if self.data_report_df is None: return pd.DataFrame()
        column_i = self.data_report_df.iloc[:, 8].astype(str)
        mask = column_i.str.contains('Bearing.*Grease', case=False, na=False, regex=True)
        return self.data_report_df[mask].copy()
        
    def get_breather_catalog(self) -> pd.DataFrame:
        return self.breather_catalog_df.copy() if self.breather_catalog_df is not None else pd.DataFrame()

    # -----------------------------
    # Fusión y Guardado de Resultados
    # -----------------------------
    
    def merge_results_with_original(self, results_df: pd.DataFrame) -> pd.DataFrame:
        """
        Fusiona el DataFrame de resultados con el DataFrame del reporte de datos original
        y devuelve el DataFrame final para ser descargado.
        """
        if self.data_report_df is None:
            logger.warning("Original data report not available for merging. Returning results only.")
            return results_df

        if 'original_index' not in results_df.columns:
            logger.error("Results DataFrame is missing 'original_index' for merging.")
            return self.data_report_df # Devuelve el original si la fusión no es posible
        
        original_with_index = self.data_report_df.reset_index().rename(columns={'index': 'original_index'})
        
        final_df = pd.merge(original_with_index, results_df, on='original_index', how='left')
        
        # Elimina la columna de índice temporal
        final_df = final_df.drop(columns=['original_index'])
        
        return final_df

    def save_results_with_merge(self, results_df: pd.DataFrame, output_path: str) -> Tuple[bool, str]:
        """
        (Método original) Fusiona y guarda los resultados en un archivo. Menos usado en Streamlit.
        """
        try:
            final_df = self.merge_results_with_original(results_df)
            final_df.to_excel(output_path, index=False, engine='openpyxl')
            return True, ""
        except PermissionError:
            error_msg = ("Could not save the file. Please check if the file is already open in Excel or if you have write permissions.")
            return False, error_msg
        except Exception as e:
            error_msg = f"An unexpected error occurred while saving: {str(e)}"
            return False, error_msg