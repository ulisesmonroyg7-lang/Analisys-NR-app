"""
Gemini API Client for NoRia Breather Selection App - VERSIÓN POTENCIADA
- Contiene múltiples funciones para crear prompts específicos para cada tarea de IA.
"""
# --- SOLUCIÓN TEMPORAL PARA REDES CORPORATIVAS ---
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
# --- FIN DE LA SOLUCIÓN TEMPORAL ---

import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

class GeminiChat:
    # ... (sin cambios en la clase GeminiChat) ...
    def __init__(self, api_key: str):
        self.model = None; self.chat = None; self.configure(api_key)
    def configure(self, api_key: str) -> bool:
        if not api_key: logger.error("API Key is missing."); return False
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash')
            logger.info("Gemini API (gemini-1.5-pro-latest) configured successfully."); return True
        except Exception as e:
            logger.error(f"Failed to configure Gemini API: {e}"); self.model = None; return False
    def start_chat_and_get_greeting(self, system_prompt: str) -> tuple[bool, str]:
        if not self.model: return False, "Modelo no configurado."
        try:
            self.chat = self.model.start_chat(history=[])
            response = self.chat.send_message(system_prompt)
            return True, response.text.strip()
        except Exception as e:
            logger.error(f"Failed to start chat session and get greeting: {e}"); return False, str(e)
    def send_message(self, user_message: str) -> str:
        if not self.chat: return "Error: The chat session has not been started."
        try:
            response = self.chat.send_message(user_message)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error communicating with AI: {e}"); return f"Error communicating with AI: {str(e)}"

# --- NUEVAS FUNCIONES DE PROMPT ---

def create_dossier_prompt_for_success(asset_info: dict) -> str:
    """Crea un prompt detallado para un análisis exitoso, incluyendo candidatos descartados."""
    breather = asset_info.get('selected_breather', [{}])[0]
    trace_text = " -> ".join(asset_info.get('rule_trace', []))
    notes = asset_info.get('installation_notes', 'N/A')
    
    rejected_candidates = asset_info.get('rejected_candidates', [])
    rejected_text = "\n".join([f"- {rej['model']}: Descartado por {rej['reason']}." for rej in rejected_candidates])
    if not rejected_text:
        rejected_text = "No se registraron otros candidatos cercanos."

    prompt = f"""
    Eres un ingeniero de confiabilidad experto de Noria. Tu tarea es analizar el siguiente dossier técnico y responder preguntas sobre la recomendación de un respirador.
    Basa tus respuestas **exclusivamente** en los datos proporcionados.

    --- DOSSIER TÉCNICO DEL ACTIVO ---
    - Activo ID (Índice): {asset_info.get('row_index', 'N/A')}
    - Respirador Recomendado: {breather.get('Brand', 'N/A')} {breather.get('Model', 'N/A')}
    - Estado de la Recomendación: {asset_info.get('result_status', 'N/A')}
    - CFM Requerido: {asset_info.get('thermal_analysis', {}).get('cfm_required', 0.0):.2f}
    - Notas de Instalación: {notes}
    
    --- JUSTIFICACIÓN Y DESCARTES ---
    - Traza de Decisión Clave: {trace_text}
    - Otros Candidatos Considerados y Descartados:
{rejected_text}
    -----------------------------------

    **ACCIÓN INICIAL:** Saluda profesionalmente, resume en una o dos frases la recomendación y la razón principal. Luego, indica que tienes información sobre por qué otros modelos fueron descartados y pregunta qué le gustaría saber en detalle a tu colega.
    """
    return prompt

def create_failure_analysis_prompt(failure_info: dict) -> str:
    """Crea un prompt para analizar por qué un cálculo falló y sugerir acciones."""
    trace_text = "\n".join(failure_info.get('rule_trace', ['No trace available.']))
    error_msg = failure_info.get('error_message', 'No specific error message.')

    prompt = f"""
    Eres un experto en diagnóstico de Noria. Un análisis de selección de respirador ha fallado. Tu tarea es analizar la traza de decisión y el error, y explicar en lenguaje sencillo la causa raíz del problema.
    
    --- INFORME DE FALLO ---
    - Activo ID (Índice): {failure_info.get('row_index', 'N/A')}
    - Mensaje de Error Técnico: {error_msg}
    - Traza de Decisión hasta el fallo:
{trace_text}
    --------------------------

    **ACCIÓN INICIAL:**
    1.  Explica en 1 o 2 frases claras cuál fue el punto exacto del proceso donde se detuvo el análisis.
    2.  Basado en la traza y el error, deduce la causa más probable del problema.
    3.  Proporciona una lista de 2 a 3 **acciones concretas y numeradas** que el usuario debe realizar en su archivo de Excel para corregir el problema y poder procesar el activo exitosamente.
    """
    return prompt

def create_summary_prompt_for_batch(summary_data: dict) -> str:
    """Crea un prompt para generar un resumen ejecutivo de un lote de resultados."""
    status_summary = "\n".join([f"- {status}: {count} activos" for status, count in summary_data['status_counts'].items()])
    top_models_summary = "\n".join([f"- {model}: {count} veces" for model, count in sorted(summary_data['top_models'].items(), key=lambda item: item[1], reverse=True)[:3]])

    prompt = f"""
    Actúa como un Ingeniero de Confiabilidad Senior que debe presentar los resultados de un análisis de selección de respiradores a gerencia.
    
    --- DATOS DEL ANÁLISIS ---
    - Total de Activos Analizados: {summary_data['total']}
    - Desglose de Resultados:
{status_summary}
    - Modelos de Respirador más recomendados:
{top_models_summary}
    --------------------------

    **TAREA:** Escribe un **resumen ejecutivo** conciso y profesional. Tu resumen debe incluir:
    1.  Un párrafo de apertura con el alcance del análisis (cuántos activos se procesaron).
    2.  Un análisis de los hallazgos clave (ej. "la mayoría de las soluciones fueron óptimas", "un número significativo requiere modificación").
    3.  Identificación de los modelos de respirador más comunes, sugiriendo una posible estandarización.
    4.  Un párrafo final con las acciones recomendadas o los siguientes pasos.
    
    El tono debe ser formal y orientado a la toma de decisiones. No incluyas saludos ni despedidas, solo el texto del resumen.
    """
    return prompt