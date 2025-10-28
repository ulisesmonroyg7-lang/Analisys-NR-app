# --- analysis/base_analysis_tab.py ---

"""
Base Analysis Tab Class - VERSIÓN CON DEFAULTS GARANTIZADOS
- CORREGIDO: get_current_config() siempre retorna temperaturas ambientales válidas
"""
import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

class BaseAnalysisTab(ABC):
    """Base class for all analysis tabs"""
    
    def __init__(self, parent, excel_handler, status_callback):
        self.parent = parent
        self.excel_handler = excel_handler
        self.status_callback = status_callback
        
        self.frame = ttk.Frame(parent, padding="20")
        
        self.config_data = {}
        self.overrides = {}
        self.original_data = pd.DataFrame()
        self.filtered_data = pd.DataFrame()
        self.results = {}
        self.processing = False
        self.data_processor = None
        
        self.setup_ui()
        
    def setup_ui(self):
        self.setup_configuration_section()
        self.setup_analysis_section()
        self.setup_action_section()
        self.setup_status_section()
        
    def setup_configuration_section(self):
        """Setup configuration section common to all tabs"""
        config_frame = ttk.LabelFrame(self.frame, text="Configuration", padding="15")
        config_frame.pack(fill=X, pady=(0, 15))
        
        global_frame = ttk.Frame(config_frame)
        global_frame.pack(fill=X)
        
        ttk.Label(global_frame, text="Default Settings:").pack(side=LEFT, padx=(0, 10))
        
        # Control de Criticidad
        ttk.Label(global_frame, text="Criticality:").pack(side=LEFT, padx=(10, 5))
        self.criticality_var = tk.StringVar(value="A")
        criticality_combo = ttk.Combobox(
            global_frame, textvariable=self.criticality_var, 
            values=["A", "B1", "B2", "C"], state="readonly", width=8
        )
        criticality_combo.pack(side=LEFT)
        criticality_combo.bind("<<ComboboxSelected>>", self.on_config_change)

        # Filtro de Marca
        ttk.Label(global_frame, text="Brand Filter:").pack(side=LEFT, padx=(15, 5))
        self.brand_filter_var = tk.StringVar(value="All Brands")
        brand_combo = ttk.Combobox(
            global_frame, textvariable=self.brand_filter_var,
            values=["All Brands", "Des-Case", "Air Sentry"], state="readonly", width=15
        )
        brand_combo.pack(side=LEFT)
        
        ttk.Button(
            global_frame, text="Advanced...", 
            command=self.open_advanced_config, bootstyle="outline-secondary"
        ).pack(side=RIGHT)
        
        ttk.Separator(config_frame, orient='horizontal').pack(fill='x', pady=10)
        
        individual_frame = ttk.Frame(config_frame)
        individual_frame.pack(fill=X)
        
        ttk.Label(individual_frame, text="Individual Settings:").pack(side=LEFT, padx=(0, 10))
        
        self.edit_selected_btn = ttk.Button(
            individual_frame, text="Edit Selected...", 
            command=self.open_edit_dialog, state="disabled"
        )
        self.edit_selected_btn.pack(side=LEFT)
        
    def get_current_config(self) -> Dict:
        """Get current configuration, ensuring all defaults are ALWAYS set."""
        # Establecer TODOS los defaults primero
        config = {
            'criticality': 'A',
            'mobile_application': False,
            'max_amb_temp': 80.0,  # ← SIEMPRE presente
            'min_amb_temp': 60.0,  # ← SIEMPRE presente
            'high_particle_removal': False,
            'esi_manual': None,
            'safety_factor': 1.4,
            'verbose_trace': False,
            'include_calculations': False,
            'gemini_api_key': '',
            'enable_manual_gpm': False,
            'manual_gpm_override': 0.0,
            'brand_filter': 'All Brands'
        }
        
        # Actualizar con config_data guardada (puede sobrescribir defaults)
        config.update(self.config_data)
        
        # Aplicar valores actuales de UI (sobrescribe todo lo anterior)
        config.update({
            'criticality': self.criticality_var.get(),
            'brand_filter': self.brand_filter_var.get()
        })
        
        # VALIDACIÓN DE SEGURIDAD: Asegurar que las temperaturas NUNCA sean None
        if config['max_amb_temp'] is None or config['min_amb_temp'] is None:
            config['max_amb_temp'] = 80.0
            config['min_amb_temp'] = 60.0
        
        return config

    @abstractmethod
    def setup_analysis_section(self):
        pass
    
    def setup_action_section(self):
        action_frame = ttk.Frame(self.frame)
        action_frame.pack(fill=X, pady=(0, 15))
        
        self.process_btn = ttk.Button(
            action_frame, text="Process Analysis", 
            command=self.process_analysis, bootstyle="primary", state="disabled"
        )
        self.process_btn.pack(side=LEFT, padx=(0, 10))
        
        self.ai_btn = ttk.Button(
            action_frame, text="AI Analysis...", 
            command=self.start_ai_analysis, state="disabled"
        )
        self.ai_btn.pack(side=LEFT, padx=(0, 10))
        
        self.export_btn = ttk.Button(
            action_frame, text="Export Results", 
            command=self.export_results, bootstyle="success", state="disabled"
        )
        self.export_btn.pack(side=LEFT)
        
        ttk.Button(
            action_frame, text="Clear All", 
            command=self.clear_all, bootstyle="outline-danger"
        ).pack(side=RIGHT)
    
    def setup_status_section(self):
        status_frame = ttk.LabelFrame(self.frame, text="Status", padding="15")
        status_frame.pack(fill=X, side=BOTTOM)
        
        self.local_status_var = tk.StringVar(value="Ready to load data")
        self.local_status_label = ttk.Label(status_frame, textvariable=self.local_status_var)
        self.local_status_label.pack(anchor=W)
    
    @abstractmethod
    def filter_data_for_analysis(self, data: pd.DataFrame) -> pd.DataFrame:
        pass
    
    @abstractmethod
    def process_analysis(self):
        pass
    
    @abstractmethod
    def get_analysis_columns(self) -> List[str]:
        pass
    
    def on_data_loaded(self):
        try:
            self.results = {}
            self.overrides = {}
            self.data_processor = None
            self.export_btn.config(state="disabled")
            if hasattr(self, 'summary_btn'):
                self.summary_btn.config(state="disabled")
            
            all_data = self.excel_handler.get_all_data()
            self.original_data = self.filter_data_for_analysis(all_data)
            
            if not self.original_data.empty:
                self.process_btn.config(state="normal")
                self.update_status(f"{len(self.original_data)} records loaded for analysis")
            else:
                self.process_btn.config(state="disabled")
                self.update_status("No applicable records found for this analysis")
            
            self.refresh_display()
        except Exception as e:
            self.update_status(f"Error processing loaded data: {str(e)}")
    
    def on_catalog_loaded(self):
        self.update_status("Breather catalog updated")
    
    def on_config_change(self, event=None):
        self.refresh_display()
    
    def update_status(self, message: str):
        self.local_status_var.set(message)
        if self.status_callback:
            self.status_callback(self.get_tab_name(), message)
    
    def refresh_display(self):
        pass
    
    def open_advanced_config(self):
        from ui.config_dialog import ConfigurationDialog
        dialog = ConfigurationDialog(self.frame, self.get_current_config())
        if dialog.result:
            self.config_data.update(dialog.result)
            self.update_status("Advanced configuration updated")
            self.refresh_display()
    
    def open_edit_dialog(self):
        pass
    
    def start_ai_analysis(self):
        pass
    
    def export_results(self):
        if not self.results:
            messagebox.showerror("Error", "No results to export")
            return
        
        from tkinter import filedialog
        default_name = f"{self.get_tab_name().replace(' ', '_').replace('/', '_')}_Results.xlsx"
        file_path = filedialog.asksaveasfilename(
            title="Save Results", 
            initialfile=default_name, 
            defaultextension=".xlsx", 
            filetypes=[("Excel files", "*.xlsx")]
        )
        
        if file_path:
            try:
                self.perform_export(file_path)
                messagebox.showinfo("Success", f"Results exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Export failed:\n{str(e)}")
    
    @abstractmethod
    def perform_export(self, file_path: str):
        pass
    
    def clear_all(self):
        self.original_data = pd.DataFrame()
        self.filtered_data = pd.DataFrame()
        self.results = {}
        self.overrides = {}
        self.data_processor = None
        
        self.process_btn.config(state="disabled")
        self.export_btn.config(state="disabled")
        self.ai_btn.config(state="disabled")
        self.edit_selected_btn.config(state="disabled")
    
    @abstractmethod
    def get_tab_name(self) -> str:
        pass