"""Hover help with no polling; destroy cancels delayed popups."""
import tkinter as tk
from tkinter import ttk
from ui_viewport import work_area

def help_icon(parent,text):
    label=ttk.Label(parent,text='?',cursor='question_arrow',padding=(5,0))
    label.pack(side='left',padx=(3,0))
    state={'timer':None,'popup':None}
    def hide(event=None):
        if state['timer']:
            label.after_cancel(state['timer']);state['timer']=None
        if state['popup']:
            state['popup'].destroy();state['popup']=None
    def show():
        state['timer']=None
        if not label.winfo_exists():return
        popup=tk.Toplevel(label);state['popup']=popup;popup.overrideredirect(True)
        ttk.Label(popup,text=text,wraplength=330,padding=10,relief='solid').pack()
        popup.update_idletasks()
        left,top,width,height=work_area(label.winfo_toplevel())
        x=max(left,min(label.winfo_rootx(),left+width-popup.winfo_reqwidth()-8))
        y=max(top,min(label.winfo_rooty()+label.winfo_height()+5,top+height-popup.winfo_reqheight()-8))
        popup.geometry(f'+{x}+{y}')
    def enter(event):
        hide();state['timer']=label.after(350,show)
    label.bind('<Enter>',enter);label.bind('<Leave>',hide);label.bind('<ButtonPress>',hide)
    label.bind('<Destroy>',hide)
    return label
