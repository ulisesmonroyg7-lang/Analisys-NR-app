# --- ARCHIVO CORREGIDO Y FINAL ---
"""
Interactive AI Chat Dialog for NoRia Breather Selection App
Allows the user to discuss a recommendation with the Gemini AI.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import threading

class ChatDialog:
    """A dialog window for a conversational AI chat."""

    # --- MODIFICACIÓN: Ahora recibe la instancia de chat de Gemini ---
    def __init__(self, parent, title="Análisis con IA", gemini_chat_instance=None, initial_message=""):
        self.parent = parent
        self.gemini_chat_instance = gemini_chat_instance # Guardamos la "llave" de la IA

        self.dialog = ttk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("700x550")
        self.dialog.resizable(True, True)

        self.dialog.transient(parent)
        self.dialog.grab_set()

        self.setup_ui()

        if initial_message:
            self.set_initial_message(initial_message)

        self.dialog.wait_window()

    def setup_ui(self):
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=BOTH, expand=True)
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        self.history_text = scrolledtext.Text(main_frame, wrap=WORD, state="disabled", font=("Arial", 10))
        self.history_text.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.history_text.tag_config("user", foreground="#3498db", font=("Arial", 10, "bold"))
        self.history_text.tag_config("assistant", foreground="white")
        self.history_text.tag_config("error", foreground="#e74c3c")

        self.input_var = tk.StringVar()
        input_entry = ttk.Entry(main_frame, textvariable=self.input_var, font=("Arial", 10))
        input_entry.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        input_entry.bind("<Return>", self.send_message_in_thread)

        self.send_button = ttk.Button(main_frame, text="Enviar", command=self.send_message_in_thread, bootstyle="primary")
        self.send_button.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(10, 0))

    # --- MODIFICACIÓN: La lógica de comunicación con la IA ahora vive aquí ---
    def send_message_in_thread(self, event=None):
        """Wrapper to run send_message in a separate thread to avoid freezing the UI."""
        threading.Thread(target=self.send_message).start()

    def send_message(self):
        user_message = self.input_var.get().strip()
        if not user_message or not self.gemini_chat_instance:
            return

        # Deshabilitar UI
        self.dialog.after(0, self.input_var.set, "")
        self.dialog.after(0, self.send_button.config, {"state": "disabled"})
        self.add_message("Tú: " + user_message, "user")
        
        # Enviar a la IA
        response = self.gemini_chat_instance.send_message(user_message)
        
        # Recibir y mostrar respuesta
        self.receive_message(response)
        
        # Rehabilitar UI
        self.dialog.after(0, self.send_button.config, {"state": "normal"})

    def receive_message(self, assistant_message: str, tag: str = "assistant"):
        self.add_message("IA: " + assistant_message, tag)

    def add_message(self, message: str, tag: str):
        # Usamos 'after' para asegurar que las actualizaciones de UI ocurran en el hilo principal
        self.dialog.after(0, self._add_message_to_widget, message, tag)

    def _add_message_to_widget(self, message, tag):
        self.history_text.config(state="normal")
        self.history_text.insert(END, message + "\n\n", tag)
        self.history_text.config(state="disabled")
        self.history_text.see(END)

    def set_initial_message(self, message: str):
        self.receive_message(message)