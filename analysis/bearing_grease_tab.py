"""
CÓDIGO CORREGIDO: Cálculo de K_Factor para Journal Bearings
Version: Streamlit Fixed
Date: 2025

Este módulo contiene las funciones corregidas para calcular los factores K
según la metodología Noria. Copia estas funciones a tu aplicación de Streamlit.
"""

import pandas as pd
import numpy as np
import re


# ============================================================================
# FUNCIONES DE FACTORES K INDIVIDUALES
# ============================================================================

def get_k_ft(operating_temp_str: str) -> float:
    """
    K_Ft - Factor de Corrección por Temperatura
    
    Rangos:
    - Menos de 150°F: 1.0
    - 150°F a 175°F: 0.5
    - 175°F a 200°F: 0.2
    - Más de 200°F: 0.1
    
    Args:
        operating_temp_str: String con temperatura(s) en °F
                           Ej: "125°F (51.7°C) - 150°F (65.6°C)"
    
    Returns:
        Factor entre 0.1 y 1.0
    """
    if pd.isna(operating_temp_str):
        return 1.0
    
    # Extraer todas las temperaturas del string
    temp_matches = re.findall(r'(\d+\.?\d*)°?F', str(operating_temp_str))
    
    if not temp_matches:
        return 1.0
    
    # Convertir a float y calcular promedio
    temps = [float(t) for t in temp_matches]
    avg_temp = sum(temps) / len(temps)
    
    # Aplicar rangos
    if avg_temp < 150:
        return 1.0
    elif 150 <= avg_temp <= 175:
        return 0.5
    elif 175 < avg_temp <= 200:
        return 0.2
    else:
        return 0.1


def get_k_fc(contaminant_index_text: str, contaminant_likelihood_text: str) -> float:
    """
    K_Fc - Factor de Corrección por Contaminación
    
    ⚠️ CRITICAL: Este factor es el que más problemas causa
    
    Matriz de decisión:
    - Earthen/Organic + Severe/Extreme: 0.7
    - Heavy/Metal + Severe/Extreme: 0.2
    - Earthen/Organic + Medium/Low: 1.0
    - Heavy/Metal + Medium/Low: 0.4  ← CASO COMÚN
    
    Args:
        contaminant_index_text: Tipo de contaminante abrasivo
                                Ej: "Heavy (Mining, Rock Quarry Environment)"
        contaminant_likelihood_text: Nivel de exposición
                                     Ej: "High", "Medium", "Low", "Severe", "Extreme"
    
    Returns:
        Factor entre 0.2 and 1.0
    """
    # Identificar tipo de contaminante
    ci_type = None
    ci_lower = str(contaminant_index_text).lower()
    
    if 'earthen' in ci_lower or 'paper' in ci_lower:
        ci_type = 'earthen'
    elif 'organic' in ci_lower or 'food' in ci_lower:
        ci_type = 'organic'
    elif 'heavy' in ci_lower or 'mining' in ci_lower or 'rock' in ci_lower:
        ci_type = 'heavy'
    elif 'metal' in ci_lower or 'foundry' in ci_lower:
        ci_type = 'metal'
    
    # ⚠️ CRITICAL: Verificar nivel de severidad
    # IMPORTANTE: "High" NO es lo mismo que "Severe"
    cl_lower = str(contaminant_likelihood_text).lower()
    
    # Solo considera Severe/Extreme como "severe"
    # "High" NO debe considerarse "severe"
    is_severe = ('severe' in cl_lower or 'extreme' in cl_lower)
    
    # Aplicar matriz de decisión
    if is_severe:
        # Condiciones severas
        if ci_type in ['earthen', 'organic']:
            return 0.7
        elif ci_type in ['heavy', 'metal']:
            return 0.2
    else:
        # Condiciones normales/medianas (incluye "High")
        if ci_type in ['earthen', 'organic']:
            return 1.0
        elif ci_type in ['heavy', 'metal']:
            return 0.4  # ← ESTO ES LO CORRECTO PARA "HIGH"
    
    # Default si no se identifica el tipo
    return 1.0


def get_k_fh(humidity_text: str, water_contact_text: str) -> float:
    """
    K_Fh - Factor de Corrección por Humedad y Contacto con Agua
    
    Prioridad:
    1. Condiciones severas de agua: 0.1
    2. Condiciones moderadas de agua: 0.4
    3. Humedad >= 75%: 0.7
    4. Normal: 1.0
    
    Args:
        humidity_text: Humedad relativa promedio
                      Ej: "75% (75 Percent)"
        water_contact_text: Condiciones de contacto con agua
                           Ej: "Typical Humidity, but Occasional Rain"
    
    Returns:
        Factor entre 0.1 and 1.0
    """
    wcc_lower = str(water_contact_text).lower()
    
    # Verificar condiciones severas de agua
    severe_water_terms = ["washdowns", "severe water", "submerged"]
    if any(term in wcc_lower for term in severe_water_terms):
        return 0.1
    
    # Verificar condiciones moderadas de agua
    moderate_water_terms = ["steam/spray", "steam", "spray", "mild water", 
                           "moderate water", "nearby water"]
    if any(term in wcc_lower for term in moderate_water_terms):
        return 0.4
    
    # Si no hay condiciones especiales de agua, verificar humedad
    try:
        # Extraer valor numérico de humedad (primer número encontrado)
        humidity_matches = re.findall(r'(\d+\.?\d*)', str(humidity_text))
        
        if humidity_matches:
            humidity_value = float(humidity_matches[0])
            
            # ⚠️ CRITICAL: Si humedad >= 75%, usar 0.7
            if humidity_value >= 75:
                return 0.7
    except (ValueError, AttributeError):
        pass
    
    # Humedad normal
    return 1.0


def get_k_fv(vibration_text: str) -> float:
    """
    K_Fv - Factor de Corrección por Vibración
    
    Rangos:
    - Mayor a 0.4 ips: 0.3
    - 0.2 a 0.4 ips: 0.6
    - Menor a 0.2 ips: 1.0
    
    Args:
        vibration_text: Nivel de vibración
                       Ej: "<0.2 ips", "0.2 to 0.4 ips", "> 0.4 ips"
    
    Returns:
        Factor entre 0.3 and 1.0
    """
    vib_str = str(vibration_text).strip().lower()
    
    if "> 0.4" in vib_str or ">0.4" in vib_str:
        return 0.3
    elif "0.2 to 0.4" in vib_str or "0.2-0.4" in vib_str:
        return 0.6
    else:
        return 1.0


def get_k_fp(position_text: str) -> float:
    """
    K_Fp - Factor de Corrección por Posición
    
    Posiciones:
    - Vertical: 0.3
    - 45 grados: 0.5
    - Horizontal: 1.0
    
    Args:
        position_text: Posición del bearing
                      Ej: "Horizontal", "Vertical", "45°"
    
    Returns:
        Factor entre 0.3 and 1.0
    """
    pos_lower = str(position_text).lower()
    
    if 'vertical' in pos_lower:
        return 0.3
    elif '45' in pos_lower:
        return 0.5
    else:
        return 1.0


def get_k_fd(bearing_type_text: str) -> float:
    """
    K_Fd - Factor de Corrección por Diseño del Bearing
    
    Tipos:
    - Ball: 10.0
    - Cylindrical/Needle: 5.0
    - Tapered/Spherical: 1.0
    - Journal: 1.0
    
    Args:
        bearing_type_text: Tipo de bearing
                          Ej: "Journal Bearing", "Ball Bearing"
    
    Returns:
        Factor entre 1.0 and 10.0
    """
    design_lower = str(bearing_type_text).lower()
    
    if 'ball' in design_lower:
        return 10.0
    elif 'cylindrical' in design_lower or 'needle' in design_lower:
        return 5.0
    elif 'tapered' in design_lower or 'spherical' in design_lower:
        return 1.0
    elif 'journal' in design_lower or 'bushing' in design_lower:
        return 1.0
    else:
        return 1.0  # Default para desconocidos


# ============================================================================
# FUNCIÓN PRINCIPAL: CALCULAR K_FACTOR TOTAL
# ============================================================================

def calculate_k_factor_complete(row_data: dict) -> dict:
    """
    Calcula TODOS los factores K para un journal bearing y el factor total.
    
    Esta función es la que debes usar en tu aplicación de Streamlit.
    
    Args:
        row_data: Diccionario con los datos del bearing, debe contener:
                 - '(D) Operating Temperature'
                 - '(D) Contaminant Abrasive Index'
                 - '(D) Contaminant Likelihood'
                 - '(D) Average Relative Humidity'
                 - '(D) Water Contact Conditions'
                 - '(D) Vibration'
                 - '(D) Position'
                 - '(D) Bearing Type'
    
    Returns:
        Diccionario con todos los factores individuales y el total:
        {
            'K_Ft': float,
            'K_Fc': float,
            'K_Fh': float,
            'K_Fv': float,
            'K_Fp': float,
            'K_Fd': float,
            'K_Total': float
        }
    """
    # Calcular cada factor individual
    k_ft = get_k_ft(row_data.get('(D) Operating Temperature'))
    k_fc = get_k_fc(
        row_data.get('(D) Contaminant Abrasive Index'),
        row_data.get('(D) Contaminant Likelihood')
    )
    k_fh = get_k_fh(
        row_data.get('(D) Average Relative Humidity'),
        row_data.get('(D) Water Contact Conditions')
    )
    k_fv = get_k_fv(row_data.get('(D) Vibration'))
    k_fp = get_k_fp(row_data.get('(D) Position'))
    k_fd = get_k_fd(row_data.get('(D) Bearing Type'))
    
    # ⚠️ CRITICAL: MULTIPLICAR todos los factores (NO sumar, NO dividir)
    k_total = k_ft * k_fc * k_fh * k_fv * k_fp * k_fd
    
    return {
        'K_Ft': k_ft,
        'K_Fc': k_fc,
        'K_Fh': k_fh,
        'K_Fv': k_fv,
        'K_Fp': k_fp,
        'K_Fd': k_fd,
        'K_Total': k_total
    }


# ============================================================================
# CÁLCULO DE FRECUENCIA PARA JOURNAL BEARINGS
# ============================================================================

def calculate_journal_bearing_frequency(
    shaft_diameter_mm: float,
    bearing_width_mm: float,
    runtime_percentage_text: str,
    k_total: float
) -> dict:
    """
    Calcula la frecuencia de re-engrase para un journal bearing.
    
    Fórmula:
    t_grease = (dc_clearance × area × Oh × 0.5) / K
    
    Donde:
    - dc_clearance = 2 × film_thickness (0.001 inches)
    - area = π × d_inner × w_width (in²)
    - Oh = 168 × runtime_percentage (horas/semana)
    - K = factor total de corrección
    
    Args:
        shaft_diameter_mm: Diámetro del eje en milímetros
        bearing_width_mm: Ancho del bearing en milímetros
        runtime_percentage_text: Porcentaje de runtime
                                Ej: "30 to 60%", "60 to 90%", ">90%"
        k_total: Factor K total (producto de todos los K individuales)
    
    Returns:
        Diccionario con:
        - frequency_hours: Frecuencia en horas
        - frequency_unit: "Hours"
        - oh_hours_per_week: Horas de operación por semana
    """
    # Constantes
    FILM_THICKNESS_INCHES = 0.001
    MM_TO_INCHES = 1 / 25.4
    MAX_FREQUENCY_HOURS = 8760  # 1 año
    
    # Conversión a pulgadas
    d_inner_inches = shaft_diameter_mm * MM_TO_INCHES
    w_width_inches = bearing_width_mm * MM_TO_INCHES
    
    # Dynamic Clearance
    dc_clearance = 2 * FILM_THICKNESS_INCHES
    
    # Área del bearing
    area_sq_inches = np.pi * d_inner_inches * w_width_inches
    
    # Runtime percentage
    runtime_map = {
        "<10%": 0.1,
        "10 to 30%": 0.3,
        "30 to 60%": 0.6,
        "60 to 90%": 0.9,
        ">90%": 1.0
    }
    
    runtime_percentage = runtime_map.get(str(runtime_percentage_text).strip(), 0.9)
    
    # Horas de operación por semana
    oh_hours_per_week = 168 * runtime_percentage
    
    # ⚠️ CRITICAL: Fórmula correcta
    frequency_hours = (dc_clearance * area_sq_inches * oh_hours_per_week * 0.5) / k_total
    
    # Aplicar límite máximo de 1 año
    if frequency_hours > MAX_FREQUENCY_HOURS:
        frequency_hours = MAX_FREQUENCY_HOURS
    
    return {
        'frequency_hours': frequency_hours,
        'frequency_unit': 'Hours',
        'oh_hours_per_week': oh_hours_per_week
    }


# ============================================================================
# FUNCIÓN INTEGRADA PARA STREAMLIT
# ============================================================================

def process_journal_bearing_complete(row_data: dict) -> dict:
    """
    Función completa que procesa un journal bearing desde datos crudos hasta resultados finales.
    
    Esta es la función que debes llamar desde tu aplicación de Streamlit.
    
    Args:
        row_data: Diccionario con todos los datos del bearing
    
    Returns:
        Diccionario completo con:
        - Todos los factores K individuales
        - K_Total
        - Frecuencia en horas
        - Horas de operación
    """
    # Calcular factores K
    k_factors = calculate_k_factor_complete(row_data)
    
    # Calcular frecuencia
    frequency_result = calculate_journal_bearing_frequency(
        shaft_diameter_mm=float(row_data.get('(D) Shaft Diameter', 0)),
        bearing_width_mm=float(row_data.get('(D) Bearing Width', 0)),
        runtime_percentage_text=row_data.get('(D) Runtime Percentage', '>90%'),
        k_total=k_factors['K_Total']
    )
    
    # Combinar resultados
    return {
        **k_factors,
        **frequency_result
    }


# ============================================================================
# EJEMPLO DE USO EN STREAMLIT
# ============================================================================

if __name__ == "__main__":
    # TEST CASE: Bomba de barro 01 - Cigüeñal
    test_data = {
        '(D) Operating Temperature': '125°F (51.7°C) - 150°F (65.6°C)',
        '(D) Contaminant Abrasive Index': 'Heavy (Mining, Rock Quarry Environment)',
        '(D) Contaminant Likelihood': 'High',  # ← NO es "Severe"
        '(D) Average Relative Humidity': '75% (75 Percent)',
        '(D) Water Contact Conditions': 'Typical Humidity, but Occasional Rain',
        '(D) Vibration': '<0.2 ips',
        '(D) Position': 'Horizontal',
        '(D) Bearing Type': 'Journal Bearing',
        '(D) Shaft Diameter': 200,  # mm
        '(D) Bearing Width': 250,  # mm
        '(D) Runtime Percentage': '30 to 60%'
    }
    
    print("="*80)
    print("TEST: Cálculo de K_Factor y Frecuencia")
    print("="*80)
    
    # Procesar bearing
    result = process_journal_bearing_complete(test_data)
    
    print("\nFactores K Individuales:")
    print(f"  K_Ft (Temperatura):   {result['K_Ft']:.2f}")
    print(f"  K_Fc (Contaminación): {result['K_Fc']:.2f}")
    print(f"  K_Fh (Humedad):       {result['K_Fh']:.2f}")
    print(f"  K_Fv (Vibración):     {result['K_Fv']:.2f}")
    print(f"  K_Fp (Posición):      {result['K_Fp']:.2f}")
    print(f"  K_Fd (Diseño):        {result['K_Fd']:.2f}")
    
    print(f"\nK_Factor Total: {result['K_Total']:.2f}")
    print(f"Frecuencia: {result['frequency_hours']:.2f} {result['frequency_unit']}")
    print(f"Horas operación/semana: {result['oh_hours_per_week']:.2f}")
    
    # Verificar valores esperados
    print("\n" + "="*80)
    print("VERIFICACIÓN:")
    print("="*80)
    
    expected = {
        'K_Total': 0.28,
        'frequency_hours': 131.48
    }
    
    tolerance = 0.5  # Tolerancia de 0.5 horas
    
    k_ok = abs(result['K_Total'] - expected['K_Total']) < 0.01
    freq_ok = abs(result['frequency_hours'] - expected['frequency_hours']) < tolerance
    
    print(f"K_Factor Total: {result['K_Total']:.2f} (Esperado: 0.28) {'✅' if k_ok else '❌'}")
    print(f"Frecuencia: {result['frequency_hours']:.2f}h (Esperado: 131.48h) {'✅' if freq_ok else '❌'}")
    
    if k_ok and freq_ok:
        print("\n✅ TODOS LOS TESTS PASARON")
    else:
        print("\n❌ HAY DIFERENCIAS - REVISAR CÓDIGO")
