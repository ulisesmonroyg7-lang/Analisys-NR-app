# utils/gemini_client.py (Versión Definitiva para la librería actualizada)

"""
Gemini API Client for NoRia Breather Selection App
"""
import ssl
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

class GeminiChat:
    def __init__(self, api_key: str):
        self.model = None
        self.chat = None
        self.configure(api_key)

    def configure(self, api_key: str) -> bool:
        if not api_key:
            logger.error("API Key is missing.")
            return False
        try:
            genai.configure(api_key=api_key)
            # Usamos 'gemini-pro', que es el nombre estable y correcto para la librería actualizada.
            self.model = genai.GenerativeModel('gemini-pro')
            logger.info("Gemini API (gemini-pro) configured successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to configure Gemini API: {e}")
            self.model = None
            return False

    def start_chat_and_get_greeting(self, system_prompt: str) -> tuple[bool, str]:
        if not self.model:
            return False, "Model not configured."
        try:
            # La nueva API maneja el historial y los roles de sistema de forma más estructurada
            self.chat = self.model.start_chat(history=[
                {'role': 'user', 'parts': [system_prompt]},
                {'role': 'model', 'parts': ["Understood. I am ready to analyze the technical dossier. How can I assist you?"]}
            ])
            # Extraemos la respuesta inicial para mostrarla
            initial_response = "Understood. I am ready to analyze the technical dossier. How can I assist you?"
            return True, initial_response
        except Exception as e:
            logger.error(f"Failed to start chat session: {e}")
            return False, str(e)

    def send_message(self, user_message: str) -> str:
        if not self.chat:
            return "Error: The chat session has not been started."
        try:
            response = self.chat.send_message(user_message)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error communicating with AI: {e}")
            return f"Error communicating with AI: {str(e)}"

# --- FUNCIONES DE PROMPT (sin cambios) ---

def create_dossier_prompt_for_success(asset_info: dict) -> str:
    """Crea un prompt detallado para un análisis exitoso, incluyendo candidatos descartados."""
    breather = asset_info.get('selected_breather', [{}])[0]
    trace_text = " -> ".join(asset_info.get('rule_trace', []))
    notes = asset_info.get('installation_notes', 'N/A')
    
    rejected_candidates = asset_info.get('rejected_candidates', [])
    rejected_text = "\n".join([f"- {rej['model']}: Discarded due to {rej['reason']}." for rej in rejected_candidates])
    if not rejected_text:
        rejected_text = "No other close candidates were logged."

    prompt = f"""
    You are a Noria expert reliability engineer. Your task is to analyze the following technical dossier and answer questions about the breather recommendation.
    Base your answers **exclusively** on the provided data.

    --- ASSET TECHNICAL DOSSIER ---
    - Asset ID (Index): {asset_info.get('row_index', 'N/A')}
    - Recommended Breather: {breather.get('Brand', 'N/A')} {breather.get('Model', 'N/A')}
    - Recommendation Status: {asset_info.get('result_status', 'N/A')}
    - Required CFM: {asset_info.get('thermal_analysis', {}).get('cfm_required', 0.0):.2f}
    - Installation Notes: {notes}
    
    --- JUSTIFICATION & REJECTED CANDIDATES ---
    - Key Decision Trace: {trace_text}
    - Other Candidates Considered and Rejected:
{rejected_text}
    -----------------------------------

    **INITIAL ACTION:** Greet your colleague professionally, summarize the recommendation and its primary reason in one or two sentences. Then, state that you have information on why other models were discarded and ask what they would like to know in detail.
    """
    return prompt

def create_failure_analysis_prompt(failure_info: dict) -> str:
    """Crea un prompt para analizar por qué un cálculo falló y sugerir acciones."""
    trace_text = "\n".join(failure_info.get('rule_trace', ['No trace available.']))
    error_msg = failure_info.get('error_message', 'No specific error message.')

    prompt = f"""
    You are a Noria diagnostic expert. A breather selection analysis has failed. Your task is to analyze the decision trace and the error, and explain the root cause of the problem in simple terms.
    
    --- FAILURE REPORT ---
    - Asset ID (Index): {failure_info.get('row_index', 'N/A')}
    - Technical Error Message: {error_msg}
    - Decision Trace up to the point of failure:
{trace_text}
    --------------------------

    **INITIAL ACTION:**
    1.  Explain in 1-2 clear sentences the exact point in the process where the analysis stopped.
    2.  Based on the trace and error, deduce the most likely cause of the problem.
    3.  Provide a list of 2-3 **concrete, numbered actions** that the user should perform in their Excel file to fix the problem and successfully process the asset.
    """
    return prompt

def create_summary_prompt_for_batch(summary_data: dict) -> str:
    """Crea un prompt para generar un resumen ejecutivo de un lote de resultados."""
    status_summary = "\n".join([f"- {status}: {count} assets" for status, count in summary_data['status_counts'].items()])
    top_models_summary = "\n".join([f"- {model}: {count} times" for model, count in sorted(summary_data['top_models'].items(), key=lambda item: item[1], reverse=True)[:3]])

    prompt = f"""
    Act as a Senior Reliability Engineer presenting the results of a breather selection analysis to management.
    
    --- ANALYSIS DATA ---
    - Total Assets Analyzed: {summary_data['total']}
    - Results Breakdown:
{status_summary}
    - Most Recommended Breather Models:
{top_models_summary}
    --------------------------

    **TASK:** Write a concise and professional **executive summary**. Your summary must include:
    1.  An opening paragraph with the scope of the analysis (how many assets were processed).
    2.  An analysis of key findings (e.g., "the majority of solutions were optimal," "a significant number require modification").
    3.  Identification of the most common breather models, suggesting potential for standardization.
    4.  A final paragraph with recommended actions or next steps.
    
    The tone should be formal and decision-oriented. Do not include greetings or sign-offs, only the summary text.
    """
    return prompt