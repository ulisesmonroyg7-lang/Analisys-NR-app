# --- core/__init__.py ---

# Este archivo hace que la carpeta 'core' sea un paquete de Python.
# También define qué se puede importar desde este paquete.

# Importa las clases principales para que sean accesibles desde otras partes del código.
from .calculations import ThermalCalculator
from .rule_engine import RuleEngine
from .data_processor import DataProcessor

# --- LÍNEA CORREGIDA ---
# Eliminamos la importación de GreaseAnalysisProcessor que ya no existe.
from .grease_calculator import GreaseCalculator
# --- FIN DE LA CORRECCIÓN ---