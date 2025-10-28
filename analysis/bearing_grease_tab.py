"""
Bearing Grease Analysis Tab - METODOLOGÍA NORIA COMPLETA (CORREGIDO)
- CORREGIDO: Archivo completo para evitar SyntaxError y ImportError.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import pandas as pd
from typing import Dict, List

from .base_analysis_tab import BaseAnalysisTab
from core.grease_calculator import GreaseCalculator
from ui.config_dialog import ConfigurationDialog
from ui.batch_config_dialog import BatchConfigurationDialog

class GreaseAnalysisDialog:
    pass

class BearingGreaseTab(BaseAnalysisTab):
    """Tab para análisis de grasa de rodamientos con la nueva metodología completa."""
    
    def __init__(self, parent, excel_handler, status_callback):
        self.calculator = GreaseCalculator()
        self.results = {}
        super().__init__(parent, excel_handler, status_callback)

    def on_data_loaded(self):
        try:
            self.results = {}; self.overrides = {}; self.export_btn.config(state="disabled")
            all_data = self.excel_handler.get_all_data()
            self.original_data = self.filter_data_for_analysis(all_data)
            if not self.original_data.empty:
                self.process_btn.config(state="normal")
                self.update_status(f"{len(self.original_data)} records loaded for analysis")
                df_to_show = self.get_analytical_dataframe()
                self.update_data_display(df_to_show)
            else:
                self.process_btn.config(state="disabled")
                self.update_status("No applicable records found for this analysis")
                self.update_data_display(pd.DataFrame())
        except Exception as e:
            self.update_status(f"Error processing loaded data: {str(e)}")

    def get_tab_name(self) -> str:
        return "Bearing Grease Analysis"
    
    def filter_data_for_analysis(self, data: pd.DataFrame) -> pd.DataFrame:
        grease_asset_types = ['Bearing (Grease)', 'Bushing (Grease)', 'Electric Motor (Grease)']
        if data.empty: return pd.DataFrame()
        column_i = data.iloc[:, 8].astype(str).str.strip()
        mask = column_i.isin(grease_asset_types)
        filtered = data[mask].copy()
        self.update_status(f"Found {len(filtered)} bearing/bushing/motor grease records")
        return filtered

    def setup_analysis_section(self):
        analysis_frame = ttk.LabelFrame(self.frame, text="Bearing Grease Analysis", padding="15")
        analysis_frame.pack(fill=BOTH, expand=True, pady=(0, 15))
        self.setup_search_section(analysis_frame)
        self.setup_data_display(analysis_frame)
    
    def setup_search_section(self, parent):
        search_frame = ttk.Frame(parent); search_frame.pack(fill=X, pady=(0, 10))
        ttk.Label(search_frame, text="Search:").pack(side=LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var); search_entry.pack(side=LEFT, fill=X, expand=True)
        search_entry.bind("<KeyRelease>", self.filter_data_live)
        ttk.Button(search_frame, text="Clear", command=self.clear_filter, bootstyle="outline-secondary").pack(side=LEFT)
    
    def setup_data_display(self, parent):
        tree_frame = ttk.Frame(parent); tree_frame.pack(fill=BOTH, expand=True)
        self.tree = ttk.Treeview(tree_frame, show='headings', bootstyle="primary", selectmode='extended')
        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        v_scrollbar.pack(side='right', fill='y'); h_scrollbar.pack(side='bottom', fill='x'); self.tree.pack(fill=BOTH, expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.on_selection_change)

    def get_analysis_columns(self) -> List[str]:
        return ['Status', 'Grease_g', 'Qty_Method', 'Frequency', 'Freq_Unit', 'K_Factor',
                'Bearing_Number', 'Bearing_Type', 'Component', 'Machine']
    
    def setup_tree_columns(self):
        cols = self.get_analysis_columns()
        config = {
            'Status': {'w': 80, 'a': 'center'}, 'Grease_g': {'w': 80, 'a': 'center'},
            'Qty_Method': {'w': 180, 'a': 'w'}, 'Frequency': {'w': 90, 'a': 'center'},
            'Freq_Unit': {'w': 80, 'a': 'center'}, 'K_Factor': {'w': 70, 'a': 'center'},
            'Bearing_Number': {'w': 150, 'a': 'w'}, 'Bearing_Type': {'w': 120, 'a': 'w'},
            'Component': {'w': 150, 'a': 'w'}, 'Machine': {'w': 150, 'a': 'w'}
        }
        self.tree["columns"] = cols; self.tree["displaycolumns"] = cols
        for col in cols:
            self.tree.heading(col, text=col.replace('_', ' '), anchor='w')
            self.tree.column(col, width=config[col]['w'], anchor=config[col]['a'])

    def process_analysis(self):
        if self.original_data.empty: return messagebox.showwarning("No Data", "No bearing grease data available")
        self.processing = True; self.results = {}; self.process_btn.config(state="disabled")
        self.update_status("Processing bearing grease analysis (quantity and frequency)..."); self.frame.update()
        try:
            for index, row in self.original_data.iterrows():
                self.results[index] = self.calculator.calculate_complete_analysis(row)
            self.update_status("Analysis complete"); self.export_btn.config(state="normal"); self.refresh_display()
            successful_qty = sum(1 for res in self.results.values() if res['gq_grams'] > 0)
            successful_freq = sum(1 for res in self.results.values() if res['frequency_hours'] > 0)
            messagebox.showinfo("Analysis Complete", f"Processed {len(self.results)} records.\n{successful_qty} quantity calculations.\n{successful_freq} frequency calculations.")
        except Exception as e:
            messagebox.showerror("Error", f"Analysis failed: {str(e)}"); self.update_status(f"Analysis failed: {str(e)}")
        finally:
            self.processing = False; self.process_btn.config(state="normal"); self.on_selection_change(None)

    def get_analytical_dataframe(self) -> pd.DataFrame:
        if self.original_data.empty: return pd.DataFrame()
        df = self.original_data.copy()
        if self.results:
            df['Grease_g'] = df.index.map(lambda i: self.results.get(i, {}).get('gq_grams', 0))
            df['Qty_Method'] = df.index.map(lambda i: self.results.get(i, {}).get('quantity_method', 'Pending'))
            df['Frequency'] = df.index.map(lambda i: self.results.get(i, {}).get('frequency_hours', 0))
            df['Freq_Unit'] = df.index.map(lambda i: self.results.get(i, {}).get('frequency_unit', 'N/A'))
            df['K_Factor'] = df.index.map(lambda i: self.results.get(i, {}).get('K_factor', 0))
            df['Status'] = df.index.map(lambda i: "Success" if (self.results.get(i, {}).get('gq_grams', 0) > 0 or self.results.get(i, {}).get('frequency_hours', 0) > 0) else "Failed")
        else:
            for col in ['Grease_g', 'Qty_Method', 'Frequency', 'Freq_Unit', 'K_Factor', 'Status']: df[col] = 'Pending'
        
        df['Bearing_Number'] = df.get('(D) Bearing/Housing Number (DE - if more than 1)', '')
        df['Bearing_Type'] = df.get('(D) Bearing Type', '')
        df['Component'] = df.get('Component', '')
        df['Machine'] = df.get('Machine', '')
        return df

    def update_data_display(self, df_to_show: pd.DataFrame):
        for item in self.tree.get_children(): self.tree.delete(item)
        if df_to_show.empty: return
        if not self.tree["columns"]: self.setup_tree_columns()
        for index, row in df_to_show.iterrows():
            values = []
            for col in self.get_analysis_columns():
                val = row.get(col, '')
                if isinstance(val, (int, float)) and pd.notna(val):
                    if col in ['Grease_g', 'K_Factor']: values.append(f"{val:.2f}")
                    elif col == 'Frequency': values.append(f"{val:,.0f}" if val >= 1000 else f"{val:.1f}")
                    else: values.append(str(val))
                else:
                    values.append(str(val) if pd.notna(val) else '')
            self.tree.insert("", "end", iid=index, values=values)
    
    def filter_data_live(self, event=None): self.filter_data()
    def clear_filter(self): self.search_var.set(""); self.filter_data()
    def refresh_display(self): self.filter_data()
    
    def filter_data(self):
        df = self.get_analytical_dataframe()
        query = self.search_var.get().lower().strip()
        if not query: self.update_data_display(df); return
        mask = df.apply(lambda row: any(query in str(cell).lower() for cell in row[self.get_analysis_columns()]), axis=1)
        self.update_data_display(df[mask])

    def perform_export(self, file_path: str):
        if not self.results: raise Exception("No analysis results to export")
        results_list = []
        for index, res in self.results.items():
            row_data = {
                'original_index': index,
                'Grease_Quantity_grams': res.get('gq_grams'),
                'Quantity_Method': res.get('quantity_method'),
                'Calculation_Error': res.get('error', ''),
                'Frequency': res.get('frequency_hours'),
                'Frequency_Unit': res.get('frequency_unit'),
                'K_Factor_Total': res.get('K_factor'),
                **{f"K_{key}": val for key, val in res.get('factors', {}).items()}
            }
            results_list.append(row_data)
        results_df = pd.DataFrame(results_list)
        if results_df.empty: raise Exception("No results data to export")
        success, msg = self.excel_handler.save_results_with_merge(results_df, file_path)
        if not success: raise Exception(msg)
            
    def on_selection_change(self, event):
        self.edit_selected_btn.config(state="normal" if self.tree.selection() else "disabled")
        self.ai_btn.config(state="disabled")

    def open_edit_dialog(self):
        messagebox.showinfo("Not Applicable", "Batch editing is not applicable for this calculation.")

    def clear_all(self):
        if messagebox.askyesno("Confirm", "Clear all data and restart this analysis?"):
            super().clear_all()
            self.results = {}; self.search_var.set("")
            for item in self.tree.get_children(): self.tree.delete(item)
            self.update_status("Analysis cleared. Load a data report to continue.")