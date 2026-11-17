"""Scrollable layouts for small work areas; Windows scales the entire UI uniformly."""
import ctypes
import tkinter as tk
from tkinter import ttk


def enable_dpi_scaling():
    # GDI-scaled unaware mode keeps Tk's pixel artwork and text in one coordinate
    # space. Windows scales the whole window on high-DPI monitors (including moves).
    # Fall back to ordinary Windows DPI virtualization on older Windows versions.
    try:
        fn=ctypes.windll.user32.SetProcessDpiAwarenessContext
        fn.argtypes=[ctypes.c_void_p];fn.restype=ctypes.c_bool
        fn(ctypes.c_void_p(-5))
    except (AttributeError,OSError):
        pass


def work_area(window):
    try:
        from ctypes import wintypes as w
        class MonitorInfo(ctypes.Structure):
            _fields_=[('size',w.DWORD),('monitor',w.RECT),('work',w.RECT),('flags',w.DWORD)]
        user=ctypes.windll.user32
        user.MonitorFromWindow.argtypes=[w.HWND,w.DWORD];user.MonitorFromWindow.restype=w.HANDLE
        user.GetMonitorInfoW.argtypes=[w.HANDLE,ctypes.POINTER(MonitorInfo)];user.GetMonitorInfoW.restype=w.BOOL
        hwnd=int(window.wm_frame(),0)
        monitor=user.MonitorFromWindow(hwnd,2)
        info=MonitorInfo();info.size=ctypes.sizeof(info)
        if monitor and user.GetMonitorInfoW(monitor,ctypes.byref(info)):
            rect=info.work
            return rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top
    except (AttributeError,OSError,ValueError,tk.TclError):pass
    return 0,0,window.winfo_screenwidth(),window.winfo_screenheight()


class Viewport:
    def __init__(self,window,background='#151b25'):
        self.window=window
        self.frame=tk.Frame(window,bg=background)
        self.frame.pack(fill='both',expand=True)
        self.frame.rowconfigure(0,weight=1);self.frame.columnconfigure(0,weight=1)
        self.canvas=tk.Canvas(self.frame,bg=background,highlightthickness=0,width=1,height=1)
        self.canvas.grid(row=0,column=0,sticky='nsew')
        self.vertical=ttk.Scrollbar(self.frame,orient='vertical',command=self.canvas.yview)
        self.horizontal=ttk.Scrollbar(self.frame,orient='horizontal',command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vertical.set,xscrollcommand=self.horizontal.set)
        self.holder=tk.Frame(self.canvas,bg=background)
        self.body=tk.Frame(self.holder,bg=background)
        self.body.grid(row=0,column=0,sticky='nsew')
        self.holder.rowconfigure(0,weight=1);self.holder.columnconfigure(0,weight=1)
        self.item=self.canvas.create_window(0,0,anchor='nw',window=self.holder)
        self.pending=None
        window.bind('<Configure>',self.schedule,add='+')
        self.body.bind('<Configure>',self.schedule)
        self.canvas.bind('<Configure>',self.schedule)
        window.bind('<MouseWheel>',self.wheel,add='+')
        window.bind('<Shift-MouseWheel>',lambda e:self.wheel(e,True),add='+')
        window.bind('<FocusIn>',self.reveal,add='+')
    def schedule(self,event=None):
        if self.pending is None:self.pending=self.window.after_idle(self.layout)
    def layout(self):
        self.pending=None
        if not self.canvas.winfo_exists():return
        w=max(self.canvas.winfo_width(),self.body.winfo_reqwidth())
        h=max(self.canvas.winfo_height(),self.body.winfo_reqheight())
        self.holder.columnconfigure(0,minsize=self.canvas.winfo_width())
        self.holder.rowconfigure(0,minsize=self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0,0,w,h))
        if h>self.canvas.winfo_height()+1:self.vertical.grid(row=0,column=1,sticky='ns')
        else:self.vertical.grid_remove();self.canvas.yview_moveto(0)
        if w>self.canvas.winfo_width()+1:self.horizontal.grid(row=1,column=0,sticky='ew')
        else:self.horizontal.grid_remove();self.canvas.xview_moveto(0)
    def wheel(self,event,horizontal=False):
        # Preserve the normal wheel behavior of editable controls and nested lists.
        if event.widget.winfo_toplevel()!=self.window:return
        if event.widget.winfo_class() in ('TCombobox','Text','Listbox','Treeview','TScale'):return
        view=self.canvas.xview if horizontal else self.canvas.yview
        if view()!=(0.0,1.0):
            (self.canvas.xview_scroll if horizontal else self.canvas.yview_scroll)(-int(event.delta/120),'units')
            return 'break'
    def reveal(self,event):
        widget=event.widget
        if widget==self.window or widget.winfo_toplevel()!=self.window:return
        try:
            x=widget.winfo_rootx()-self.body.winfo_rootx();y=widget.winfo_rooty()-self.body.winfo_rooty()
            for position,length,total,view,move in ((x,widget.winfo_width(),self.body.winfo_width(),self.canvas.xview,self.canvas.xview_moveto),(y,widget.winfo_height(),self.body.winfo_height(),self.canvas.yview,self.canvas.yview_moveto)):
                start,end=view()
                if position<start*total:move(max(0,position-8)/total)
                elif position+length>end*total:move(max(0,position+length-(end-start)*total+8)/total)
        except tk.TclError:pass


def fit(window,width=None,height=None):
    window.update_idletasks()
    x,y,available_w,available_h=work_area(window)
    w=min(width or window.winfo_reqwidth(),max(240,available_w-24))
    h=min(height or window.winfo_reqheight(),max(200,available_h-64))
    window.minsize(min(640,w),min(400,h))
    window.geometry(f'{w}x{h}+{x+max(0,(available_w-w)//2)}+{y+max(0,(available_h-h)//2-20)}')


def place_popup(window,parent):
    """Place on the parent's monitor; size/scroll adaptation remains separate."""
    window.update_idletasks()
    left,top,width,height=work_area(parent)
    w=max(window.winfo_width(),window.winfo_reqwidth())
    h=max(window.winfo_height(),window.winfo_reqheight())
    x=max(left,min(parent.winfo_rootx()+(parent.winfo_width()-w)//2,left+width-w-8))
    y=max(top,min(parent.winfo_rooty()+(parent.winfo_height()-h)//2,top+height-h-40))
    window.geometry(f'+{x}+{y}')


def watch_popups(root):
    def changed(event):
        win=event.widget
        if not isinstance(win,tk.Toplevel) or hasattr(win,'_viewport') or getattr(win,'_viewport_job',None):return
        if win.overrideredirect():return  # Tooltips are not resizable dialogs.
        def adapt():
            win._viewport_job=None
            if not win.winfo_exists() or hasattr(win,'_viewport'):return
            win.update_idletasks()
            width,height=win.winfo_width(),win.winfo_height()
            _,_,aw,ah=work_area(win)
            oversized=max(win.winfo_reqwidth(),width)>aw-24 or max(win.winfo_reqheight(),height)>ah-64
            clipped=width+1<win.winfo_reqwidth() or height+1<win.winfo_reqheight()
            if not oversized and not clipped:return
            children=[c for c in win.winfo_children() if c.winfo_manager() in ('pack','grid')]
            if not children:return
            placements=[(c,c.winfo_manager(),c.pack_info() if c.winfo_manager()=='pack' else c.grid_info()) for c in children]
            columns,rows=win.grid_size()
            grid_columns=[win.grid_columnconfigure(i) for i in range(columns)]
            grid_rows=[win.grid_rowconfigure(i) for i in range(rows)]
            for c,manager,info in placements:getattr(c,manager+'_forget')()
            viewport=Viewport(win);win._viewport=viewport
            for i,config in enumerate(grid_columns):viewport.body.grid_columnconfigure(i,**config)
            for i,config in enumerate(grid_rows):viewport.body.grid_rowconfigure(i,**config)
            for c,manager,info in placements:
                info['in']=viewport.body
                getattr(c,manager)(**info)
            if oversized:fit(win,min(width,aw-24),min(height,ah-64))
            else:win.geometry(f'{width}x{height}')
            viewport.schedule()
        win._viewport_job=root.after_idle(adapt)
    root.bind_all('<Map>',changed,add='+')
    root.bind_all('<Configure>',changed,add='+')


def message_area(parent,lines=2):
    """Reserve message height so status changes do not move controls vertically."""
    from tkinter import font
    style=ttk.Style(parent)
    metrics=font.Font(root=parent,font=style.lookup('Muted.TLabel','font') or 'TkDefaultFont')
    frame=ttk.Frame(parent,height=metrics.metrics('linespace')*lines+4)
    frame.pack(fill='x');frame.pack_propagate(False)
    return frame


def fit_content(window,body,width=1040,height=900):
    window.update_idletasks()
    fit(window,max(width,body.winfo_reqwidth()+20),max(height,body.winfo_reqheight()+20))
