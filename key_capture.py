"""Focused-widget key capture only: no global hooks, key injection or polling."""
from remapping import KEYS

SYMBOLS={'BackSpace':'BACKSPACE','Return':'ENTER','Escape':'ESC','Tab':'TAB','ISO_Left_Tab':'TAB',
    'space':'SPACE','Control_L':'CTRL','Control_R':'RCTRL','Shift_L':'SHIFT','Shift_R':'RSHIFT',
    'Alt_L':'ALT','Alt_R':'RALT','Meta_L':'WIN','Meta_R':'RWIN','Super_L':'WIN','Super_R':'RWIN',
    'Win_L':'WIN','Win_R':'RWIN','Caps_Lock':'CAPSLOCK','Num_Lock':'NUMLOCK','Scroll_Lock':'SCROLLLOCK',
    'Prior':'PAGEUP','Next':'PAGEDOWN','Print':'PRINTSCREEN','Pause':'PAUSE',
    'KP_Enter':'NUMENTER','KP_Add':'NUMADD','KP_Subtract':'NUMSUBTRACT','KP_Multiply':'NUMMULTIPLY',
    'KP_Divide':'NUMDIVIDE','KP_Decimal':'NUMDECIMAL','KP_Delete':'NUMDECIMAL',
    'KP_Insert':'NUM0','KP_End':'NUM1','KP_Down':'NUM2','KP_Next':'NUM3','KP_Left':'NUM4',
    'KP_Begin':'NUM5','KP_Right':'NUM6','KP_Home':'NUM7','KP_Up':'NUM8','KP_Prior':'NUM9'}
SYMBOLS.update({f'KP_{i}':f'NUM{i}' for i in range(10)})
VK={8:'BACKSPACE',9:'TAB',13:'ENTER',27:'ESC',32:'SPACE',33:'PAGEUP',34:'PAGEDOWN',35:'END',36:'HOME',
    37:'LEFT',38:'UP',39:'RIGHT',40:'DOWN',45:'INSERT',46:'DELETE',
    106:'NUMMULTIPLY',107:'NUMADD',109:'NUMSUBTRACT',110:'NUMDECIMAL',111:'NUMDIVIDE',
    186:'SEMICOLON',187:'EQUAL',188:'COMMA',189:'MINUS',190:'PERIOD',191:'SLASH',192:'GRAVE',
    219:'LEFTBRACKET',220:'BACKSLASH',221:'RIGHTBRACKET',222:'QUOTE'}
VK.update({i:chr(i) for i in range(65,91)})
VK.update({i:chr(i) for i in range(48,58)})
VK.update({96+i:f'NUM{i}' for i in range(10)})
VK.update({112+i:f'F{i+1}' for i in range(24)})

def event_key(event):
    symbol=getattr(event,'keysym','')
    if symbol in SYMBOLS:return SYMBOLS[symbol]
    # Windows virtual keys preserve physical Latin keys regardless of IME/Shift.
    if getattr(event,'keycode',None) in VK:return VK[event.keycode]
    name=symbol.upper()
    return name if name in KEYS else None

class KeyCapture:
    def __init__(self):self.reset()
    def reset(self):
        self.down=set();self.combo=[];self.invalid=False
    def press(self,key):
        if not self.down:self.combo=[];self.invalid=False
        if key is None:self.invalid=True;self.down.add('?');return
        if key in self.down:return  # OS auto-repeat never appends text.
        self.down.add(key)
        if key not in self.combo:self.combo.append(key)
        if len(self.combo)>4:self.invalid=True
    def release(self,key):
        if (key or '?') not in self.down:return None
        self.down.discard(key or '?')
        if self.down:return None
        if self.invalid:return None
        return '+'.join(sorted(self.combo,key=lambda k:0 if KEYS[k]>=224 else 1))
