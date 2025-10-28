"""
Configuration Dialog for NoRia Breather Selection App - VERSIÓN SIMPLIFICADA
Handles advanced configuration parameters, incluyendo la API Key de Gemini.
ELIMINADO: Automatic temperature lookup (funcionalidad no usada que causaba bugs)
"""

import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

class ConfigurationDialog:
    """Advanced configuration dialog for breather selection parameters"""
    
    def __init__(self, parent, current_config=None):
        self.parent = parent
        self.result = None
        
        self.config = current_config.copy() if current_config else {}
        self.setup_defaults()
        
        self.dialog = ttk.Toplevel(parent)
        self.dialog.title("Edit Configuration")
        self.dialog.geometry("500x750")  # Altura reducida al eliminar sección auto-temp
        self.dialog.resizable(False, False)
        
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.center_dialog()
        self.setup_ui()
        self.dialog.wait_window()
    
    def setup_defaults(self):
        """Setup default configuration values"""
        defaults = {
            'criticality': 'A',
            'mobile_application': False,
            'max_amb_temp': 80.0,  # Siempre presente
            'min_amb_temp': 60.0,  # Siempre presente
            'high_particle_removal': False,
            'esi_manual': None,
            'safety_factor': 1.4,
            'verbose_trace': False,
            'include_calculations': False,
            'generate_ai_explanations': False,
            'gemini_api_key': '',
            'enable_manual_gpm': False,
            'manual_gpm_override': 0.0,
        }
        for key, value in defaults.items():
            self.config.setdefault(key, value)
    
    def center_dialog(self):
        self.dialog.update_idletasks()
        parent_x, parent_y = self.parent.winfo_rootx(), self.parent.winfo_rooty()
        parent_w, parent_h = self.parent.winfo_width(), self.parent.winfo_height()
        dialog_w, dialog_h = self.dialog.winfo_width(), self.dialog.winfo_height()
        x = parent_x + (parent_w - dialog_w) // 2
        y = parent_y + (parent_h - dialog_h) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def setup_ui(self):
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=BOTH, expand=True)
        
        title_label = ttk.Label(main_frame, text="Configuration Settings", font=("Arial", 14, "bold"))
        title_label.pack(anchor=W, pady=(0, 20))
        
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=BOTH, expand=True, pady=(0, 20))
        
        self.setup_general_tab(notebook)
        self.setup_temperature_tab(notebook)
        self.setup_environmental_tab(notebook)
        self.setup_advanced_tab(notebook)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=X, side=BOTTOM, pady=(10, 0))
        ttk.Button(button_frame, text="OK", command=self.ok, bootstyle="primary").pack(side=RIGHT)
        ttk.Button(button_frame, text="Cancel", command=self.cancel, bootstyle="outline-secondary").pack(side=RIGHT, padx=(10, 0))
        ttk.Button(button_frame, text="Reset to Defaults", command=self.reset_defaults, bootstyle="outline-warning").pack(side=LEFT)

    def setup_general_tab(self, notebook):
        gen_frame = ttk.Frame(notebook, padding="15")
        notebook.add(gen_frame, text="General")
        
        crit_frame = ttk.LabelFrame(gen_frame, text="Asset Criticality", padding="10")
        crit_frame.pack(fill=X, pady=(0, 15))
        self.criticality_var = tk.StringVar(value=self.config.get('criticality'))
        ttk.Combobox(crit_frame, textvariable=self.criticality_var, values=["A", "B1", "B2", "C"], state="readonly", width=15).pack(anchor=W)
        
        mobile_frame = ttk.LabelFrame(gen_frame, text="Operating Context", padding="10")
        mobile_frame.pack(fill=X, pady=(10, 0))
        self.mobile_app_var = tk.BooleanVar(value=self.config.get('mobile_application'))
        ttk.Checkbutton(mobile_frame, text="This is a Mobile Application", variable=self.mobile_app_var).pack(anchor=W)

    def setup_temperature_tab(self, notebook):
        """VERSIÓN SIMPLIFICADA - Sin automatic lookup"""
        temp_frame = ttk.Frame(notebook, padding="15")
        notebook.add(temp_frame, text="Temperature")
        
        # Instrucciones simples
        info_label = ttk.Label(
            temp_frame, 
            text="Set the ambient temperature range for your facility:",
            font=("Arial", 10)
        )
        info_label.pack(anchor=W, pady=(0, 15))
        
        # Frame de temperaturas (siempre visible y activo)
        temps_frame = ttk.LabelFrame(temp_frame, text="Ambient Temperature Range", padding="10")
        temps_frame.pack(fill=X)
        
        # Temperatura máxima
        max_temp_frame = ttk.Frame(temps_frame)
        max_temp_frame.pack(fill=X, pady=(0, 10))
        ttk.Label(max_temp_frame, text="Maximum Ambient Temperature (°F):").pack(side=LEFT)
        self.max_amb_temp_var = tk.DoubleVar(value=self.config.get('max_amb_temp', 80.0))
        ttk.Spinbox(
            max_temp_frame, 
            from_=-20, to=150, 
            textvariable=self.max_amb_temp_var, 
            width=10
        ).pack(side=RIGHT)
        
        # Temperatura mínima
        min_temp_frame = ttk.Frame(temps_frame)
        min_temp_frame.pack(fill=X)
        ttk.Label(min_temp_frame, text="Minimum Ambient Temperature (°F):").pack(side=LEFT)
        self.min_amb_temp_var = tk.DoubleVar(value=self.config.get('min_amb_temp', 60.0))
        ttk.Spinbox(
            min_temp_frame, 
            from_=-20, to=150, 
            textvariable=self.min_amb_temp_var, 
            width=10
        ).pack(side=RIGHT)
        
        # Nota informativa
        note_label = ttk.Label(
            temps_frame,
            text="💡 These values represent the typical temperature range in your plant.",
            font=("Arial", 9),
            bootstyle="secondary"
        )
        note_label.pack(anchor=W, pady=(10, 0))

    def setup_environmental_tab(self, notebook):
        env_frame = ttk.Frame(notebook, padding="15")
        notebook.add(env_frame, text="Environment")
        
        particle_frame = ttk.LabelFrame(env_frame, text="Particle Filtration", padding="10")
        particle_frame.pack(fill=X, pady=(0, 15))
        self.high_particle_var = tk.BooleanVar(value=self.config.get('high_particle_removal'))
        ttk.Checkbutton(particle_frame, text="Force high particle removal (rebuildable cartridge)", variable=self.high_particle_var).pack(anchor=W)
        
        esi_frame = ttk.LabelFrame(env_frame, text="Extended Service Override", padding="10")
        esi_frame.pack(fill=X)
        self.esi_var = tk.StringVar(value=self.config.get('esi_manual') or 'Auto')
        for option in ["Auto", "Disposable", "Rebuildable"]:
            ttk.Radiobutton(esi_frame, text=option, variable=self.esi_var, value=option).pack(anchor=W, pady=2)
    
    def setup_advanced_tab(self, notebook):
        adv_frame = ttk.Frame(notebook, padding="15")
        notebook.add(adv_frame, text="Advanced")
        
        override_frame = ttk.LabelFrame(adv_frame, text="Manual Overrides (Circulating Systems Only)", padding="10")
        override_frame.pack(fill=X, pady=(0, 15))
        
        self.enable_gpm_var = tk.BooleanVar(value=self.config.get('enable_manual_gpm'))
        gpm_check = ttk.Checkbutton(override_frame, text="Manually override GPM flow rate", variable=self.enable_gpm_var, command=self.toggle_gpm_mode)
        gpm_check.pack(anchor=W)

        gpm_input_frame = ttk.Frame(override_frame)
        gpm_input_frame.pack(fill=X, pady=(5, 0), padx=(20, 0))
        
        ttk.Label(gpm_input_frame, text="Flow Rate (GPM):").pack(side=LEFT)
        self.manual_gpm_var = tk.DoubleVar(value=self.config.get('manual_gpm_override'))
        self.gpm_spinbox = ttk.Spinbox(gpm_input_frame, from_=0, to=10000, increment=0.5, textvariable=self.manual_gpm_var, width=12, format="%.1f")
        self.gpm_spinbox.pack(side=LEFT, padx=(10, 0))

        cfm_frame = ttk.LabelFrame(adv_frame, text="CFM Calculation", padding="10")
        cfm_frame.pack(fill=X, pady=(0, 15))
        safety_frame = ttk.Frame(cfm_frame)
        safety_frame.pack(fill=X)
        ttk.Label(safety_frame, text="Safety Factor:").pack(side=LEFT)
        self.safety_factor_var = tk.DoubleVar(value=self.config.get('safety_factor'))
        ttk.Spinbox(safety_frame, from_=1.0, to=2.0, increment=0.1, textvariable=self.safety_factor_var, width=10, format="%.1f").pack(side=RIGHT)
        
        # AI & Debug
        ai_debug_frame = ttk.LabelFrame(adv_frame, text="AI & Debugging", padding="10")
        ai_debug_frame.pack(fill=X)
        
        # API Key
        api_key_frame = ttk.Frame(ai_debug_frame)
        api_key_frame.pack(fill=X, pady=(0, 10))
        ttk.Label(api_key_frame, text="Gemini API Key:").pack(side=LEFT, padx=(0, 10))
        self.gemini_api_key_var = tk.StringVar(value=self.config.get('gemini_api_key'))
        ttk.Entry(api_key_frame, textvariable=self.gemini_api_key_var, width=40, show="*").pack(side=LEFT)
        
        # Debug options
        self.verbose_trace_var = tk.BooleanVar(value=self.config.get('verbose_trace'))
        ttk.Checkbutton(ai_debug_frame, text="Include verbose rule trace in output", variable=self.verbose_trace_var).pack(anchor=W)
        self.include_calculations_var = tk.BooleanVar(value=self.config.get('include_calculations'))
        ttk.Checkbutton(ai_debug_frame, text="Include intermediate calculations in output", variable=self.include_calculations_var).pack(anchor=W, pady=(5, 0))
        
        self.toggle_gpm_mode()

    def toggle_gpm_mode(self):
        state = "normal" if self.enable_gpm_var.get() else "disabled"
        self.gpm_spinbox.config(state=state)

    def validate_config(self):
        """Validación simplificada - las temperaturas siempre están presentes"""
        if self.max_amb_temp_var.get() <= self.min_amb_temp_var.get():
            messagebox.showerror("Validation Error", "Maximum temperature must be greater than minimum.")
            return False
        return True
    
    def reset_defaults(self):
        if messagebox.askyesno("Confirm Reset", "Reset all settings to default values?"):
            self.config.clear()
            self.setup_defaults()
            
            # Actualizar UI
            self.criticality_var.set(self.config['criticality'])
            self.mobile_app_var.set(self.config['mobile_application'])
            self.max_amb_temp_var.set(self.config['max_amb_temp'])
            self.min_amb_temp_var.set(self.config['min_amb_temp'])
            self.high_particle_var.set(self.config['high_particle_removal'])
            self.esi_var.set(self.config.get('esi_manual') or 'Auto')
            self.safety_factor_var.set(self.config['safety_factor'])
            self.verbose_trace_var.set(self.config['verbose_trace'])
            self.include_calculations_var.set(self.config['include_calculations'])
            self.enable_gpm_var.set(self.config['enable_manual_gpm'])
            self.manual_gpm_var.set(self.config['manual_gpm_override'])
            self.gemini_api_key_var.set(self.config['gemini_api_key'])
            self.toggle_gpm_mode()
    
    def ok(self):
        if self.validate_config():
            self.config.update({
                'criticality': self.criticality_var.get(),
                'mobile_application': self.mobile_app_var.get(),
                'max_amb_temp': self.max_amb_temp_var.get(),  # Siempre tiene valor
                'min_amb_temp': self.min_amb_temp_var.get(),  # Siempre tiene valor
                'high_particle_removal': self.high_particle_var.get(),
                'esi_manual': self.esi_var.get() if self.esi_var.get() != 'Auto' else None,
                'safety_factor': self.safety_factor_var.get(),
                'verbose_trace': self.verbose_trace_var.get(),
                'include_calculations': self.include_calculations_var.get(),
                'manual_gpm_override': self.manual_gpm_var.get() if self.enable_gpm_var.get() else None,
                'enable_manual_gpm': self.enable_gpm_var.get(),
                'gemini_api_key': self.gemini_api_key_var.get().strip()
            })
            self.result = self.config
            self.dialog.destroy()
    
    def cancel(self):
        self.result = None
        self.dialog.destroy()