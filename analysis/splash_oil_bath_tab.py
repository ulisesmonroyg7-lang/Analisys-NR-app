# --- analysis/splash_oil_bath_tab.py ---
"""
Splash/Oil Bath Breather Analysis Tab - VERSIÓN FINAL CORREGIDA
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import pandas as pd
from typing import Dict, List, Optional, Any
import logging

from .base_analysis_tab import BaseAnalysisTab
from core import DataProcessor, RuleEngine
from ui.config_dialog import ConfigurationDialog
from ui.batch_config_dialog import BatchConfigurationDialog
from ui.chat_dialog import ChatDialog
from utils.gemini_client import GeminiChat, create_dossier_prompt_for_success, create_summary_prompt_for_batch, create_failure_analysis_prompt

logger = logging.getLogger(__name__)


class SplashOilBathTab(BaseAnalysisTab):
    """Splash/Oil Bath Breather Analysis Tab"""
    
    def __init__(self, parent, excel_handler, status_callback):
        super().__init__(parent, excel_handler, status_callback)
        self.data_processor = None
        self.rule_engine_for_factors = RuleEngine({})
        
    def get_tab_name(self) -> str: 
        return "Splash/Oil Bath Breathers"
        
    def filter_data_for_analysis(self, data: pd.DataFrame) -> pd.DataFrame:
        if data.empty:
            return pd.DataFrame()
        splash_types = ['Gearbox Housing (Oil)', 'Bearing (Oil)', 'Pump (Oil)', 'Electric Motor Bearing (Oil)', 'Blower (Oil)']
        column_i = data.iloc[:, 8].astype(str)
        mask_exact = column_i.str.strip().isin(splash_types)
        splash_keywords = [r'gearbox.*housing.*oil', r'^bearing.*oil$', r'^pump.*oil$', r'electric.*motor.*bearing.*oil', r'^blower.*oil$']
        mask_keywords = pd.Series([False] * len(data), index=data.index)
        for keyword in splash_keywords:
            mask_keywords |= column_i.str.contains(keyword, case=False, na=False, regex=True)
        filtered = data[mask_exact | mask_keywords].copy()
        self.update_status(f"Found {len(filtered)} splash/oil bath records")
        return filtered
        
    def setup_analysis_section(self):
        analysis_frame = ttk.LabelFrame(self.frame, text="Splash/Oil Bath Analysis", padding="15")
        analysis_frame.pack(fill=BOTH, expand=True, pady=(0, 15))
        self.setup_search_and_filter_section(analysis_frame)
        self.setup_data_display(analysis_frame)

    def setup_search_and_filter_section(self, parent):
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill=X, pady=(0, 10))
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=X)
        ttk.Label(search_frame, text="Search:").pack(side=LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=LEFT, fill=X, expand=True)
        search_entry.bind("<KeyRelease>", self._apply_filters)
        ttk.Button(search_frame, text="Clear", command=self.clear_filter, bootstyle="outline-secondary").pack(side=LEFT, padx=10)
        filter_frame = ttk.Frame(main_frame)
        filter_frame.pack(fill=X, pady=(10, 0))
        ttk.Label(filter_frame, text="Filtros Rápidos:").pack(side=LEFT, padx=(0, 10))
        self.filter_vars = {'requires_action': tk.BooleanVar(value=False), 'critical_a': tk.BooleanVar(value=False), 'no_solution': tk.BooleanVar(value=False)}
        style = ttk.Style()
        style.configure('Toggle.TButton', font=('Arial', 9))
        ttk.Checkbutton(filter_frame, text="⚠️ Requiere Acción", variable=self.filter_vars['requires_action'], command=self._apply_filters, style='Toggle.TButton').pack(side=LEFT, padx=5)
        ttk.Checkbutton(filter_frame, text="🅰️ Críticos (A)", variable=self.filter_vars['critical_a'], command=self._apply_filters, style='Toggle.TButton').pack(side=LEFT, padx=5)
        ttk.Checkbutton(filter_frame, text="❌ Sin Solución", variable=self.filter_vars['no_solution'], command=self._apply_filters, style='Toggle.TButton').pack(side=LEFT, padx=5)

    def setup_data_display(self, parent):
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=BOTH, expand=True)
        self.tree = ttk.Treeview(tree_frame, show='headings', bootstyle="primary", selectmode='extended')
        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        v_scrollbar.pack(side='right', fill='y')
        h_scrollbar.pack(side='bottom', fill='x')
        self.tree.pack(fill=BOTH, expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.on_selection_change)
    
    def setup_action_section(self):
        action_frame = ttk.Frame(self.frame)
        action_frame.pack(fill=X, pady=(0, 15))
        self.process_btn = ttk.Button(action_frame, text="Process Analysis", command=self.process_analysis, bootstyle="primary", state="disabled")
        self.process_btn.pack(side=LEFT, padx=(0, 10))
        self.summary_btn = ttk.Button(action_frame, text="📄 Generar Resumen IA", command=self.generate_ai_summary, state="disabled")
        self.summary_btn.pack(side=LEFT, padx=(0, 10))
        self.ai_btn = ttk.Button(action_frame, text="🤖 Analizar Selección con IA", command=self.start_ai_analysis, state="disabled")
        self.ai_btn.pack(side=LEFT, padx=(0, 10))
        self.export_btn = ttk.Button(action_frame, text="Export Results", command=self.export_results, bootstyle="success", state="disabled")
        self.export_btn.pack(side=LEFT)
        ttk.Button(action_frame, text="Clear All", command=self.clear_all, bootstyle="outline-danger").pack(side=RIGHT)

    def get_analysis_columns(self) -> List[str]:
        return ['Status', 'Recommended_Model', 'CFM_Required', 'Criticality', 'Mobile', 'CI', 'WCCI', 'ESI', 'Machine', 'Component']
        
    def setup_tree_columns(self):
        cols = self.get_analysis_columns()
        config = {'Status': {'w': 100, 'a': 'w'}, 'Recommended_Model': {'w': 120, 'a': 'w'}, 'CFM_Required': {'w': 100, 'a': 'center'}, 'Criticality': {'w': 80, 'a': 'center'}, 'Mobile': {'w': 60, 'a': 'center'}, 'CI': {'w': 60, 'a': 'center'}, 'WCCI': {'w': 80, 'a': 'center'}, 'ESI': {'w': 120, 'a': 'w'}, 'Machine': {'w': 150, 'a': 'w'}, 'Component': {'w': 150, 'a': 'w'}}
        self.tree["columns"] = cols
        self.tree["displaycolumns"] = cols
        for col in cols:
            header_text = col.replace("_", " ")
            self.tree.heading(col, text=header_text, anchor='w')
            self.tree.column(col, width=config.get(col, {'w': 100})['w'], anchor=config.get(col, {'a': 'w'})['a'])
            
    def get_analytical_dataframe(self) -> pd.DataFrame:
        if self.original_data.empty:
            return pd.DataFrame()
        df = self.original_data.copy()
        g_config = self.get_current_config()
        factors_data = []
        for idx, row in df.iterrows():
            f_config = g_config.copy()
            if idx in self.overrides:
                f_config.update(self.overrides[idx])
            factors = self.rule_engine_for_factors._extract_operational_factors(row, f_config)
            factors['Criticality'] = f_config.get('criticality', g_config['criticality'])
            factors_data.append(factors)
        factors_df = pd.DataFrame(factors_data, index=df.index).rename(columns={'ci': 'CI', 'wcci': 'WCCI', 'esi': 'ESI', 'mobile_application': 'Mobile'})
        cols_to_add = ['Criticality', 'Mobile', 'CI', 'WCCI', 'ESI']
        cols_to_drop = [col for col in cols_to_add if col in df.columns]
        if cols_to_drop:
            df = df.drop(columns=cols_to_drop)
        df = df.join(factors_df[cols_to_add])
        if self.data_processor and self.data_processor.results:
            res = self.data_processor.results
            df['CFM_Required'] = df.index.map(lambda i: res.get(i, {}).get('thermal_analysis', {}).get('cfm_required'))
            df['Status'] = df.index.map(lambda i: res.get(i, {}).get('result_status', 'Failed'))
            def get_model(idx):
                result = res.get(idx, {})
                selected_list = result.get('selected_breather', [])
                if selected_list:
                    return selected_list[0].get('Model', '-')
                return 'No Solution Found'
            df['Recommended_Model'] = df.index.map(get_model)
        else:
            df['CFM_Required'] = '-'
            df['Recommended_Model'] = '-'
            df['Status'] = 'Pending'
        return df
        
    def _apply_filters(self, event=None):
        df = self.get_analytical_dataframe()
        if 'Status' not in df.columns:
            return
        if self.filter_vars['requires_action'].get():
            action_statuses = ['Sub-optimal', 'Optimal - Modification required', 'Optimal - Remote Installation']
            df = df[df['Status'].astype(str).isin(action_statuses)]
        if self.filter_vars['critical_a'].get():
            df = df[df['Criticality'].astype(str) == 'A']
        if self.filter_vars['no_solution'].get():
            df = df[df['Status'].astype(str) == 'No Solution Found']
        query = self.search_var.get().lower().strip()
        if query:
            for term in query.split():
                if ":" in term:
                    key, val = term.split(":", 1)
                    col_map = {'crit': 'Criticality', 'mobile': 'Mobile', 'ci': 'CI', 'wcci': 'WCCI', 'esi': 'ESI', 'model': 'Recommended_Model', 'status': 'Status'}
                    if key in col_map:
                        df = df[df[col_map[key]].astype(str).str.lower().str.contains(val, na=False)]
                else:
                    mask = (df['Machine'].str.lower().str.contains(term, na=False) | df['Component'].str.lower().str.contains(term, na=False))
                    df = df[mask]
        self.update_data_display(df)
        
    def update_data_display(self, df_to_show: pd.DataFrame):
        for item in self.tree.get_children():
            self.tree.delete(item)
        if df_to_show.empty:
            return
        if not self.tree["columns"]:
            self.setup_tree_columns()
        for index, row in df_to_show.iterrows():
            values = []
            for col in self.get_analysis_columns():
                val = row.get(col, '')
                if isinstance(val, float) and pd.notna(val):
                    values.append(f"{val:.2f}")
                else:
                    values.append(str(val) if pd.notna(val) else '')
            self.tree.insert("", "end", iid=index, values=values)
            
    def clear_filter(self): 
        self.search_var.set("")
        for var in self.filter_vars.values():
            var.set(False)
        self._apply_filters()
        
    def refresh_display(self):
        self._apply_filters()
        
    def on_selection_change(self, event):
        selected_ids = self.tree.selection()
        self.edit_selected_btn.config(state="normal" if selected_ids else "disabled")
        if self.data_processor and len(selected_ids) == 1:
            idx = int(selected_ids[0])
            result = self.results.get(idx, {})
            if result.get('success'):
                self.ai_btn.config(text="🤖 Analizar Selección con IA", command=self.start_ai_analysis, state="normal")
            elif result.get('result_status') in ['No Solution Found', 'Error']:
                self.ai_btn.config(text="🔬 Analizar Fallo con IA", command=self.start_ai_failure_analysis, state="normal")
            else:
                self.ai_btn.config(state="disabled")
        else:
            self.ai_btn.config(state="disabled")
            
    def process_analysis(self):
        if self.original_data.empty:
            messagebox.showwarning("No Data", "No data available")
            return
        self.processing = True
        self.results = {}
        self.process_btn.config(state="disabled")
        self.update_status("Processing splash/oil bath analysis...")
        self.frame.update()
        try:
            self.data_processor = DataProcessor(self.excel_handler, self.original_data, self.get_current_config(), self.overrides)
            self.results = self.data_processor.process_all_records()
            self.update_status("Analysis complete")
            self.export_btn.config(state="normal")
            self.summary_btn.config(state="normal")
            self.refresh_display()
            total = len(self.results)
            successful = sum(1 for r in self.results.values() if r.get('success'))
            messagebox.showinfo("Analysis Complete", f"Processed {total} records\n{successful} successful analyses")
        except Exception as e:
            messagebox.showerror("Error", f"Analysis failed: {str(e)}")
            self.update_status(f"Analysis failed: {str(e)}")
            logger.error(f"Analysis error: {str(e)}", exc_info=True)
        finally:
            self.processing = False
            self.process_btn.config(state="normal")
            self.on_selection_change(None)
            
    def open_edit_dialog(self):
        selected = self.tree.selection()
        if not selected:
            return
        if len(selected) == 1:
            idx = int(selected[0])
            config = self.get_current_config().copy()
            if idx in self.overrides:
                config.update(self.overrides[idx])
            dialog = ConfigurationDialog(self.frame, config)
        else:
            dialog = BatchConfigurationDialog(self.frame, len(selected))
        if dialog.result:
            for item_id in selected:
                idx = int(item_id)
                if idx not in self.overrides:
                    self.overrides[idx] = {}
                self.overrides[idx].update(dialog.result)
            self.update_status(f"Configuration updated for {len(selected)} asset(s)")
            self.refresh_display()

    def clear_all(self):
        if messagebox.askyesno("Confirmar", "¿Limpiar todos los datos y reiniciar este análisis?"):
            super().clear_all()
            self.search_var.set("")
            for var in self.filter_vars.values():
                var.set(False)
            if hasattr(self, 'summary_btn'):
                self.summary_btn.config(state="disabled")
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.update_status("Análisis limpiado. Carga un reporte de datos para continuar.")
            
    def _get_api_key_and_chat_instance(self):
        api_key = self.get_current_config().get('gemini_api_key')
        if not api_key:
            messagebox.showwarning("API Key Missing", "Provide a Gemini API Key in Advanced settings.")
            return None
        chat = GeminiChat(api_key)
        if not chat.model:
            messagebox.showerror("API Error", "Could not configure Gemini API.")
            return None
        return chat

    def start_ai_analysis(self):
        selected = self.tree.selection()
        if not (selected and len(selected) == 1):
            return
        chat = self._get_api_key_and_chat_instance()
        if not chat:
            return
        idx = int(selected[0])
        asset_result = self.results.get(idx)
        if not asset_result or not asset_result.get('success'):
            messagebox.showinfo("Analysis Unavailable", "Cannot analyze a failed asset.")
            return
        prompt = create_dossier_prompt_for_success(asset_result)
        success, msg = chat.start_chat_and_get_greeting(prompt)
        if not success:
            messagebox.showerror("AI Error", f"Could not start chat.\nError: {msg}")
            return
        ChatDialog(self.frame, title=f"Analysis for Asset {idx}", gemini_chat_instance=chat, initial_message=msg)

    def start_ai_failure_analysis(self):
        selected = self.tree.selection()
        if not (selected and len(selected) == 1):
            return
        chat = self._get_api_key_and_chat_instance()
        if not chat:
            return
        idx = int(selected[0])
        asset_result = self.results.get(idx)
        prompt = create_failure_analysis_prompt(asset_result)
        success, msg = chat.start_chat_and_get_greeting(prompt)
        if not success:
            messagebox.showerror("AI Error", f"Could not start chat.\nError: {msg}")
            return
        ChatDialog(self.frame, title=f"Failure Diagnosis for Asset {idx}", gemini_chat_instance=chat, initial_message=msg)

    def generate_ai_summary(self):
        if not self.results:
            messagebox.showwarning("No Data", "Process analysis first.")
            return
        chat = self._get_api_key_and_chat_instance()
        if not chat:
            return
        self.update_status("Generating AI Executive Summary...")
        self.frame.update()
        summary_data = {'total': 0, 'status_counts': {}, 'top_models': {}}
        for res in self.results.values():
            summary_data['total'] += 1
            status = res.get('result_status', 'Error')
            summary_data['status_counts'][status] = summary_data['status_counts'].get(status, 0) + 1
            if res.get('success') and res.get('selected_breather'):
                model = res['selected_breather'][0].get('Model')
                summary_data['top_models'][model] = summary_data['top_models'].get(model, 0) + 1
        prompt = create_summary_prompt_for_batch(summary_data)
        summary_text = chat.send_message(prompt)
        self.update_status("AI Summary generated.")
        summary_dialog = tk.Toplevel(self.frame)
        summary_dialog.title("AI Executive Summary")
        summary_dialog.geometry("700x500")
        summary_dialog.transient(self.frame)
        summary_dialog.grab_set()
        text_area = scrolledtext.Text(summary_dialog, wrap=WORD, font=("Arial", 10), relief="flat")
        text_area.pack(expand=True, fill=BOTH, padx=15, pady=10)
        text_area.insert(tk.INSERT, summary_text)
        text_area.config(state="disabled")
        def copy_to_clipboard():
            self.frame.clipboard_clear()
            self.frame.clipboard_append(text_area.get("1.0", tk.END))
            copy_btn.config(text="Copied!")
        copy_btn = ttk.Button(summary_dialog, text="Copy to Clipboard", command=copy_to_clipboard)
        copy_btn.pack(pady=10)
        
    def perform_export(self, file_path: str):
        if not self.data_processor:
            raise Exception("No analysis results to export.")
        results_df = self.data_processor.get_results_as_dataframe()
        if results_df.empty:
            raise Exception("No valid results data to export.")
        current_config = self.get_current_config()
        if current_config.get('verbose_trace'):
            logger.info("Exporting with verbose rule trace enabled")
        if current_config.get('include_calculations'):
            logger.info("Exporting with intermediate calculations enabled")
        success, msg = self.excel_handler.save_results_with_merge(results_df, file_path)
        if not success:
            raise Exception(msg)
        columns_exported = len(results_df.columns)
        rows_exported = len(results_df)
        logger.info(f"✅ Exported {rows_exported} rows with {columns_exported} columns to {file_path}")
        if current_config.get('verbose_trace') or current_config.get('include_calculations'):
            extra_cols = []
            if current_config.get('verbose_trace'):
                extra_cols.append("Verbose_Rule_Trace")
                extra_cols.append("Rejected_Candidates")
            if current_config.get('include_calculations'):
                extra_cols.append("Thermal_Calculations")
            logger.info(f"📊 Additional diagnostic columns included: {', '.join(extra_cols)}")