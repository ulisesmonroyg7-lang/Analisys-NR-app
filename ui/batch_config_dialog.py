# --- ARCHIVO CORREGIDO (VERSIÓN 2) ---
"""
Batch Configuration Dialog for NoRia Breather Selection App
Handles applying configuration changes to multiple assets at once.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

class BatchConfigurationDialog:
    """A dialog for applying specific configuration changes to multiple assets."""

    def __init__(self, parent, item_count):
        self.parent = parent
        self.item_count = item_count
        self.result = None

        self.dialog = ttk.Toplevel(parent)
        self.dialog.title(f"Batch Edit for {item_count} Assets")
        self.dialog.geometry("550x600")
        self.dialog.resizable(False, False)
        
        self.apply_vars = {
            'criticality': tk.BooleanVar(),
            'mobile_application': tk.BooleanVar(),
            'temperature': tk.BooleanVar(),
            'high_particle_removal': tk.BooleanVar(),
            'esi_manual': tk.BooleanVar(),
            'safety_factor': tk.BooleanVar(),
        }
        
        self.config_vars = {
            'criticality': tk.StringVar(value="A"),
            'mobile_application': tk.BooleanVar(),
            'auto_temp_lookup': tk.BooleanVar(value=True),
            'location': tk.StringVar(),
            'min_amb_temp': tk.DoubleVar(value=60.0),
            'max_amb_temp': tk.DoubleVar(value=80.0),
            'high_particle_removal': tk.BooleanVar(),
            'esi_manual': tk.StringVar(value="Auto"),
            'safety_factor': tk.DoubleVar(value=1.4),
        }

        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.setup_ui()
        self.dialog.wait_window()

    def setup_ui(self):
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=BOTH, expand=True)

        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=X, pady=(0, 20))
        ttk.Label(title_frame, text=f"Apply changes to {self.item_count} assets", font=("Arial", 14, "bold")).pack(anchor=W)
        ttk.Label(title_frame, text="Check a box to enable and apply a new setting to the entire selection.", wraplength=500).pack(anchor=W, pady=(5,0))
        
        controls_frame = ttk.Frame(main_frame)
        controls_frame.pack(fill=BOTH, expand=True)

        self.create_criticality_section(controls_frame)
        self.create_mobile_app_section(controls_frame)
        self.create_temperature_section(controls_frame)
        self.create_particle_section(controls_frame)
        self.create_esi_section(controls_frame)
        self.create_safety_factor_section(controls_frame)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=X, side=BOTTOM, pady=(20, 0))
        ttk.Button(button_frame, text="Apply Changes", command=self.apply, bootstyle="primary").pack(side=RIGHT)
        ttk.Button(button_frame, text="Cancel", command=self.cancel, bootstyle="outline-secondary").pack(side=RIGHT, padx=(10, 0))

    def create_section_frame(self, parent, key, label_text, controlled_widgets):
        frame = ttk.Frame(parent)
        frame.pack(fill=X, pady=4)
        
        apply_var = self.apply_vars[key]
        
        check = ttk.Checkbutton(frame, text=label_text, variable=apply_var, 
                                command=lambda v=apply_var, w=controlled_widgets: self.toggle_widget_state(v, w))
        check.pack(side=LEFT)
        self.toggle_widget_state(apply_var, controlled_widgets)

    def toggle_widget_state(self, control_var, widgets):
        """Enables or disables a list of widgets based on a control BooleanVar."""
        state = "normal" if control_var.get() else "disabled"
        for widget in widgets:
            # --- CORRECCIÓN CLAVE ---
            # Si el widget es un LabelFrame, aplicamos el estado a sus hijos, no a él mismo.
            if isinstance(widget, ttk.LabelFrame):
                for child in widget.winfo_children():
                    try:
                        child.configure(state=state)
                    except tk.TclError:
                        # Algunos sub-widgets como frames internos tampoco tienen 'state'
                        pass
            else:
                try:
                    widget.configure(state=state)
                except tk.TclError:
                    # Ignorar widgets que no soportan el estado 'state'
                    pass
        
        if widgets and isinstance(widgets[0], ttk.LabelFrame) and control_var.get():
             self.toggle_temp_sub_controls()

    def create_criticality_section(self, parent):
        widget_frame = ttk.Frame(parent)
        self.crit_combo = ttk.Combobox(widget_frame, textvariable=self.config_vars['criticality'], values=["A", "B1", "B2", "C"], width=15)
        self.crit_combo.pack(side=RIGHT, padx=(0, 10))
        self.create_section_frame(parent, 'criticality', "Change Criticality", [self.crit_combo])
        widget_frame.pack(fill=X)

    def create_mobile_app_section(self, parent):
        widget_frame = ttk.Frame(parent)
        self.mobile_check = ttk.Checkbutton(widget_frame, text="Is Mobile Application", variable=self.config_vars['mobile_application'])
        self.mobile_check.pack(side=RIGHT, padx=(0, 10))
        self.create_section_frame(parent, 'mobile_application', "Change Mobile Status", [self.mobile_check])
        widget_frame.pack(fill=X)

    def create_particle_section(self, parent):
        widget_frame = ttk.Frame(parent)
        self.particle_check = ttk.Checkbutton(widget_frame, text="Force High Particle Removal", variable=self.config_vars['high_particle_removal'])
        self.particle_check.pack(side=RIGHT, padx=(0, 10))
        self.create_section_frame(parent, 'high_particle_removal', "Change Particle Filtration", [self.particle_check])
        widget_frame.pack(fill=X)
    
    def create_esi_section(self, parent):
        widget_frame = ttk.Frame(parent)
        self.esi_combo = ttk.Combobox(widget_frame, textvariable=self.config_vars['esi_manual'], values=["Auto", "Disposable", "Rebuildable"], width=15)
        self.esi_combo.pack(side=RIGHT, padx=(0, 10))
        self.create_section_frame(parent, 'esi_manual', "Change Service Type", [self.esi_combo])
        widget_frame.pack(fill=X)

    def create_safety_factor_section(self, parent):
        widget_frame = ttk.Frame(parent)
        self.safety_spinbox = ttk.Spinbox(widget_frame, from_=1.0, to=2.0, increment=0.1, textvariable=self.config_vars['safety_factor'], width=10, format="%.1f")
        self.safety_spinbox.pack(side=RIGHT, padx=(0, 10))
        self.create_section_frame(parent, 'safety_factor', "Change Safety Factor", [self.safety_spinbox])
        widget_frame.pack(fill=X)
    
    def create_temperature_section(self, parent):
        self.temp_options_frame = ttk.LabelFrame(parent, text="Temperature Options", padding=10)
        self.create_section_frame(parent, 'temperature', "Change Temperature Settings", [self.temp_options_frame])
        self.temp_options_frame.pack(fill=X, padx=20, pady=5)

        auto_radio = ttk.Radiobutton(self.temp_options_frame, text="Automatic by Location", variable=self.config_vars['auto_temp_lookup'], value=True, command=self.toggle_temp_sub_controls)
        auto_radio.pack(anchor=W)
        self.location_entry = ttk.Entry(self.temp_options_frame, textvariable=self.config_vars['location'], width=30)
        self.location_entry.pack(anchor=W, padx=(20, 0), pady=(0, 5))
        
        manual_radio = ttk.Radiobutton(self.temp_options_frame, text="Manual (°F)", variable=self.config_vars['auto_temp_lookup'], value=False, command=self.toggle_temp_sub_controls)
        manual_radio.pack(anchor=W)
        manual_frame = ttk.Frame(self.temp_options_frame)
        manual_frame.pack(anchor=W, padx=(20, 0))
        ttk.Label(manual_frame, text="Min:").pack(side=LEFT)
        self.min_temp_spin = ttk.Spinbox(manual_frame, from_=-20, to=150, textvariable=self.config_vars['min_amb_temp'], width=8)
        self.min_temp_spin.pack(side=LEFT, padx=(5,10))
        ttk.Label(manual_frame, text="Max:").pack(side=LEFT)
        self.max_temp_spin = ttk.Spinbox(manual_frame, from_=-20, to=150, textvariable=self.config_vars['max_amb_temp'], width=8)
        self.max_temp_spin.pack(side=LEFT, padx=5)

    def toggle_temp_sub_controls(self):
        is_auto = self.config_vars['auto_temp_lookup'].get()
        self.location_entry.config(state="normal" if is_auto else "disabled")
        self.min_temp_spin.config(state="disabled" if is_auto else "normal")
        self.max_temp_spin.config(state="disabled" if is_auto else "normal")
    
    def apply(self):
        self.result = {}
        for key, apply_var in self.apply_vars.items():
            if apply_var.get():
                if key == 'temperature':
                    is_auto = self.config_vars['auto_temp_lookup'].get()
                    self.result['auto_temp_lookup'] = is_auto
                    if is_auto:
                        self.result['location'] = self.config_vars['location'].get()
                        self.result['min_amb_temp'], self.result['max_amb_temp'] = None, None
                    else:
                        min_t, max_t = self.config_vars['min_amb_temp'].get(), self.config_vars['max_amb_temp'].get()
                        if min_t >= max_t:
                            messagebox.showerror("Validation Error", "Maximum temperature must be greater than minimum.", parent=self.dialog)
                            return
                        self.result['location'] = ''
                        self.result['min_amb_temp'], self.result['max_amb_temp'] = min_t, max_t
                elif key == 'esi_manual':
                    value = self.config_vars[key].get()
                    self.result[key] = value if value != 'Auto' else None
                else:
                    self.result[key] = self.config_vars[key].get()
        
        self.dialog.destroy()

    def cancel(self):
        self.result = None
        self.dialog.destroy()