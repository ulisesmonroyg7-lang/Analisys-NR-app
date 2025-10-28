"""
Styles and theming for NoRia Breather Selection App
Modern UI styling using ttkbootstrap
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

class AppStyles:
    """Custom styles and theming for the application"""
    
    def __init__(self, root):
        self.root = root
        self.style = ttk.Style()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom styles for the application"""
        
        # Custom header style
        self.style.configure(
            'Header.TLabel',
            font=('Arial', 18, 'bold'),
            foreground='#ffffff',
            background='#2b3e50'
        )
        
        # Custom subtitle style
        self.style.configure(
            'Subtitle.TLabel',
            font=('Arial', 10),
            foreground='#bdc3c7'
        )
        
        # Custom section header style
        self.style.configure(
            'Section.TLabel',
            font=('Arial', 12, 'bold'),
            foreground='#34495e'
        )
        
        # Custom info text style
        self.style.configure(
            'Info.TLabel',
            font=('Arial', 9),
            foreground='#7f8c8d'
        )
        
        # Custom success status style
        self.style.configure(
            'Success.TLabel',
            font=('Arial', 9, 'bold'),
            foreground='#27ae60'
        )
        
        # Custom error status style
        self.style.configure(
            'Error.TLabel',
            font=('Arial', 9, 'bold'),
            foreground='#e74c3c'
        )
        
        # Custom progress bar style
        self.style.configure(
            'Custom.TProgressbar',
            troughcolor='#34495e',
            background='#3498db',
            borderwidth=0,
            lightcolor='#3498db',
            darkcolor='#3498db'
        )
        
        # Custom button styles
        self.style.configure(
            'Primary.TButton',
            font=('Arial', 10, 'bold')
        )
        
        self.style.configure(
            'Secondary.TButton',
            font=('Arial', 9)
        )
        
        # Custom frame styles for better organization
        self.style.configure(
            'Card.TFrame',
            relief='solid',
            borderwidth=1,
            background='#ffffff'
        )
        
        # Custom entry style
        self.style.configure(
            'Custom.TEntry',
            fieldbackground='#ffffff',
            borderwidth=1,
            relief='solid'
        )
        
        # Custom combobox style
        self.style.configure(
            'Custom.TCombobox',
            fieldbackground='#ffffff',
            borderwidth=1,
            relief='solid'
        )
    
    @staticmethod
    def get_color_scheme():
        """Get the application color scheme"""
        return {
            'primary': '#3498db',      # Blue
            'secondary': '#95a5a6',    # Gray
            'success': '#27ae60',      # Green
            'warning': '#f39c12',      # Orange
            'danger': '#e74c3c',       # Red
            'info': '#3498db',         # Blue
            'light': '#ecf0f1',        # Light gray
            'dark': '#2c3e50',         # Dark blue-gray
            'background': '#ffffff',    # White
            'text': '#2c3e50',         # Dark text
            'muted': '#7f8c8d'         # Muted gray
        }
    
    @staticmethod
    def apply_hover_effects(widget, enter_color='#2980b9', leave_color='#3498db'):
        """Apply hover effects to buttons"""
        def on_enter(event):
            widget.configure(background=enter_color)
        
        def on_leave(event):
            widget.configure(background=leave_color)
        
        widget.bind('<Enter>', on_enter)
        widget.bind('<Leave>', on_leave)
    
    @staticmethod
    def create_section_frame(parent, title, padding="15"):
        """Create a styled section frame with title"""
        frame = ttk.LabelFrame(
            parent,
            text=title,
            padding=padding,
            bootstyle="primary"
        )
        return frame
    
    @staticmethod
    def create_info_label(parent, text, style="info"):
        """Create an info label with appropriate styling"""
        colors = AppStyles.get_color_scheme()
        color = colors.get(style, colors['muted'])
        
        label = ttk.Label(
            parent,
            text=text,
            font=('Arial', 9),
            foreground=color
        )
        return label
    
    @staticmethod
    def create_status_label(parent, text="Ready", status_type="info"):
        """Create a status label with color coding"""
        colors = AppStyles.get_color_scheme()
        
        status_colors = {
            'ready': colors['info'],
            'success': colors['success'],
            'warning': colors['warning'],
            'error': colors['danger'],
            'processing': colors['primary']
        }
        
        color = status_colors.get(status_type, colors['muted'])
        
        label = ttk.Label(
            parent,
            text=text,
            font=('Arial', 9, 'bold'),
            foreground=color
        )
        return label
    
    @staticmethod
    def create_primary_button(parent, text, command=None, width=None):
        """Create a primary action button"""
        btn = ttk.Button(
            parent,
            text=text,
            command=command,
            bootstyle="primary",
            width=width
        )
        return btn
    
    @staticmethod
    def create_secondary_button(parent, text, command=None, width=None):
        """Create a secondary action button"""
        btn = ttk.Button(
            parent,
            text=text,
            command=command,
            bootstyle="outline-secondary",
            width=width
        )
        return btn
    
    @staticmethod
    def create_success_button(parent, text, command=None, width=None):
        """Create a success action button"""
        btn = ttk.Button(
            parent,
            text=text,
            command=command,
            bootstyle="success",
            width=width
        )
        return btn
    
    @staticmethod
    def create_danger_button(parent, text, command=None, width=None):
        """Create a danger action button"""
        btn = ttk.Button(
            parent,
            text=text,
            command=command,
            bootstyle="outline-danger",
            width=width
        )
        return btn
    
    @staticmethod
    def style_text_widget(text_widget, font_family="Consolas", font_size=9):
        """Apply styling to text widgets"""
        colors = AppStyles.get_color_scheme()
        
        text_widget.configure(
            font=(font_family, font_size),
            background=colors['background'],
            foreground=colors['text'],
            selectbackground=colors['primary'],
            selectforeground='white',
            wrap=tk.WORD,
            relief='solid',
            borderwidth=1
        )
    
    @staticmethod
    def create_tooltip(widget, text):
        """Create a tooltip for a widget"""
        try:
            from tkinter_tooltip import ToolTip
            ToolTip(widget, msg=text, delay=0.5)
        except ImportError:
            # Fallback if tkinter_tooltip is not available
            pass
    
    @staticmethod
    def apply_card_style(frame):
        """Apply card-like styling to a frame"""
        frame.configure(
            relief='solid',
            borderwidth=1,
            padding="15"
        )
    
    @staticmethod
    def create_separator(parent, orient='horizontal'):
        """Create a styled separator"""
        return ttk.Separator(parent, orient=orient, bootstyle="secondary")
    
    @staticmethod
    def create_progress_bar(parent, mode='determinate'):
        """Create a styled progress bar"""
        return ttk.Progressbar(
            parent,
            mode=mode,
            bootstyle="primary-striped"
        )
    
    @staticmethod
    def get_icon_unicode():
        """Get unicode icons for UI elements"""
        return {
            'file': '📁',
            'settings': '⚙️',
            'process': '⚡',
            'export': '💾',
            'success': '✅',
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️',
            'clear': '🗑️',
            'refresh': '🔄'
        }
    
    @staticmethod
    def create_icon_button(parent, text, icon_key, command=None, bootstyle="outline-primary"):
        """Create a button with icon and text"""
        icons = AppStyles.get_icon_unicode()
        icon = icons.get(icon_key, '')
        
        button_text = f"{icon} {text}" if icon else text
        
        btn = ttk.Button(
            parent,
            text=button_text,
            command=command,
            bootstyle=bootstyle
        )
        return btn
    
    @staticmethod
    def apply_responsive_layout(widget, min_width=800, min_height=600):
        """Apply responsive layout constraints"""
        widget.minsize(min_width, min_height)
        
        # Make the widget responsive
        widget.columnconfigure(0, weight=1)
        widget.rowconfigure(0, weight=1)

# Theme configurations for different environments
THEME_CONFIGS = {
    'light': {
        'theme': 'flatly',
        'colors': {
            'bg': '#ffffff',
            'fg': '#212529',
            'select': '#007bff'
        }
    },
    'dark': {
        'theme': 'superhero',
        'colors': {
            'bg': '#2b3e50',
            'fg': '#ffffff',
            'select': '#375a7f'
        }
    },
    'modern': {
        'theme': 'litera',
        'colors': {
            'bg': '#f8f9fa',
            'fg': '#495057',
            'select': '#007bff'
        }
    }
}

def apply_theme(root, theme_name='dark'):
    """Apply a theme to the application"""
    if theme_name in THEME_CONFIGS:
        config = THEME_CONFIGS[theme_name]
        root.style.theme_use(config['theme'])
        return True
    return False